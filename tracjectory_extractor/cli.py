"""Command-line interface for trajectory extraction and ontology induction."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .codex_runner import CodexConfig, CodexRunner
from .coding import closed_code, consolidate, iterative_code, open_code
from .extractor import discover_trajectories, normalize_trajectory, write_jsonl


def _runner(args: argparse.Namespace) -> CodexRunner:
    return CodexRunner(
        CodexConfig(
            executable=args.codex,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            timeout_seconds=args.timeout,
            reuse_checkpoints_across_reasoning=(
                args.reuse_checkpoints_across_reasoning
            ),
        )
    )


def _add_codex_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--codex", default="codex", help="Codex executable")
    parser.add_argument(
        "--model",
        default="gpt-5.6-luna",
        help="Codex model ID (default: gpt-5.6-luna)",
    )
    parser.add_argument(
        "--reasoning-effort", default="xhigh", help="Codex reasoning effort"
    )
    parser.add_argument("--timeout", type=int, default=1800, help="Seconds per call")
    parser.add_argument(
        "--reuse-checkpoints-across-reasoning",
        action="store_true",
        help=(
            "Reuse checkpoints when only the reasoning effort changed; new "
            "requests use the selected reasoning effort"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser("normalize", help="Normalize raw trajectories")
    normalize.add_argument("inputs", nargs="+", type=Path)
    normalize.add_argument("--output", type=Path, required=True)

    open_parser = subparsers.add_parser("open-code", help="Open-code every event")
    open_parser.add_argument("events", type=Path)
    open_parser.add_argument("--output-dir", type=Path, required=True)
    open_parser.add_argument("--batch-size", type=int, default=20)
    _add_codex_options(open_parser)

    iterative_parser = subparsers.add_parser(
        "iterative-code",
        help="Induce a frozen v1 ontology and validate it until saturation",
    )
    iterative_parser.add_argument("events", type=Path)
    iterative_parser.add_argument("--output-dir", type=Path, required=True)
    iterative_parser.add_argument("--batch-size", type=int, default=20)
    iterative_parser.add_argument("--discovery-rounds", type=int, default=3)
    iterative_parser.add_argument("--max-iterations", type=int, default=8)
    iterative_parser.add_argument("--stable-rounds", type=int, default=2)
    iterative_parser.add_argument("--random-seed", type=int, default=1729)
    iterative_parser.add_argument("--max-no-fit-rate", type=float, default=0.01)
    iterative_parser.add_argument("--max-ambiguous-rate", type=float, default=0.01)
    iterative_parser.add_argument("--max-change-rate", type=float, default=0.01)
    _add_codex_options(iterative_parser)

    consolidate_parser = subparsers.add_parser(
        "consolidate", help="Consolidate open labels into an ontology"
    )
    consolidate_parser.add_argument("codings", type=Path)
    consolidate_parser.add_argument("--output", type=Path, required=True)
    _add_codex_options(consolidate_parser)

    closed_parser = subparsers.add_parser(
        "closed-code", help="Apply a frozen ontology to every event"
    )
    closed_parser.add_argument("events", type=Path)
    closed_parser.add_argument("ontology", type=Path)
    closed_parser.add_argument("--output-dir", type=Path, required=True)
    closed_parser.add_argument("--batch-size", type=int, default=20)
    _add_codex_options(closed_parser)

    pipeline = subparsers.add_parser("pipeline", help="Run all four stages")
    pipeline.add_argument("inputs", nargs="+", type=Path)
    pipeline.add_argument("--work-dir", type=Path, required=True)
    pipeline.add_argument("--batch-size", type=int, default=20)
    _add_codex_options(pipeline)
    return parser


def _normalize(inputs: list[Path], output: Path) -> Path:
    events = []
    for trajectory in discover_trajectories(inputs):
        events.extend(normalize_trajectory(trajectory))
    write_jsonl(output, events)
    return output


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if args.command == "normalize":
        _normalize(args.inputs, args.output)
        return 0

    with _runner(args) as runner:
        if args.command == "open-code":
            open_code(args.events, args.output_dir, runner, args.batch_size)
        elif args.command == "iterative-code":
            iterative_code(
                args.events,
                args.output_dir,
                runner,
                batch_size=args.batch_size,
                discovery_rounds=args.discovery_rounds,
                max_iterations=args.max_iterations,
                stable_rounds=args.stable_rounds,
                random_seed=args.random_seed,
                max_no_fit_rate=args.max_no_fit_rate,
                max_ambiguous_rate=args.max_ambiguous_rate,
                max_change_rate=args.max_change_rate,
            )
        elif args.command == "consolidate":
            consolidate(args.codings, args.output, runner)
        elif args.command == "closed-code":
            closed_code(
                args.events, args.ontology, args.output_dir, runner, args.batch_size
            )
        elif args.command == "pipeline":
            args.work_dir.mkdir(parents=True, exist_ok=True)
            events = _normalize(args.inputs, args.work_dir / "normalized_events.jsonl")
            codings = open_code(events, args.work_dir, runner, args.batch_size)
            ontology = consolidate(codings, args.work_dir / "ontology.v1.json", runner)
            closed_code(events, ontology, args.work_dir, runner, args.batch_size)
    return 0
