# Trajectory Extractor

This first version turns Codex JSONL trajectories into a neutral event dataset,
uses Codex to open-code every event, consolidates the discovered labels into a
candidate ontology, and applies that ontology back to every event.

The directory name intentionally follows the requested `tracjectory_extractor`
spelling.

## Stages

1. `normalize`: correlate Codex `item.started`, `item.updated`, and
   `item.completed` records and emit one neutral record per logical event.
2. `open-code`: ask Codex to describe each event without predefined categories.
3. `consolidate`: merge the open labels into a candidate ontology with explicit
   inclusion and exclusion criteria.
4. `closed-code`: apply only the frozen ontology categories and identify
   ambiguous or no-fit events.

The coding prompts deliberately omit task success and validation summaries.
Each abstract event retains its raw payload and source-line provenance.

## Usage

Normalize one or more input directories:

```bash
python -m tracjectory_extractor normalize \
  agent_output_codex_gpt54_sub/20260811_222152_2244055 \
  agent_output_codex_qwen/20260812_170242_1381707 \
  --output ontology_work/normalized_events.jsonl
```

Run the complete subscription-backed pipeline with Luna and maximum reasoning:

```bash
python -m tracjectory_extractor pipeline \
  agent_output_codex_gpt54_sub/20260811_222152_2244055 \
  agent_output_codex_qwen/20260812_170242_1381707 \
  --work-dir ontology_work \
  --model gpt-5.6-luna \
  --reasoning-effort xhigh
```

The default model and reasoning settings are already `gpt-5.6-luna` and `xhigh`.
Codex uses the active local subscription credentials. Runs are sequential to
avoid credential-refresh conflicts.

Stages can also be run separately:

```bash
python -m tracjectory_extractor open-code \
  ontology_work/normalized_events.jsonl --output-dir ontology_work

python -m tracjectory_extractor consolidate \
  ontology_work/open_codings.jsonl \
  --output ontology_work/ontology.v1.json

python -m tracjectory_extractor closed-code \
  ontology_work/normalized_events.jsonl \
  ontology_work/ontology.v1.json \
  --output-dir ontology_work
```

## Iterative saturation

Use `iterative-code` to run independent discovery rounds, freeze the resulting ontology, and validate coding through constant comparison:

```bash
python -m tracjectory_extractor iterative-code \
  ontology_work/normalized_events.jsonl \
  --output-dir ontology_work/iterative \
  --batch-size 20 \
  --discovery-rounds 3 \
  --max-iterations 8 \
  --stable-rounds 2 \
  --max-ambiguous-rate 0.01 \
  --model gpt-5.6-luna \
  --reasoning-effort xhigh
```

Each discovery round uses a separate, reproducible event order and a fresh Codex call context.
The prompt still includes the immediate previous and next events from the original trajectory.
The discovery rounds do not receive a prior ontology.

The tool consolidates all discovery labels into an initial ontology.
It freezes that ontology as version 1.
Every validation round closed-codes every event with the same frozen ontology.
The tool does not add, remove, rename, move, or redefine categories after consolidation.
The comparison report identifies each changed event and shows its previous and current coding fields.

Saturation requires the configured number of consecutive stable validation rounds.
A round is stable when the `no_fit` and `ambiguous` rates are within their limits and the full-dataset coding change rate is within the limit.
The process stops at `--max-iterations` if it does not reach saturation.
Timestamped progress logs are written to standard error during discovery, each batch, Codex requests, validation, and completion.
Checkpoint hits are also logged when a resumed run reuses finished work.
If Codex omits or duplicates an event, the tool preserves valid codings and retries only the affected events before it writes the checkpoint.
If closed coding returns a category outside the ontology, the tool preserves the batch and recodes only the invalid events with ontology-constrained enums.

The first validation round establishes the comparison baseline and does not count as a stable round.
Set `--max-iterations` to at least one more than `--stable-rounds` when the run must be able to reach saturation.

The main iterative outputs are:

- `ontology.final.json`: the final candidate ontology.
- `closed_codings.final.jsonl`: the final event coding.
- `saturation_report.json`: parameters, convergence measurements, and the reason the process stopped.
- `discovery/round_NNN/`: separate discovery results and checkpoints.
- `validation/round_NNN/`: complete closed-coding validation results and checkpoints.

Each LLM batch is checkpointed under `open_coding_batches/` or `closed_coding_batches/`.
A checkpoint is reused only when the prompt, JSON schema, runner, model, and reasoning effort have the same SHA-256 digest.
Interrupted runs are resumable, and configuration changes cannot silently reuse stale labels.

## Outputs

- `normalized_events.jsonl`: ontology-independent event evidence.
- `open_codings.jsonl`: unconstrained labels proposed for every event.
- `ontology.v1.json`: consolidated candidate ontology.
- `closed_codings.jsonl`: frozen-ontology labels plus fit assessments.

The candidate ontology still requires human review before it should be treated
as frozen research data.
