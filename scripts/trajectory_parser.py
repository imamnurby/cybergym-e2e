"""Parse OpenHands batch-run logs into renderer-friendly trajectory data."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
EVENT_RE = re.compile(
    r"^(?P<time>\d{2}:\d{2}:\d{2}) - "
    r"(?P<kind>USER_ACTION|ACTION|OBSERVATION)\s*$"
)
LOG_TIME_RE = re.compile(r"(?P<time>\d{2}:\d{2}:\d{2}) - openhands:")


@dataclass
class TrajectoryEvent:
    timestamp: str
    offset_seconds: float
    kind: str
    action_type: str
    title: str
    detail: str
    phase: str
    line: int


@dataclass
class TrajectoryStep:
    phase: str
    title: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    event_count: int
    summary: str
    evidence_lines: list[str] = field(default_factory=list)


@dataclass
class IdleGap:
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    start_timestamp: str
    end_timestamp: str


@dataclass
class Marker:
    kind: str
    title: str
    detail: str
    timestamp: str | None
    line: int


@dataclass
class ValidationOutcome:
    stage: int
    status: str
    detail: str
    line: int


@dataclass
class Trajectory:
    source: str
    task: str | None
    agent: str | None
    model: str | None
    prompt_style: str | None
    status: str
    duration_seconds: float | None
    timeout_seconds: float | None
    exit_code: int | None
    events: list[TrajectoryEvent] = field(default_factory=list)
    steps: list[TrajectoryStep] = field(default_factory=list)
    idle_gaps: list[IdleGap] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    validation: list[ValidationOutcome] = field(default_factory=list)
    artifacts: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for report renderers."""
        return asdict(self)


