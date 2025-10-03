


# LM-Gambit v1.0.0: Automated LLM Diagnostic Suite


**Version 1.0.0**

LM-Gambit is a modular, extensible framework for benchmarking and analyzing local or remote Large Language Models (LLMs). It supports both a command-line interface (CLI) and a Tkinter-based GUI, enabling rapid, repeatable evaluation of LLMs using customizable prompt suites.

---

## Features

- **Automated Testing:** Run a suite of prompt-based diagnostics against any supported LLM provider.
- **Provider System:** Out-of-the-box support for LM Studio (API) and a native Local Engine (hardware-optimized, supports Apple Silicon, CUDA, ROCm, CPU).
- **Extensible:** Add new providers or engine runtimes with minimal code changes.
- **GUI & CLI:** Choose between a full-featured GUI or a fast CLI for scripting and automation.
- **Customizable Reports:** Generates detailed Markdown reports with performance metrics and qualitative analysis sections.
- **Prompt Management:** Prompts are simple `.txt` files, editable in the GUI or any text editor.

---

## Installation

**Requirements:**
- Python 3.10+
- macOS, Linux, or Windows (Apple Silicon, NVIDIA, AMD, or CPU-only supported)

**Install dependencies:**

```bash
python -m pip install -r requirements.txt
```

**(Optional)** For Apple Silicon (MLX), ensure `mlx-lm` is installed. For CUDA/ROCm, ensure your system drivers are set up.

---

## Quick Start

### CLI Usage

Run all tests with the default provider/model:

```bash
python auto-test.py
```

**Options:**
- `-h, --help` — Show usage instructions
- `-p <provider>` — Select provider (e.g., "Local Engine", "LM Studio")
- `-m <model>` — Select model by ID or filename
- `-l, --list` — List available providers or models
- `-t <test>` — (Reserved) Specify a test suite

Example:

```bash
python auto-test.py -p "Local Engine" -m Qwen3-Coder-30B.gguf
```

Reports are saved to `results/automated_report_<model>.md`.

### GUI Usage

```bash
python index.py
```

**GUI Features:**
- Provider/model dropdowns with auto-discovery
- Adjustable sampling temperature
- Run, refresh, open prompts/results, and view latest report
- Live log of test progress
- Settings dialog for managing model search paths

---

## Project Structure

- `.core/` — Core logic, providers, engine loader, reporting, templates
  - `providers/` — Provider adapters (LM Studio, Local Engine, etc.)
  - `.engine/` — Hardware-specific runtime implementations (MLX, CUDA, ROCm, CPU)
  - `runner.py` — Orchestrates test runs, progress, and reporting
  - `reporting.py` — Markdown report generation, code-fence hygiene
  - `prompts.py` — Loads and parses prompt files from `tests/`
  - `templates/test-block.md` — Customizable template for each test result
- `models/` — Drop-in directory for `.gguf` or MLX-compatible weights (auto-discovered)
- `tests/` — One prompt per `.txt` file (edit or add your own)
- `results/` — Markdown reports generated after each run
- `auto-test.py` — CLI entrypoint
- `index.py` — Tkinter GUI entrypoint

---

## How the Core Engine Works

1. **Provider Selection:**
   - Providers (e.g., LM Studio, Local Engine) are registered in `.core/providers/`.
   - Each provider implements `list_models()` and `run_prompt()`.
   - The Local Engine auto-selects the best runtime for your hardware (MLX, CUDA, ROCm, or CPU fallback).

2. **Prompt Loading:**
   - Prompts are loaded from the `tests/` directory (one `.txt` file per test).
   - Each prompt file's first non-empty line is used as the test title.

3. **Test Execution:**
   - For each prompt, the selected provider/model is used to generate a response.
   - Results are streamed to the CLI or GUI with live progress updates.

4. **Reporting:**
   - Each test result is rendered using a Markdown template (`.core/templates/test-block.md`).
   - Performance metrics (tokens/sec, time to first token, etc.) are included.
   - A summary and qualitative analysis section are generated at the top of the report.

---

## Configuration & Environment Variables

You can customize behavior via environment variables:

| Variable                | Purpose                                                      |
|-------------------------|--------------------------------------------------------------|
| `LM_STUDIO_BASE_URL`    | Override LM Studio API endpoint (default: http://localhost:1234) |
| `AUTO_TEST_TEMPERATURE` | Default sampling temperature for test runs                   |
| `AUTO_TEST_PROVIDER`    | Default provider for CLI runs                                |
| `LOCAL_LLM_PATHS`       | `:`-separated list of extra directories for `.gguf` models   |

Model search paths can also be managed via the GUI settings dialog (persisted in `.core/user_settings.json`).

---


## Extending LM-Gambit

**Add a new provider:**
1. Create a new class in `.core/providers/` inheriting from `Provider` (see `base.py`).
2. Implement `list_models()` and `run_prompt()`.
3. Register your provider in `.core/providers/__init__.py`.

**Add a new engine runtime:**
1. Add a new Python file under `.core/.engine/.<architecture>/<version>.py`.
2. Implement an `EngineRuntime` class inheriting from `BaseRuntime`.
3. The engine loader will auto-detect and use your runtime if the hardware matches.

---


## Customizing Prompts & Reports in LM-Gambit

- Add/edit prompt `.txt` files in `tests/` (first non-empty line is the title).
- Edit `.core/templates/test-block.md` to change the report format.

---

## Troubleshooting

- **No models found?**
  - Ensure your `.gguf` files are in `models/` or listed in `LOCAL_LLM_PATHS`.
  - For LM Studio, ensure the app is running and the API is enabled.
- **Engine errors?**
  - Check your hardware drivers and Python dependencies.
- **GUI not launching?**
  - Ensure `tkinter` is installed and available in your Python environment.

---


## License

MIT License. See `LICENSE` for details.

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


## Extending Providers in LM-Gambit

Provider adapters live under `.core/providers/` and are registered in `.core/providers/__init__.py`. Each provider implements `list_models` and `run_prompt` to integrate with the runner and GUI, while hardware-specific runtimes reside under `.core/.engine/`.
