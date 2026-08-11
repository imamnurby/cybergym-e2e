#!/usr/bin/env python3
"""Generate a self-contained HTML report from agent trajectory logs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from trajectory_parser import parse_trajectories


PHASE_ORDER = (
    "setup",
    "investigation",
    "poc",
    "patch",
    "validation",
    "termination",
    "other",
)


def discover_logs(inputs: Iterable[Path]) -> list[Path]:
    """Return unique trajectory log files in deterministic order."""
    found: dict[Path, None] = {}
    for input_path in inputs:
        path = input_path.expanduser()
        if path.is_dir():
            run_logs = list(path.rglob("*_run.log"))
            candidates = list(run_logs)
            for jsonl_path in path.rglob("trajectory/attempt_*.jsonl"):
                run_dir = jsonl_path.parent.parent
                task_dir = run_dir.parent
                batch_log = task_dir.parent / f"{task_dir.name}_run.log"
                if not batch_log.is_file():
                    candidates.append(jsonl_path)
        elif path.is_file():
            candidates = (path,)
        else:
            raise FileNotFoundError(f"Input does not exist: {path}")
        for candidate in candidates:
            found[candidate.resolve()] = None
    return sorted(found, key=lambda item: str(item))


def _json_value(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def build_report_data(log_paths: Iterable[Path]) -> list[dict[str, Any]]:
    """Parse logs and return JSON-safe report data."""
    reports: list[dict[str, Any]] = []
    for path in log_paths:
        for trajectory in parse_trajectories(path):
            parsed = _json_value(trajectory)
            if not isinstance(parsed, dict):
                raise TypeError(f"Parser returned an unsupported value for {path}")
            parsed.setdefault("source", str(path))
            parsed.setdefault("task", path.name.removesuffix("_run.log"))
            parsed.setdefault("status", "unknown")
            parsed.setdefault("events", [])
            parsed.setdefault("steps", [])
            parsed.setdefault("idle_gaps", [])
            parsed.setdefault("markers", [])
            parsed.setdefault("validation", [])
            reports.append(parsed)
    return reports


def _safe_json(data: Any) -> str:
    """Encode data for an application/json script element."""
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_html(
    runs: list[dict[str, Any]],
    *,
    title: str = "Trajectory report",
    generated_at: str | None = None,
) -> str:
    """Render parsed runs as a portable interactive HTML document."""
    payload = {
        "title": title,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs": runs,
        "phase_order": PHASE_ORDER,
    }
    encoded_payload = _safe_json(payload)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html_text(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080d18;
      --surface: #101827;
      --surface-2: #162235;
      --surface-3: #1c2a40;
      --border: #2a3b55;
      --text: #e8eef7;
      --muted: #94a4bb;
      --faint: #64748b;
      --accent: #5dd6c0;
      --success: #63d894;
      --failure: #ff727f;
      --warning: #f7c968;
      --setup: #7aa2f7;
      --investigation: #bb9af7;
      --poc: #2ac3de;
      --patch: #e0af68;
      --validation: #9ece6a;
      --termination: #f7768e;
      --other: #737aa2;
      --shadow: 0 18px 50px rgb(0 0 0 / 24%);
    }}
    * {{ box-sizing: border-box; }}
    html {{ background: var(--bg); scroll-behavior: smooth; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 15% -5%, rgb(93 214 192 / 14%), transparent 35rem),
        radial-gradient(circle at 95% 10%, rgb(122 162 247 / 12%), transparent 32rem),
        var(--bg);
      font: 14px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    button, input, select {{ font: inherit; }}
    .shell {{ width: min(1500px, calc(100% - 40px)); margin: 0 auto; padding: 44px 0 80px; }}
    .hero {{ display: flex; align-items: end; justify-content: space-between; gap: 24px; margin-bottom: 28px; }}
    .eyebrow {{ margin: 0 0 8px; color: var(--accent); font-size: 12px; font-weight: 800; letter-spacing: .14em; text-transform: uppercase; }}
    h1 {{ margin: 0; font-size: clamp(30px, 4vw, 48px); line-height: 1.05; letter-spacing: -.035em; }}
    .subtitle {{ max-width: 760px; margin: 12px 0 0; color: var(--muted); font-size: 15px; }}
    .generated {{ color: var(--faint); font-size: 12px; white-space: nowrap; }}
    .overview {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 22px; }}
    .metric {{ min-height: 108px; padding: 17px 18px; border: 1px solid var(--border); border-radius: 15px; background: rgb(16 24 39 / 86%); box-shadow: var(--shadow); }}
    .metric-label {{ color: var(--muted); font-size: 11px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }}
    .metric-value {{ margin-top: 8px; font-size: 28px; font-weight: 760; letter-spacing: -.03em; }}
    .metric-note {{ margin-top: 2px; color: var(--faint); font-size: 12px; }}
    .controls {{ position: sticky; top: 10px; z-index: 20; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 0 0 22px; padding: 11px; border: 1px solid var(--border); border-radius: 14px; background: rgb(8 13 24 / 90%); box-shadow: 0 10px 35px rgb(0 0 0 / 30%); backdrop-filter: blur(16px); }}
    .controls input, .controls select {{ min-height: 38px; color: var(--text); border: 1px solid var(--border); border-radius: 9px; outline: none; background: var(--surface); }}
    .controls input {{ flex: 1 1 260px; padding: 0 12px; }}
    .controls select {{ padding: 0 32px 0 10px; }}
    .controls input:focus, .controls select:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px rgb(93 214 192 / 12%); }}
    .button {{ min-height: 38px; padding: 0 12px; color: var(--text); border: 1px solid var(--border); border-radius: 9px; background: var(--surface-2); cursor: pointer; }}
    .button:hover {{ border-color: #46617f; background: var(--surface-3); }}
    .control-check {{ display: inline-flex; align-items: center; gap: 7px; min-height: 38px; padding: 0 7px; color: var(--muted); white-space: nowrap; }}
    .control-check input {{ flex: none; min-height: 0; width: 15px; height: 15px; accent-color: var(--accent); }}
    .panel {{ margin-bottom: 22px; overflow: hidden; border: 1px solid var(--border); border-radius: 16px; background: rgb(16 24 39 / 82%); box-shadow: var(--shadow); }}
    .panel-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 18px; border-bottom: 1px solid var(--border); }}
    .panel-title {{ margin: 0; font-size: 15px; letter-spacing: -.01em; }}
    .comparison-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; text-align: left; }}
    th, td {{ padding: 12px 16px; border-bottom: 1px solid rgb(42 59 85 / 70%); white-space: nowrap; }}
    th {{ color: var(--muted); background: rgb(22 34 53 / 70%); font-size: 10px; letter-spacing: .09em; text-transform: uppercase; }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tbody tr:hover td {{ background: rgb(28 42 64 / 50%); }}
    .runs {{ display: grid; gap: 22px; }}
    .run {{ overflow: hidden; border: 1px solid var(--border); border-radius: 18px; background: rgb(16 24 39 / 88%); box-shadow: var(--shadow); }}
    .run.hidden {{ display: none; }}
    .run-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 20px 22px 16px; }}
    .run-title {{ margin: 0; font-size: 21px; line-height: 1.2; letter-spacing: -.02em; }}
    .run-meta {{ display: flex; flex-wrap: wrap; gap: 7px 14px; margin-top: 7px; color: var(--muted); font-size: 12px; }}
    .status {{ display: inline-flex; align-items: center; gap: 7px; padding: 6px 10px; border: 1px solid currentColor; border-radius: 999px; font-size: 11px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }}
    .status::before {{ width: 7px; height: 7px; border-radius: 50%; background: currentColor; content: ""; box-shadow: 0 0 12px currentColor; }}
    .status-success {{ color: var(--success); background: rgb(99 216 148 / 8%); }}
    .status-failed, .status-error {{ color: var(--failure); background: rgb(255 114 127 / 8%); }}
    .status-unknown {{ color: var(--warning); background: rgb(247 201 104 / 8%); }}
    .run-stats {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); background: rgb(8 13 24 / 40%); }}
    .run-stat {{ padding: 12px 20px; border-right: 1px solid var(--border); }}
    .run-stat:last-child {{ border-right: 0; }}
    .run-stat span {{ display: block; color: var(--faint); font-size: 10px; font-weight: 750; letter-spacing: .07em; text-transform: uppercase; }}
    .run-stat strong {{ display: block; margin-top: 3px; font-size: 16px; }}
    .phase-area {{ padding: 18px 22px 15px; }}
    .section-label {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 9px; color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; }}
    .phase-track {{ position: relative; display: flex; height: 30px; overflow: hidden; border: 1px solid var(--border); border-radius: 9px; background: #0a1120; }}
    .phase-segment {{ position: relative; min-width: 3px; border-right: 1px solid rgb(8 13 24 / 45%); cursor: help; }}
    .phase-segment:last-child {{ border-right: 0; }}
    .phase-segment:hover {{ filter: brightness(1.2); }}
    .idle-marker {{ position: absolute; z-index: 3; top: 0; bottom: 0; min-width: 2px; border-left: 1px solid rgb(255 114 127 / 90%); border-right: 1px solid rgb(255 114 127 / 90%); background: repeating-linear-gradient(135deg, rgb(255 114 127 / 42%) 0 4px, rgb(255 114 127 / 10%) 4px 8px); pointer-events: none; }}
    .phase-legend {{ display: flex; flex-wrap: wrap; gap: 7px 15px; margin-top: 10px; color: var(--muted); font-size: 11px; }}
    .legend-item {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend-dot {{ width: 8px; height: 8px; border-radius: 3px; }}
    .run-body {{ display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(270px, .65fr); gap: 22px; padding: 4px 22px 22px; }}
    .timeline {{ position: relative; padding-left: 92px; }}
    .timeline::before {{ position: absolute; top: 8px; bottom: 8px; left: 76px; width: 1px; background: var(--border); content: ""; }}
    .step {{ position: relative; min-height: 68px; padding: 0 0 17px 19px; }}
    .step:last-child {{ padding-bottom: 0; }}
    .step-time {{ position: absolute; top: 0; left: -92px; width: 68px; color: var(--faint); font: 10px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; text-align: right; white-space: nowrap; }}
    .step-dot {{ position: absolute; top: 3px; left: -20px; width: 9px; height: 9px; border: 2px solid var(--surface); border-radius: 50%; background: var(--other); box-shadow: 0 0 0 1px var(--border); }}
    .step-head {{ display: flex; flex-wrap: wrap; align-items: baseline; gap: 7px; }}
    .step-title {{ font-weight: 720; }}
    .phase-chip {{ padding: 2px 6px; border-radius: 5px; color: #07101a; font-size: 9px; font-weight: 850; letter-spacing: .06em; text-transform: uppercase; }}
    .step-duration {{ color: var(--faint); font-size: 11px; }}
    .step-summary {{ margin: 4px 0 0; color: var(--muted); font-size: 12px; }}
    details {{ margin-top: 7px; }}
    summary {{ color: var(--accent); font-size: 11px; cursor: pointer; user-select: none; }}
    pre {{ max-height: 320px; margin: 7px 0 0; overflow: auto; padding: 11px 12px; color: #cbd7e8; border: 1px solid var(--border); border-radius: 8px; background: #080e19; font: 10.5px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }}
    .side {{ display: grid; align-content: start; gap: 13px; }}
    .side-box {{ padding: 14px; border: 1px solid var(--border); border-radius: 11px; background: rgb(8 13 24 / 45%); }}
    .side-title {{ margin: 0 0 10px; color: var(--muted); font-size: 10px; font-weight: 800; letter-spacing: .09em; text-transform: uppercase; }}
    .validation-list, .marker-list, .gap-list {{ display: grid; gap: 8px; }}
    .validation-item, .marker-item, .gap-item {{ display: grid; grid-template-columns: auto 1fr; align-items: start; gap: 8px; color: var(--muted); font-size: 11px; }}
    .mini-dot {{ width: 8px; height: 8px; margin-top: 4px; border-radius: 50%; background: var(--faint); }}
    .mini-dot.passed, .mini-dot.success {{ background: var(--success); }}
    .mini-dot.failed, .mini-dot.error {{ background: var(--failure); }}
    .mini-dot.warning, .mini-dot.timeout, .mini-dot.idle {{ background: var(--warning); }}
    .source {{ overflow-wrap: anywhere; color: var(--faint); font: 10px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .actions {{ margin: 0 22px 22px; overflow: hidden; border: 1px solid var(--border); border-radius: 12px; background: rgb(8 13 24 / 45%); }}
    .actions-head {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; padding: 13px 14px; border-bottom: 1px solid var(--border); }}
    .actions-heading {{ display: flex; align-items: baseline; gap: 9px; }}
    .actions-title {{ margin: 0; font-size: 13px; }}
    .actions-count {{ color: var(--faint); font-size: 11px; }}
    .actions-controls {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .actions-controls select {{ min-height: 32px; padding: 0 29px 0 9px; color: var(--text); border: 1px solid var(--border); border-radius: 8px; background: var(--surface); }}
    .event-list {{ display: grid; }}
    .event {{ display: grid; grid-template-columns: 118px minmax(115px, .45fr) minmax(0, 1.5fr) 70px; gap: 12px; align-items: start; padding: 11px 14px; border-bottom: 1px solid rgb(42 59 85 / 65%); }}
    .event:last-child {{ border-bottom: 0; }}
    .event:hover {{ background: rgb(28 42 64 / 35%); }}
    .event-time {{ color: var(--faint); font: 10px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .event-offset {{ display: block; color: var(--muted); }}
    .event-type {{ min-width: 0; color: var(--accent); font: 10.5px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }}
    .event-kind {{ display: inline-block; margin-top: 4px; padding: 1px 5px; border: 1px solid var(--border); border-radius: 4px; color: var(--muted); font: 9px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace; text-transform: uppercase; }}
    .event-main {{ min-width: 0; }}
    .event-title {{ overflow: hidden; font-size: 12px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }}
    .event-preview {{ margin-top: 3px; overflow: hidden; color: var(--muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }}
    .event details {{ margin-top: 5px; }}
    .event-line {{ color: var(--faint); font: 10px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; text-align: right; }}
    .actions-more {{ display: flex; justify-content: center; padding: 12px; border-top: 1px solid var(--border); }}
    .actions-more[hidden] {{ display: none; }}
    .empty {{ padding: 24px; color: var(--muted); text-align: center; }}
    .footer {{ margin-top: 26px; color: var(--faint); font-size: 11px; text-align: center; }}
    .phase-setup, .bg-setup {{ background: var(--setup); }}
    .phase-investigation, .bg-investigation {{ background: var(--investigation); }}
    .phase-poc, .bg-poc {{ background: var(--poc); }}
    .phase-patch, .bg-patch {{ background: var(--patch); }}
    .phase-validation, .bg-validation {{ background: var(--validation); }}
    .phase-termination, .bg-termination {{ background: var(--termination); }}
    .phase-other, .bg-other {{ background: var(--other); }}
    @media (max-width: 1000px) {{
      .overview {{ grid-template-columns: repeat(3, 1fr); }}
      .run-body {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 680px) {{
      .shell {{ width: min(100% - 20px, 1500px); padding-top: 26px; }}
      .hero {{ align-items: flex-start; flex-direction: column; }}
      .overview {{ grid-template-columns: repeat(2, 1fr); }}
      .run-head {{ padding-inline: 15px; }}
      .run-stats {{ grid-template-columns: repeat(2, 1fr); }}
      .run-stat {{ border-bottom: 1px solid var(--border); }}
      .phase-area, .run-body {{ padding-inline: 15px; }}
      .actions {{ margin-inline: 15px; }}
      .actions-head {{ align-items: stretch; flex-direction: column; }}
      .actions-controls select {{ flex: 1 1 130px; min-width: 0; }}
      .event {{ grid-template-columns: 92px minmax(0, 1fr) 50px; gap: 8px; padding-inline: 10px; }}
      .event-type {{ grid-column: 2; grid-row: 1; }}
      .event-main {{ grid-column: 1 / -1; grid-row: 2; }}
      .event-line {{ grid-column: 3; grid-row: 1; }}
      .timeline {{ padding-left: 72px; }}
      .timeline::before {{ left: 57px; }}
      .step-time {{ left: -72px; width: 48px; }}
    }}
    @media print {{
      :root {{ color-scheme: light; --bg: #fff; --surface: #fff; --surface-2: #f5f7fa; --border: #ccd3dd; --text: #152033; --muted: #4a596d; --faint: #65748a; }}
      body {{ background: #fff; }}
      .shell {{ width: 100%; padding: 0; }}
      .controls {{ display: none; }}
      .run, .panel, .metric {{ box-shadow: none; break-inside: avoid; }}
      details {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">Agent trajectory analysis</p>
        <h1 id="report-title"></h1>
        <p class="subtitle">High-level phases, validation outcomes, idle periods, and supporting trajectory evidence.</p>
      </div>
      <div class="generated" id="generated-at"></div>
    </header>
    <section class="overview" id="overview" aria-label="Report overview"></section>
    <nav class="controls" aria-label="Report filters">
      <input id="search" type="search" placeholder="Search tasks, models, phases, and evidence" aria-label="Search runs">
      <select id="status-filter" aria-label="Filter by status">
        <option value="all">All statuses</option>
        <option value="success">Success</option>
        <option value="failed">Failed</option>
        <option value="unknown">Unknown</option>
      </select>
      <label class="control-check"><input id="idle-only" type="checkbox"> Has idle gaps</label>
      <button class="button" id="expand-all" type="button">Expand evidence</button>
    </nav>
    <section class="panel" id="comparison-panel">
      <div class="panel-head"><h2 class="panel-title">Run comparison</h2><span class="generated" id="visible-count"></span></div>
      <div class="comparison-wrap"><table><thead><tr><th>Task</th><th>Status</th><th>Model</th><th>Duration</th><th>Actions</th><th>Idle time</th><th>Final phase</th></tr></thead><tbody id="comparison-body"></tbody></table></div>
    </section>
    <section class="runs" id="runs"></section>
    <footer class="footer">Generated locally from benchmark logs. No external assets or network access are required.</footer>
  </main>
  <script id="report-data" type="application/json">{encoded_payload}</script>
  <script>
    (() => {{
      "use strict";
      const report = JSON.parse(document.getElementById("report-data").textContent);
      const phaseColors = {{setup:"var(--setup)", investigation:"var(--investigation)", poc:"var(--poc)", patch:"var(--patch)", validation:"var(--validation)", termination:"var(--termination)", other:"var(--other)"}};
      const state = {{ query: "", status: "all", idleOnly: false, expanded: false }};
      const el = (tag, className, text) => {{
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
      }};
      const num = (value, fallback = 0) => Number.isFinite(Number(value)) ? Number(value) : fallback;
      const text = (value, fallback = "") => value === undefined || value === null ? fallback : String(value);
      const duration = seconds => {{
        const value = Math.max(0, num(seconds));
        if (value < 60) return `${{value.toFixed(value < 10 ? 1 : 0)}}s`;
        if (value < 3600) return `${{Math.floor(value / 60)}}m ${{Math.round(value % 60)}}s`;
        return `${{Math.floor(value / 3600)}}h ${{Math.floor((value % 3600) / 60)}}m`;
      }};
      const clock = seconds => {{
        const value = Math.max(0, Math.floor(num(seconds)));
        const h = Math.floor(value / 3600);
        const m = Math.floor((value % 3600) / 60);
        const s = value % 60;
        return h ? `${{h}}:${{String(m).padStart(2,"0")}}:${{String(s).padStart(2,"0")}}` : `${{m}}:${{String(s).padStart(2,"0")}}`;
      }};
      const statusClass = value => {{
        const normalized = text(value, "unknown").toLowerCase();
        if (["success", "passed", "pass"].includes(normalized)) return "success";
        if (["failed", "failure", "error", "timeout"].includes(normalized)) return normalized === "error" ? "error" : "failed";
        return "unknown";
      }};
      const normalizeRun = (run, index) => {{
        const events = Array.isArray(run.events) ? run.events : [];
        const steps = Array.isArray(run.steps) ? run.steps : [];
        const gaps = Array.isArray(run.idle_gaps) ? run.idle_gaps : [];
        const markers = Array.isArray(run.markers) ? run.markers : [];
        const validation = Array.isArray(run.validation) ? run.validation : [];
        const runDuration = num(run.duration_seconds, Math.max(0, ...events.map(event => num(event.offset_seconds))));
        const search = JSON.stringify({{task:run.task, model:run.model, status:run.status, steps, markers, validation}}).toLowerCase();
        return {{...run, _index:index, events, steps, gaps, markers, validation, runDuration, search}};
      }};
      const runs = (Array.isArray(report.runs) ? report.runs : []).map(normalizeRun);
      document.getElementById("report-title").textContent = text(report.title, "Trajectory report");
      document.getElementById("generated-at").textContent = `Generated ${{new Date(report.generated_at).toLocaleString()}}`;

      function idleSeconds(run) {{ return run.gaps.reduce((sum, gap) => sum + num(gap.duration_seconds), 0); }}
      function phaseName(value) {{ const phase = text(value, "other").toLowerCase(); return phaseColors[phase] ? phase : "other"; }}
      function visibleRuns() {{
        return runs.filter(run => {{
          const matchesQuery = !state.query || run.search.includes(state.query);
          const runStatus = statusClass(run.status);
          const matchesStatus = state.status === "all" || runStatus === state.status;
          return matchesQuery && matchesStatus && (!state.idleOnly || run.gaps.length > 0);
        }});
      }}
      function metric(label, value, note) {{
        const box = el("article", "metric");
        box.append(el("div", "metric-label", label), el("div", "metric-value", value), el("div", "metric-note", note));
        return box;
      }}
      function renderOverview() {{
        const overview = document.getElementById("overview");
        overview.replaceChildren();
        const successes = runs.filter(run => statusClass(run.status) === "success").length;
        const failures = runs.filter(run => statusClass(run.status) === "failed").length;
        const totalTime = runs.reduce((sum, run) => sum + run.runDuration, 0);
        const totalIdle = runs.reduce((sum, run) => sum + idleSeconds(run), 0);
        const actions = runs.reduce((sum, run) => sum + run.events.filter(event => text(event.kind).toLowerCase() === "action").length, 0);
        overview.append(
          metric("Runs", runs.length, `${{successes}} passed, ${{failures}} failed`),
          metric("Success rate", runs.length ? `${{Math.round(successes / runs.length * 100)}}%` : "N/A", "Independent validation result"),
          metric("Total duration", duration(totalTime), "Sum of reported run durations"),
          metric("Idle time", duration(totalIdle), totalTime ? `${{Math.round(totalIdle / totalTime * 100)}}% of run time` : "No duration data"),
          metric("Actions", actions.toLocaleString(), "Parsed agent actions")
        );
      }}
      function statusBadge(value) {{
        const normalized = statusClass(value);
        return el("span", `status status-${{normalized}}`, text(value, "unknown"));
      }}
      function renderComparison(filtered) {{
        const body = document.getElementById("comparison-body");
        body.replaceChildren();
        for (const run of filtered) {{
          const row = el("tr");
          const finalStep = run.steps.length ? run.steps[run.steps.length - 1] : null;
          const values = [
            text(run.task, "Unknown task"),
            text(run.status, "unknown"),
            text(run.model, "unknown"),
            duration(run.runDuration),
            run.events.filter(event => text(event.kind).toLowerCase() === "action").length,
            duration(idleSeconds(run)),
            finalStep ? text(finalStep.title || finalStep.phase, "other") : "No steps",
          ];
          values.forEach((value, index) => {{
            const cell = el("td");
            if (index === 1) cell.append(statusBadge(value)); else cell.textContent = value;
            row.append(cell);
          }});
          body.append(row);
        }}
        if (!filtered.length) {{
          const row = el("tr");
          const cell = el("td", "empty", "No runs match the active filters.");
          cell.colSpan = 7;
          row.append(cell);
          body.append(row);
        }}
        document.getElementById("visible-count").textContent = `${{filtered.length}} of ${{runs.length}} runs`;
      }}
      function runStat(label, value) {{
        const item = el("div", "run-stat");
        item.append(el("span", "", label), el("strong", "", value));
        return item;
      }}
      function renderPhaseBar(run) {{
        const area = el("div", "phase-area");
        const label = el("div", "section-label");
        label.append(el("span", "", "Elapsed phase map"), el("span", "", "Hatched areas show idle gaps"));
        area.append(label);
        const track = el("div", "phase-track");
        const total = Math.max(1, run.runDuration, ...run.steps.map(step => num(step.end_seconds)));
        if (run.steps.length) {{
          for (const step of run.steps) {{
            const phase = phaseName(step.phase);
            const start = num(step.start_seconds);
            const end = Math.max(start, num(step.end_seconds, start));
            const segment = el("div", `phase-segment phase-${{phase}}`);
            segment.style.flex = `${{Math.max(.002, (end - start) / total)}} 1 0`;
            segment.title = `${{text(step.title || step.phase, phase)}}: ${{duration(end - start)}}`;
            track.append(segment);
          }}
        }} else {{
          const segment = el("div", "phase-segment phase-other");
          segment.style.flex = "1";
          segment.title = "No high-level steps were detected";
          track.append(segment);
        }}
        for (const gap of run.gaps) {{
          const marker = el("div", "idle-marker");
          marker.style.left = `${{Math.min(100, num(gap.start_seconds) / total * 100)}}%`;
          marker.style.width = `${{Math.max(.15, num(gap.duration_seconds) / total * 100)}}%`;
          marker.title = `Idle gap: ${{duration(gap.duration_seconds)}}`;
          track.append(marker);
        }}
        area.append(track);
        const usedPhases = [...new Set(run.steps.map(step => phaseName(step.phase)))];
        const legend = el("div", "phase-legend");
        for (const phase of usedPhases.length ? usedPhases : ["other"]) {{
          const item = el("span", "legend-item");
          item.append(el("span", `legend-dot bg-${{phase}}`), el("span", "", phase));
          legend.append(item);
        }}
        area.append(legend);
        return area;
      }}
      function evidenceText(step) {{
        const lines = Array.isArray(step.evidence_lines) ? step.evidence_lines : [];
        if (lines.length) return lines.join("\\n");
        return text(step.detail || step.evidence, "");
      }}
      function renderTimeline(run) {{
        const column = el("section");
        column.append(el("div", "section-label", "High-level steps"));
        const timeline = el("div", "timeline");
        if (!run.steps.length) timeline.append(el("div", "empty", "No high-level steps were detected."));
        for (const step of run.steps) {{
          const phase = phaseName(step.phase);
          const start = num(step.start_seconds);
          const end = Math.max(start, num(step.end_seconds, start));
          const item = el("article", "step");
          item.append(el("div", "step-time", clock(start)), el("span", "step-dot"));
          item.querySelector(".step-dot").style.background = phaseColors[phase];
          const head = el("div", "step-head");
          head.append(el("span", "step-title", text(step.title || step.phase, "Trajectory activity")));
          const chip = el("span", "phase-chip", phase);
          chip.style.background = phaseColors[phase];
          head.append(chip, el("span", "step-duration", duration(end - start)));
          item.append(head);
          if (step.summary) item.append(el("p", "step-summary", step.summary));
          const evidence = evidenceText(step);
          if (evidence) {{
            const detail = el("details");
            detail.open = state.expanded;
            detail.append(el("summary", "", "Show evidence"), el("pre", "", evidence));
            item.append(detail);
          }}
          timeline.append(item);
        }}
        column.append(timeline);
        return column;
      }}
      function sideBox(title) {{ const box = el("section", "side-box"); box.append(el("h3", "side-title", title)); return box; }}
      function renderSide(run) {{
        const side = el("aside", "side");
        const validation = sideBox("Validation");
        const validationList = el("div", "validation-list");
        if (!run.validation.length) validationList.append(el("div", "source", "No validation results detected."));
        for (const item of run.validation) {{
          const row = el("div", "validation-item");
          const itemStatus = statusClass(item.status);
          row.append(el("span", `mini-dot ${{itemStatus}}`), el("span", "", `${{text(item.stage, "Stage")}}: ${{text(item.status, "unknown")}}${{item.detail ? ` - ${{item.detail}}` : ""}}`));
          validationList.append(row);
        }}
        validation.append(validationList);
        side.append(validation);

        const gaps = sideBox("Idle gaps");
        const gapList = el("div", "gap-list");
        if (!run.gaps.length) gapList.append(el("div", "source", "No significant idle gaps detected."));
        for (const gap of run.gaps.slice().sort((a,b) => num(b.duration_seconds) - num(a.duration_seconds)).slice(0, 8)) {{
          const row = el("div", "gap-item");
          row.append(el("span", "mini-dot idle"), el("span", "", `${{duration(gap.duration_seconds)}} after ${{text(gap.start_timestamp, clock(gap.start_seconds))}}`));
          gapList.append(row);
        }}
        gaps.append(gapList);
        side.append(gaps);

        const markers = sideBox("Notable events");
        const markerList = el("div", "marker-list");
        if (!run.markers.length) markerList.append(el("div", "source", "No notable events detected."));
        for (const marker of run.markers.slice(0, 12)) {{
          const kind = text(marker.kind, "other").toLowerCase();
          const row = el("div", "marker-item");
          row.append(el("span", `mini-dot ${{kind}}`), el("span", "", text(marker.title || marker.detail, kind)));
          markerList.append(row);
        }}
        markers.append(markerList);
        side.append(markers);

        const source = sideBox("Source");
        source.append(el("div", "source", text(run.source, "Unknown log")));
        side.append(source);
        return side;
      }}
      function eventDetail(event) {{
        if (event.detail !== undefined && event.detail !== null) {{
          return typeof event.detail === "string" ? event.detail : JSON.stringify(event.detail, null, 2);
        }}
        const remaining = Object.fromEntries(Object.entries(event).filter(([key]) => !["timestamp", "offset_seconds", "kind", "action_type", "title", "phase", "line"].includes(key)));
        return Object.keys(remaining).length ? JSON.stringify(remaining, null, 2) : "";
      }}
      function selectControl(labelText, values) {{
        const select = el("select");
        select.setAttribute("aria-label", labelText);
        select.append(el("option", "", `All ${{labelText.toLowerCase()}}`));
        select.firstChild.value = "all";
        for (const value of values) {{
          const option = el("option", "", value);
          option.value = value;
          select.append(option);
        }}
        return select;
      }}
      function renderActions(run) {{
        const pageSize = 250;
        let shown = pageSize;
        let phaseFilter = "all";
        let kindFilter = "all";
        const section = el("section", "actions");
        const head = el("div", "actions-head");
        const heading = el("div", "actions-heading");
        const count = el("span", "actions-count");
        heading.append(el("h3", "actions-title", "Detailed actions"), count);
        const controls = el("div", "actions-controls");
        const phases = [...new Set(run.events.map(event => phaseName(event.phase)))].sort();
        const kinds = [...new Set(run.events.map(event => text(event.kind, "other").toLowerCase()))].sort();
        const phaseSelect = selectControl("Phases", phases);
        const kindSelect = selectControl("Kinds", kinds);
        controls.append(phaseSelect, kindSelect);
        head.append(heading, controls);
        const list = el("div", "event-list");
        const moreWrap = el("div", "actions-more");
        const more = el("button", "button", `Show ${{pageSize}} more`);
        more.type = "button";
        moreWrap.append(more);
        section.append(head, list, moreWrap);

        const filteredEvents = () => run.events.filter(event =>
          (phaseFilter === "all" || phaseName(event.phase) === phaseFilter) &&
          (kindFilter === "all" || text(event.kind, "other").toLowerCase() === kindFilter)
        );
        function update() {{
          const filtered = filteredEvents();
          const visible = filtered.slice(0, shown);
          list.replaceChildren();
          for (const event of visible) {{
            const row = el("article", "event");
            const time = el("div", "event-time", text(event.timestamp, "No timestamp"));
            time.append(el("span", "event-offset", `+${{clock(event.offset_seconds)}}`));
            const type = el("div", "event-type", text(event.action_type || event.kind, "event"));
            type.append(el("span", "event-kind", text(event.kind, "other")));
            const main = el("div", "event-main");
            main.append(el("div", "event-title", text(event.title, "Untitled event")));
            const detailText = eventDetail(event);
            if (detailText) {{
              const preview = detailText.replace(/\\s+/g, " ").trim();
              main.append(el("div", "event-preview", preview.length > 180 ? `${{preview.slice(0, 177)}}...` : preview));
              const detail = el("details");
              detail.open = state.expanded;
              detail.append(el("summary", "", "Show full detail"), el("pre", "", detailText));
              main.append(detail);
            }}
            const sourceLine = event.line === undefined || event.line === null ? "" : `L${{event.line}}`;
            row.append(time, type, main, el("div", "event-line", sourceLine));
            list.append(row);
          }}
          if (!filtered.length) list.append(el("div", "empty", "No events match these filters."));
          count.textContent = `${{Math.min(shown, filtered.length).toLocaleString()}} of ${{filtered.length.toLocaleString()}} events`;
          moreWrap.hidden = shown >= filtered.length;
        }}
        phaseSelect.addEventListener("change", event => {{ phaseFilter = event.target.value; shown = pageSize; update(); }});
        kindSelect.addEventListener("change", event => {{ kindFilter = event.target.value; shown = pageSize; update(); }});
        more.addEventListener("click", () => {{ shown += pageSize; update(); }});
        update();
        return section;
      }}
      function renderRuns(filtered) {{
        const root = document.getElementById("runs");
        root.replaceChildren();
        if (!filtered.length) {{ root.append(el("div", "panel empty", "No runs match the active filters.")); return; }}
        for (const run of filtered) {{
          const card = el("article", "run");
          const head = el("header", "run-head");
          const identity = el("div");
          identity.append(el("h2", "run-title", text(run.task, "Unknown task")));
          const meta = el("div", "run-meta");
          meta.append(el("span", "", text(run.model, "Unknown model")), el("span", "", text(run.agent, "Unknown agent")), el("span", "", text(run.prompt_style, "Unknown prompt")));
          identity.append(meta);
          head.append(identity, statusBadge(run.status));
          card.append(head);
          const stats = el("div", "run-stats");
          stats.append(
            runStat("Duration", duration(run.runDuration)),
            runStat("Actions", run.events.filter(event => text(event.kind).toLowerCase() === "action").length),
            runStat("High-level steps", run.steps.length),
            runStat("Idle time", duration(idleSeconds(run))),
            runStat("Validation", `${{run.validation.filter(item => statusClass(item.status) === "success").length}}/${{run.validation.length || 0}} passed`)
          );
          card.append(stats, renderPhaseBar(run));
          const body = el("div", "run-body");
          body.append(renderTimeline(run), renderSide(run));
          card.append(body, renderActions(run));
          root.append(card);
        }}
      }}
      function render() {{ const filtered = visibleRuns(); renderComparison(filtered); renderRuns(filtered); }}
      document.getElementById("search").addEventListener("input", event => {{ state.query = event.target.value.trim().toLowerCase(); render(); }});
      document.getElementById("status-filter").addEventListener("change", event => {{ state.status = event.target.value; render(); }});
      document.getElementById("idle-only").addEventListener("change", event => {{ state.idleOnly = event.target.checked; render(); }});
      document.getElementById("expand-all").addEventListener("click", event => {{ state.expanded = !state.expanded; event.target.textContent = state.expanded ? "Collapse evidence" : "Expand evidence"; document.querySelectorAll("details").forEach(detail => detail.open = state.expanded); }});
      renderOverview();
      render();
    }})();
  </script>
</body>
</html>
"""


def _html_text(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a self-contained HTML report from agent run logs."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="Log files or directories searched recursively for *_run.log files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("trajectory_report.html"),
        help="Output HTML path. Default: trajectory_report.html",
    )
    parser.add_argument(
        "--title", default="Trajectory report", help="Title shown in the report."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        logs = discover_logs(args.inputs)
        if not logs:
            raise FileNotFoundError("No *_run.log files were found")
        runs = build_report_data(logs)
        output = args.output.expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_html(runs, title=args.title), encoding="utf-8")
    except (FileNotFoundError, OSError, TypeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {len(runs)} runs to {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
