# CyberGym-E2E: Scalable Real-World Benchmark for AI Agents' End-to-End Cybersecurity Capabilities

[![Website](https://img.shields.io/badge/Website-cybergym.io-0a9396?style=flat&logo=Google-Chrome&logoColor=white)](https://www.cybergym.io/cybergym-e2e/)
[![ArXiv](https://img.shields.io/badge/arXiv-2606.04460-b31b1b?style=flat&logo=arxiv&logoColor=white)](https://arxiv.org/abs/2606.04460)
[![Hugging Face](https://img.shields.io/badge/HuggingFace-cybergym--e2e-orange?logo=huggingface&logoColor=white)](https://huggingface.co/datasets/sunblaze-ucb/cybergym-e2e)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

CyberGym-E2E is a large-scale benchmark built from real-world vulnerabilities in widely used open-source projects to evaluate AI agents' end-to-end cybersecurity capabilities, from discovering vulnerabilities to generating proof-of-concept to writing patches.

## Evaluation Modes

- **End-to-end (`e2e`):** The agent receives only source code, and must find the vulnerability, generate a proof-of-concept (`poc.bin`), and produce a patch (`fix.patch`).
- **Patch-only (`patch-only`):** The agent receives source code along with a crash log and PoC, and must produce a patch.

Validation runs in four stages:

1. Agent PoC triggers a crash without the patch
2. Agent PoC does not crash with the patch applied
3. Project test suite passes with the patch applied
4. Ground-truth PoC does not crash with the patch applied

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed, then create the locked project environment:

```bash
uv sync --locked
```

Download the benchmark data from HuggingFace:

```bash
export HF_TOKEN=...
uv run hf download sunblaze-ucb/cybergym-e2e --repo-type dataset --local-dir data/
```

Download the Docker images:

```bash
uv run python scripts/pull_images.py
```

Set ASLR entropy for sanitizer compatibility:
```bash
sudo sysctl -w vm.mmap_rnd_bits=28
```

## Running the Agent

### Single Task

```bash
# End-to-end mode
uv run python scripts/run_agent.py curl/arvo_66012 --mode e2e

# Patch-only mode
uv run python scripts/run_agent.py curl/arvo_66012 --mode patch-only
```

### Batch Run

Use the unified runner to select an agent and model preset:

```bash
# Run Qwen on the tasks in easy_instance.txt with one worker
./run_e2e.sh qwen easy_instance.txt 1

# Run Codex with Qwen on the same tasks
./run_e2e.sh codex-qwen easy_instance.txt 1

# Run Pi with Qwen on the same tasks
./run_e2e.sh pi-qwen easy_instance.txt 1

# Run Pi with GPT-5.4 through the OpenAI API
./run_e2e.sh pi-gpt54 instance_failed_qwen.txt 1

# Run Claude Opus 4.6 on instance.txt with two workers
./run_e2e.sh opus46 instance.txt 2

# Run Codex with GPT-5.4 and ChatGPT subscription auth
./run_e2e.sh codex-gpt54-sub succesful_instance.txt 1

# Run DeepSeek V4 Pro with OpenHands
export DEEPSEEK_API_KEY=...
./run_e2e.sh deepseek instance.txt 2
```

Available presets are `qwen`, `codex-qwen`, `pi-qwen`, `pi-gpt54`, `openhands-gpt55`, `codex-gpt55`, `codex-gpt54-sub`, `deepseek`, `opus45`, `opus46`, and `sonnet5`.
The `pi-qwen` preset installs Pi 0.84.1 in each task container and uses the OpenAI-compatible Chat Completions API.
It uses the built-in Pi coding tools and disables Pi extensions, skills, and prompt templates.
It still loads repository context files such as `AGENTS.md`.
The preset checks the model endpoint and sends a required tool-call request before it starts a batch.
Set `PI_THINKING_LEVEL` to change the default `medium` thinking level.
The `pi-qwen` and `pi-gpt54` presets both declare a 262,144-token context window and a 128,000-token maximum output for comparable experiments.
Set `PI_CONTEXT_WINDOW` or `PI_MAX_OUTPUT_TOKENS` to override these shared defaults explicitly.
Each Pi result summary records the effective provider, thinking level, context window, and maximum output.
The `pi-gpt54` preset uses Pi's built-in OpenAI provider and reads `OPENAI_API_KEY` from the environment.
The `codex-gpt54-sub` preset reads file-based ChatGPT credentials from `~/.codex/auth.json` by default.
Run `codex login` first, or set `CODEX_AUTH_FILE` to another file-based credential cache.
The subscription preset requires one worker so refreshed credentials can be persisted safely between tasks.
Treat the credential file like a password and never add it to the repository.
The DeepSeek preset uses `deepseek-v4-pro` and `https://api.deepseek.com` by default.
Set `DEEPSEEK_MODEL_ID` or `DEEPSEEK_BASE_URL` to override either value.
Run `./run_e2e.sh --help` for configuration options.
The task file defaults to `instance.txt`, and the worker count defaults to `2`.

### Trajectory Report

Generate a self-contained HTML visualization from one or more agent run logs or output directories:

```bash
python scripts/trajectory_report.py \
  agent_output_openhands_qwen_test \
  --output trajectory_report_qwen.html \
  --title "Qwen trajectory report"
```

The report shows high-level phases, validation results, idle gaps, notable termination events, and expandable log evidence.
Each run also has a detailed action browser with phase and event-kind filters, timestamps, source lines, previews, and expandable full details.
The report includes comparison, status filtering, and text search without external JavaScript or CSS dependencies.
Codex runs store live newline-delimited JSON in `trajectory/attempt_N.jsonl` and store diagnostic stderr separately in `trajectory/attempt_N.stderr.log`.
Pi runs use the same raw live JSONL and stderr paths.
Pi also stores the native session as `trajectory/attempt_N.session.jsonl`.
The current report parser does not normalize Pi events yet, so use these raw files when you inspect the first integration.

### PI Session Viewer

Start the local browser application to inspect native PI session files under `results_pi`:

```bash
uv run python scripts/trajectory_viewer.py
```

The viewer discovers `attempt_*.session.jsonl` files and groups them by task, model, run, and attempt.
It shows one timeline item for each physical JSONL line and provides direct line navigation, full-text search, filters, linked tool calls and results, raw JSON, and live updates.
You can also drag a session file into the browser or use **Open JSONL** to read it locally without uploading it to the server.

Use another results directory or port when needed:

```bash
uv run python scripts/trajectory_viewer.py \
  --root /path/to/results_pi \
  --port 9000 \
  --no-browser
```

The server binds to `127.0.0.1` by default and restricts file access to the configured results root.
Use `--host` only when you intend to expose the viewer on another network interface.

Use the same command with another output directory to inspect a different model run:

```bash
python scripts/trajectory_report.py \
  agent_output_openhands_opus_test \
  --output trajectory_report_opus45.html \
  --title "Claude Opus 4.5 trajectory report"
```

## Citation

If you use this project in your research, please cite:

```bibtex
@inproceedings{shi2026cybergyme2e,
  title={CyberGym-E2E: Scalable Real-World Benchmark for {AI} Agents' End-to-End Cybersecurity Capabilities},
  author={Shi, Tianneng and Rheem, Robin and Jiang, Dongwei and Wang, Mona and De La Riega, Francisco and Wang, Zhun and Jiang, Jingzhi and Cheung, Alexander and Tai, Sean and Cha, Jonah and Tu, Jianhong and Han, Gabriel and Wang, Chenguang and He, Jingxuan and Guo, Wenbo and Song, Dawn},
  booktitle={Proceedings of the 43rd International Conference on Machine Learning},
  year={2026},
  url={https://arxiv.org/abs/2606.04460},
}
```

## License

This project is licensed under the [Apache License 2.0](LICENSE).