def _clock_seconds(timestamp: str) -> int:
    hours, minutes, seconds = (int(part) for part in timestamp.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _event_offsets(timestamps: list[str]) -> list[float]:
    if not timestamps:
        return []
    absolute: list[int] = []
    day_offset = 0
    previous = _clock_seconds(timestamps[0])
    absolute.append(previous)
    for timestamp in timestamps[1:]:
        current = _clock_seconds(timestamp)
        if current < previous:
            day_offset += 24 * 3600
        absolute.append(day_offset + current)
        previous = current
    origin = absolute[0]
    return [float(value - origin) for value in absolute]


def _first_match(lines: list[str], pattern: str) -> str | None:
    regex = re.compile(pattern)
    for line in lines:
        match = regex.match(line)
        if match:
            return match.group(1).strip()
    return None


def _action_type(detail: str, kind: str) -> str:
    if kind == "USER_ACTION":
        return "MessageAction"
    bold = re.search(r"\*\*([A-Za-z][A-Za-z0-9_]+)", detail)
    if bold:
        return bold.group(1)
    plain = re.search(r"\b([A-Za-z][A-Za-z0-9_]*(?:Action|Observation))\b", detail)
    return plain.group(1) if plain else kind.title()


def _command_text(detail: str) -> str | None:
    match = re.search(r"(?:^|\n)COMMAND:\s*\n+(.+?)(?=\n\d{2}:\d{2}:\d{2} - |\Z)", detail, re.S)
    if not match:
        return None
    return match.group(1).strip()


def _event_title(kind: str, action_type: str, detail: str) -> str:
    if kind == "USER_ACTION":
        return "Task received"
    command = _command_text(detail)
    if command:
        first = next((line.strip() for line in command.splitlines() if line.strip()), "")
        return first[:140]
    path = re.search(r"path=['\"]([^'\"]+)", detail)
    if path:
        verb = "Read" if "Read" in action_type else "Edit"
        return f"{verb} {path.group(1)}"
    if "ErrorObservation" in action_type:
        first = next((line.strip() for line in detail.splitlines()[1:] if line.strip()), "Error")
        return first[:140]
    labels = {
        "CmdOutputObservation": "Command result",
        "AgentStateChangedObservation": "Agent state changed",
        "RecallObservation": "Workspace context loaded",
        "FinishAction": "Agent finished",
    }
    return labels.get(action_type, action_type)


def _phase_for_action(action_type: str, title: str, detail: str) -> str:
    text = f"{action_type}\n{title}\n{detail}".lower()
    if "finishaction" in text:
        return "termination"
    if "validate.py" in text or "stage 1" in text and "--poc-file" in text:
        return "validation"
    if any(token in text for token in ("/output/fix.patch", "git diff", "apply_patch")):
        return "patch"
    if "fileeditaction" in text and "/src/" in text:
        return "patch"
    if any(
        token in text
        for token in (
            "/output/poc.bin",
            "run agent poc",
            "test_fuzztest.bin",
            "crash input",
            "corpus input",
        )
    ):
        return "poc"
    if any(
        token in text
        for token in (
            "run_poc.sh",
            "llvmfuzzertestoneinput",
            "fuzzerinterface",
            "fuzzshark.c",
        )
    ):
        return "setup"
    return "investigation"


def _parse_events(lines: list[str]) -> list[TrajectoryEvent]:
    blocks: list[tuple[str, str, int, str]] = []
    current: tuple[str, str, int] | None = None
    body: list[str] = []
    for line_number, line in enumerate(lines, 1):
        match = EVENT_RE.match(line)
        if match:
            if current:
                blocks.append((*current, "\n".join(body).strip()))
            current = (match.group("time"), match.group("kind"), line_number)
            body = []
        elif current and re.match(r"^\s+Agent:\s*[0-9.]+s .*exit=-?\d+\s*$", line):
            blocks.append((*current, "\n".join(body).strip()))
            current = None
            body = []
        elif current:
            body.append(line)
    if current:
        blocks.append((*current, "\n".join(body).strip()))

    offsets = _event_offsets([block[0] for block in blocks])
    events: list[TrajectoryEvent] = []
    active_phase = "setup"
    for (timestamp, kind, line_number, detail), offset in zip(blocks, offsets):
        action_type = _action_type(detail, kind)
        title = _event_title(kind, action_type, detail)
        if kind in {"ACTION", "USER_ACTION"}:
            active_phase = "setup" if kind == "USER_ACTION" else _phase_for_action(
                action_type, title, detail
            )
        events.append(
            TrajectoryEvent(
                timestamp=timestamp,
                offset_seconds=offset,
                kind=kind.lower(),
                action_type=action_type,
                title=title,
                detail=detail,
                phase=active_phase,
                line=line_number,
            )
        )
    return events


def _build_steps(
    events: list[TrajectoryEvent], duration_seconds: float | None
) -> list[TrajectoryStep]:
    titles = {
        "setup": "Understand the task and harness",
        "investigation": "Investigate the vulnerable code",
        "poc": "Develop and test a proof of concept",
        "patch": "Create the source patch",
        "validation": "Validate the proof of concept and patch",
        "termination": "Finish the agent run",
    }
    action_events = [event for event in events if event.kind in {"action", "user_action"}]
    if not action_events:
        return []

    # Build milestone phases instead of exposing every short action-level phase
    # change. Agents often alternate between source inspection and PoC commands.
    # Those actions belong to one high-level PoC or patching phase once that
    # milestone starts.
    boundaries: list[tuple[int, str]] = []
    first_agent_action = next(
        (index for index, event in enumerate(action_events) if event.kind == "action"),
        None,
    )
    if action_events[0].kind == "user_action":
        boundaries.append((0, "setup"))
    if first_agent_action is not None:
        boundaries.append((first_agent_action, "investigation"))

    poc_index = next(
        (index for index, event in enumerate(action_events) if event.phase == "poc"),
        None,
    )
    patch_index = next(
        (index for index, event in enumerate(action_events) if event.phase == "patch"),
        None,
    )
    if poc_index is not None and (patch_index is None or poc_index < patch_index):
        boundaries.append((poc_index, "poc"))
    if patch_index is not None:
        boundaries.append((patch_index, "patch"))
        validation_index = next(
            (
                index
                for index, event in enumerate(action_events)
                if index > patch_index and event.phase == "validation"
            ),
            None,
        )
        if validation_index is not None:
            boundaries.append((validation_index, "validation"))

    termination_index = next(
        (
            index
            for index, event in enumerate(action_events)
            if event.phase == "termination"
        ),
        None,
    )
    if termination_index is not None:
        boundaries.append((termination_index, "termination"))

    boundaries = sorted(boundaries, key=lambda boundary: boundary[0])
    # Two milestones can share a timestamp or action index. Keep the phase with
    # the later workflow meaning.
    deduplicated: list[tuple[int, str]] = []
    for boundary in boundaries:
        if deduplicated and deduplicated[-1][0] == boundary[0]:
            deduplicated[-1] = boundary
        else:
            deduplicated.append(boundary)

    steps: list[TrajectoryStep] = []
    final_end = max(
        events[-1].offset_seconds if events else 0.0,
        duration_seconds or 0.0,
    )
    for index, (start_index, phase) in enumerate(deduplicated):
        end_index = (
            deduplicated[index + 1][0]
            if index + 1 < len(deduplicated)
            else len(action_events)
        )
        phase_events = action_events[start_index:end_index]
        if not phase_events:
            continue
        start = phase_events[0].offset_seconds
        end = (
            action_events[end_index].offset_seconds
            if end_index < len(action_events)
            else final_end
        )
        count = len(phase_events)
        steps.append(
            TrajectoryStep(
                phase=phase,
                title=titles[phase],
                start_seconds=start,
                end_seconds=end,
                duration_seconds=max(0.0, end - start),
                event_count=count,
                summary=f"{count} agent action{'s' if count != 1 else ''}",
                evidence_lines=[
                    f"L{event.line}: {event.title}" for event in phase_events[:5]
                ],
            )
        )
    return steps


def _idle_gaps(events: list[TrajectoryEvent], threshold: float) -> list[IdleGap]:
    gaps: list[IdleGap] = []
    for index, event in enumerate(events):
        if event.kind != "action" or index == 0:
            continue
        previous = events[index - 1]
        if previous.kind != "observation":
            continue
        duration = event.offset_seconds - previous.offset_seconds
        if duration >= threshold:
            gaps.append(
                IdleGap(
                    start_seconds=previous.offset_seconds,
                    end_seconds=event.offset_seconds,
                    duration_seconds=duration,
                    start_timestamp=previous.timestamp,
                    end_timestamp=event.timestamp,
                )
            )
    return gaps


def _line_timestamp(line: str) -> str | None:
    match = LOG_TIME_RE.search(line)
    return match.group("time") if match else None


def _markers(lines: list[str], exit_code: int | None) -> list[Marker]:
    signatures = [
        ("api_credit", "API credit exhausted", "credit balance is too low"),
        ("budget", "Task budget exhausted", "reached maximum budget for conversation"),
        ("stuck", "Agent loop detected", "agentstuckinlooperror"),
        ("no_poc", "No proof of concept", "no poc generated"),
        ("no_patch", "No patch", "no patch generated"),
    ]
    markers: list[Marker] = []
    lowered = [line.lower() for line in lines]
    for kind, title, needle in signatures:
        for index, line in enumerate(lowered):
            if needle in line:
                detail = lines[index].strip()
                markers.append(
                    Marker(kind, title, detail[:500], _line_timestamp(lines[index]), index + 1)
                )
                break
    if exit_code == 124:
        line_number = next(
            (i for i, line in enumerate(lines, 1) if "exit=124" in line), len(lines)
        )
        markers.append(
            Marker("timeout", "Agent timed out", "The agent process reached its timeout.", None, line_number)
        )
    return sorted(markers, key=lambda marker: marker.line)


def _validation(lines: list[str]) -> list[ValidationOutcome]:
    outcomes: dict[int, ValidationOutcome] = {}
    stage_re = re.compile(r"^\s*Stage ([1-4]) \((.+?)\):\s+(PASS|FAIL|N/A)\s*$")
    for line_number, line in enumerate(lines, 1):
        match = stage_re.match(line)
        if match and match.group(3) != "N/A":
            status = {"PASS": "passed", "FAIL": "failed"}[match.group(3)]
            stage = int(match.group(1))
            outcomes[stage] = ValidationOutcome(stage, status, match.group(2), line_number)

    attempt_re = re.compile(r"^\s*Attempt \d+:\s+(.+?)\s+->")
    for line_number, line in enumerate(lines, 1):
        match = attempt_re.match(line)
        if not match:
            continue
        for stage_text, status in re.findall(r"S([1-4]):([a-z_]+)", match.group(1)):
            stage = int(stage_text)
            outcomes[stage] = ValidationOutcome(
                stage=stage,
                status=status,
                detail=f"Runner result for stage {stage}",
                line=line_number,
            )
    return [outcomes[stage] for stage in sorted(outcomes)]


def _artifact_flags(events: list[TrajectoryEvent], lines: list[str], validation: list[ValidationOutcome]) -> dict[str, bool]:
    action_text = "\n".join(event.detail.lower() for event in events if event.kind == "action")
    poc = "/output/poc.bin" in action_text
    patch = "/output/fix.patch" in action_text
    all_text = "\n".join(lines).lower()
    if "no poc generated" in all_text:
        poc = False
    if "no patch generated" in all_text:
        patch = False
    stage_status = {outcome.stage: outcome.status for outcome in validation}
    if stage_status.get(1) == "passed":
        poc = True
    if any(stage_status.get(stage) == "passed" for stage in (2, 3, 4)):
        patch = True
    return {"poc": poc, "patch": patch}


def _parse_trajectory_lines(
    source: Path,
    lines: list[str],
    idle_gap_seconds: float,
    line_offset: int = 0,
) -> Trajectory:
    """Parse the lines for one runner session."""
    task = _first_match(lines, r"^Task:\s*(.+)$")
    agent = _first_match(lines, r"^Agent:\s*(.+)$")
    model = _first_match(lines, r"^Model:\s*(.+)$")
    prompt_style = _first_match(lines, r"^Prompt style:\s*(.+)$")
    status_matches = [
        match.group(1).upper()
        for line in lines
        if (match := re.match(r"^Status:\s*(\S+)", line))
    ]
    status = status_matches[-1] if status_matches else "UNKNOWN"

    timeout_text = _first_match(lines, r"^Timeout:\s*([0-9.]+)s")
    timeout_seconds = float(timeout_text) if timeout_text else None
    timing_matches = [
        match
        for line in lines
        if (match := re.search(r"Agent:\s*([0-9.]+)s.*?exit=(-?\d+)", line))
    ]
    duration_seconds = float(timing_matches[-1].group(1)) if timing_matches else None
    exit_code = int(timing_matches[-1].group(2)) if timing_matches else None

    events = _parse_events(lines)
    validation = _validation(lines)
    trajectory = Trajectory(
        source=str(source),
        task=task,
        agent=agent,
        model=model,
        prompt_style=prompt_style,
        status=status,
        duration_seconds=duration_seconds,
        timeout_seconds=timeout_seconds,
        exit_code=exit_code,
        events=events,
        steps=_build_steps(events, duration_seconds),
        idle_gaps=_idle_gaps(events, idle_gap_seconds),
        markers=_markers(lines, exit_code),
        validation=validation,
        artifacts=_artifact_flags(events, lines, validation),
    )
    if line_offset:
        for event in trajectory.events:
            event.line += line_offset
        for marker in trajectory.markers:
            marker.line += line_offset
        for outcome in trajectory.validation:
            outcome.line += line_offset
        for step in trajectory.steps:
            step.evidence_lines = [
                re.sub(
                    r"^L(\d+):",
                    lambda match: f"L{int(match.group(1)) + line_offset}:",
                    evidence,
                )
                for evidence in step.evidence_lines
            ]
    return trajectory


def _session_starts(lines: list[str]) -> list[int]:
    """Find full runner headers, without treating the final summary as a run."""
    starts: list[int] = []
    for index, line in enumerate(lines):
        if not re.match(r"^Task:\s*\S", line):
            continue

        # A completed run repeats ``Task:`` in its summary. A real session header
        # also has Agent and Model metadata before its attempt banner or summary.
        header: list[str] = []
        for candidate in lines[index + 1 : index + 30]:
            if (
                re.match(r"^={10,}\s*$", candidate)
                or EVENT_RE.match(candidate)
                or re.match(r"^Task:\s*\S", candidate)
            ):
                break
            header.append(candidate)
        has_agent = any(re.match(r"^Agent:\s*\S", candidate) for candidate in header)
        has_model = any(re.match(r"^Model:\s*\S", candidate) for candidate in header)
        if has_agent and has_model:
            starts.append(index)
    return starts


def parse_trajectories(
    path: Path | str, idle_gap_seconds: float = 60.0
) -> list[Trajectory]:
    """Parse every OpenHands runner session in one ``*_run.log`` file.

    Batch output can append a new session to an existing log. Each returned
    trajectory has metadata, events, timing, and validation from only its own
    session. Incomplete and unstructured files still return one safe trajectory.
    """
    source = Path(path)
    raw_text = source.read_text(encoding="utf-8", errors="replace")
    lines = [ANSI_RE.sub("", line.rstrip("\r")) for line in raw_text.splitlines()]
    starts = _session_starts(lines)
    if len(starts) <= 1:
        return [_parse_trajectory_lines(source, lines, idle_gap_seconds)]

    chunks: list[tuple[int, list[str]]] = []
    # Keep any warnings before the first header with the first session.
    boundaries = [0, *starts[1:], len(lines)]
    for start, end in zip(boundaries, boundaries[1:]):
        chunks.append((start, lines[start:end]))
    return [
        _parse_trajectory_lines(source, chunk, idle_gap_seconds, line_offset=start)
        for start, chunk in chunks
    ]


def parse_log(path: Path | str, idle_gap_seconds: float = 60.0) -> Trajectory:
    """Parse one OpenHands log and return its latest runner session.

    This function keeps the original single-trajectory API. Use
    :func:`parse_trajectories` when a file can contain appended sessions. The
    parser accepts incomplete logs. Missing runner metadata is represented by
    ``None``, and an unfinished run has status ``UNKNOWN``.
    """
    return parse_trajectories(path, idle_gap_seconds=idle_gap_seconds)[-1]
