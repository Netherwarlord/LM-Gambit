# LLM Automated Test Suite

This project automates a battery of diagnostic prompts against local or remote language models via a modular core runner and an optional GUI.

## Prerequisites

- Python 3.10 or newer (tkinter included with the standard library on macOS/Linux; install `python3-tk` on Debian-based systems if needed).
- Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Project Layout

- `.core/` – shared logic modules, templates, engines, and transient workspace used by both CLI and GUI.
  - `config.py` – path/setting helpers.
  - `prompts.py` – prompt discovery from `tests/`.
  - `providers/` – provider adapters (LM Studio and the native Local Engine runtime).
  - `reporting.py` – markdown templating, code-fence hygiene, report summaries.
  - `runner.py` – orchestrates full test runs with progress callbacks.
  - `engine_loader.py` – detects the host platform/GPU and loads the appropriate runtime.
  - `.engine/.<architecture>/<version>.py` – runtime implementations per hardware family (Apple Silicon ↦ MLX, CUDA ↦ llama.cpp, ROCm ↦ llama.cpp, CPU fallback).
  - `.temp/` – ephemeral staging for rendered blocks.
  - `templates/test-block.md` – markdown template for each test result.
- `models/` – drop-in directory for local `.gguf` (and MLX-compatible) weights discovered by the Local Engine provider.
- `tests/` – one prompt per `.txt` file (editable via the GUI or any editor).
- `results/` – generated markdown reports.
- `auto-test.py` – CLI entrypoint that runs the default provider/model.
- `index.py` – Tkinter GUI for provider/model selection, running tests, and opening prompts/results.

## Running the CLI

```bash
python auto-test.py
```

The CLI selects the first available model for the default provider (LM Studio by default) and streams progress to stdout. Reports are saved in `results/automated_report_<model>.md`.

To switch to the Local Engine runtime, set `AUTO_TEST_PROVIDER="Local Engine"` (or choose it in the GUI) and ensure your models are available in the `models/` directory or any path listed in `LOCAL_LLM_PATHS`.

## Using the GUI

```bash
python index.py
```

GUI features:

- Provider dropdown with automatic model discovery.
- Model dropdown populated per provider.
- Adjustable sampling temperature.
- Buttons to run tests, refresh models, open the `tests/` folder, open the `results/` folder, and open the latest report.
- Live log of test progress and completion status.
- Settings menu → “Configure Model Paths…” to manage additional folders scanned by the Local Engine provider (persisted in `.core/user_settings.json`).

## Configuration

Environment variables:

- `LM_STUDIO_BASE_URL` – override the default `http://localhost:1234` endpoint for the LM Studio provider.
- `AUTO_TEST_TEMPERATURE` – default sampling temperature for test runs.
- `AUTO_TEST_PROVIDER` – default provider name for CLI runs.
- `LOCAL_LLM_PATHS` – optional `os.pathsep`-separated list of extra directories to scan for `.gguf` weights.

Templates can be customized by editing `.core/templates/test-block.md`.

### Local Engine provider

- Place `.gguf` (llama.cpp) weights inside `models/` or add extra directories via the GUI settings dialog / `LOCAL_LLM_PATHS` environment variable.
- Paths include common defaults (for example `~/.lmstudio`, `~/.lmstudio/models`, or `~/Library/Application Support/lm-studio/models` on macOS) so LM Studio downloads are discovered automatically.
- The engine loader automatically selects the best runtime for your hardware: MLX on Apple Silicon, CUDA on NVIDIA GPUs, ROCm on AMD GPUs, or a CPU fallback via `llama-cpp-python`.
- Settings are saved in `.core/user_settings.json`, keeping CLI and GUI runs in sync.

## Extending Providers

Provider adapters live under `.core/providers/` and are registered in `.core/providers/__init__.py`. Each provider implements `list_models` and `run_prompt` to integrate with the runner and GUI, while hardware-specific runtimes reside under `.core/.engine/`.
