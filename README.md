# LM-Gambit v2.0.0 — Automated LLM Diagnostic Suite

LM-Gambit benchmarks local or remote Large Language Models against a suite of prompts you
author yourself. It runs each question one at a time, records throughput and latency for
every answer, and writes a markdown report you can grade.

Version 2.0.0 replaces the Tkinter GUI with a React web interface served by a FastAPI
backend. The diagnostic engine under `.core/` is unchanged — the CLI, providers, hardware
runtimes and report format all behave exactly as before.

---

## Install

**Requirements**

- Python 3.10+ (3.11 recommended)
- Node.js 20+ and npm (only to build the interface)
- macOS, Linux or Windows — Apple Silicon, NVIDIA, AMD or CPU-only

```bash
python -m pip install -r requirements.txt
cd web && npm install && npm run build && cd ..
```

## Run

```bash
python app.py
```

That serves the API and the compiled interface from one origin and opens
`http://localhost:8765` in your browser.

| Flag | Purpose |
|---|---|
| `--port <n>` | Serve on a specific port (default 8765; the next free port is used if taken) |
| `--host <addr>` | Bind a different interface (default `127.0.0.1`) |
| `--no-browser` | Do not open a browser window |
| `--reload` | Auto-reload on Python changes |

---

## The interface

| View | What it does |
|---|---|
| **Run** | Pick a provider, model and temperature; choose all or a subset of questions; watch results stream in per question with live throughput, token counts and TTFT. Cancel between questions — the partial report is still finalized. |
| **Suite** | The question editor. One text box per question, with add, duplicate, reorder and delete. |
| **Reports** | Every saved report, with a per-question throughput chart, a metrics table and the full rendered markdown. |
| **Playground** | Send a single prompt without touching the suite or writing a report. |
| **Settings** | Default provider and temperature, model search paths, engine and folder information, and which plugins loaded. |

A run keeps streaming while you browse other views, and reattaches if you reload the page
mid-run.

---

## Writing questions

Questions live in `tests/` as one `.txt` file per prompt. The **entire file** is sent to the
model, and its **first non-empty line** doubles as the title in reports — so lead with the
task:

```
Write a Swift function that solves the FizzBuzz problem.

The function must have the exact signature:
`func generateFizzBuzz(upTo max: Int) -> [String]`
```

Saving from the Suite Builder rewrites the folder as `test1.txt … testN.txt` in the order
shown, so the web interface and `auto-test.py` always run the same suite in the same order.
You can still edit the `.txt` files by hand.

---

## Plugins

Drop a `.py` file into `plugins/` and it loads at startup. Start from the
skeleton, which documents every hook:

```bash
cp plugins/_skeleton.py plugins/my_plugin.py
```

Files beginning with `_` are ignored, so the skeleton itself never runs. A
plugin directory with an `__init__.py` works too, if you want to split one
across files.

### Hooks

Every hook is optional — define only what you need.

| Hook | When | Purpose |
|---|---|---|
| `grade(test)` | after each answer | Score it. Return `0.0`–`1.0`, `True`/`False`, a `Grade`, or `None` to abstain |
| `on_run_start(run)` | before the first question | Set up, announce, start a timer |
| `on_test_complete(test)` | after each question | Log, stream elsewhere, react to failures |
| `on_run_complete(run)` | when the run ends | Notify, export, archive — fires on cancel and failure too |
| `report_sections(run)` | after the report is written | Return extra markdown to append |
| `register_routes(router)` | at server start | Add endpoints under `/api/plugins/<slug>` |
| `register()` | once, at load | One-time setup; raising here disables the plugin |

Plugins import only from `plugin_api`, which exposes `TestRecord`, `RunRecord`,
`Grade` and `GradeEntry` as plain frozen dataclasses. They never touch engine or
server internals.

### A minimal grader

```python
# plugins/actor_check.py
from plugin_api import Grade

NAME = "Actor check"
DESCRIPTION = "Verifies concurrency questions actually use an actor."


def grade(test):
    if "thread-safe" not in test.prompt.lower():
        return None                      # abstain — not my kind of question
    used_actor = "actor " in (test.response or "")
    return Grade(
        score=1.0 if used_actor else 0.0,
        label="actor" if used_actor else "no actor",
    )
```

### How grading behaves

- **Abstaining is free.** Returning `None` excludes the question from that
  grader entirely; it never counts as a zero.
- **A question's score is the mean** of every grader that scored it. The run's
  score is the mean of those per-question scores.
- **Failed questions are never graded** — there is no answer to judge. Use
  `on_test_complete` if you want to see failures.
- **Grades replace the report's "grade this by hand" placeholder** with a table
  of scores, a letter grade, and each grader's notes. With no graders installed,
  the report is unchanged from v1.
- Scores appear live in the run feed and in the Reports table.

### Failure isolation

A plugin that raises is logged with its slug and skipped for that call only —
it stays loaded and its other hooks keep firing. A plugin that fails to import
is listed in Settings → Plugins with the error, and everything else still runs.
A plugin can never fail a run or stop the server.

### Reloading

**Settings → Plugins → Reload** re-scans the directory, picking up new graders
and lifecycle hooks without a restart. Plugins that add HTTP routes need a full
restart, since routes are bound when the server starts.

Set `ENABLED = False` in a plugin to keep the file but stop loading it.

---

## CLI

The CLI is unchanged and does not require the frontend to be built.

```bash
python auto-test.py -p "Local Engine" -m Qwen3-Coder-30B.gguf
```

| Flag | Purpose |
|---|---|
| `-h, --help` | Usage instructions |
| `-p <provider>` | Provider to use (e.g. `"Local Engine"`, `"LM Studio"`) |
| `-m <model>` | Model by id or filename |
| `-l, --list` | List providers, or models when combined with `-p` |

Reports are written to `results/automated_report_<model>.md`.

---

## Project structure

```
.core/                  Diagnostic engine (unchanged)
  providers/            Provider adapters (LM Studio, Local Engine)
  .engine/              Hardware runtimes (MLX, CUDA, ROCm, CPU)
  runner.py             Orchestrates a run and its report
  reporting.py          Markdown report generation
  prompts.py            Loads prompts from tests/
  templates/            test-block.md — the per-question report template
server/                 FastAPI backend wrapping the engine
  core_bridge.py        Import shim for the hidden .core package
  api.py                REST endpoints
  run_manager.py        Background runs + server-sent-event streaming
  suite.py              Reads and writes tests/
  plugins.py            Bridge between server internals and the plugin API
plugins/                Drop-in plugins — _skeleton.py is the starter template
plugin_api.py           Stable types plugins import
plugin_system.py        Plugin discovery and hook dispatch
web/                    React + TypeScript interface (Vite)
models/                 Drop .gguf or MLX weights here (auto-discovered)
tests/                  One prompt per .txt file
results/                Generated markdown reports
app.py                  Web entrypoint
auto-test.py            CLI entrypoint
```

---

## How a run works

1. **Provider selection** — providers are registered in `.core/providers/`, each implementing
   `list_models()` and `run_prompt()`. The Local Engine picks the best runtime for your
   hardware: MLX on Apple Silicon, CUDA on NVIDIA, ROCm on AMD, or a `llama-cpp-python` CPU
   fallback.
2. **Prompt loading** — every `.txt` in `tests/`, in natural filename order.
3. **Execution** — one prompt at a time against the selected model. The backend streams each
   result to the browser as it lands, so nothing is buffered until the end.
4. **Reporting** — each result is rendered through `.core/templates/test-block.md`, with a
   performance summary written at the top once the run finishes.

---

## API

The backend is a normal REST API — interactive docs at `http://localhost:8765/api/docs`.

| Endpoint | Purpose |
|---|---|
| `GET /api/providers` · `GET /api/providers/{name}/models` | Discovery |
| `GET /api/tests` · `PUT /api/tests` | Read and replace the suite |
| `POST /api/runs` · `GET /api/runs/{id}/events` · `POST /api/runs/{id}/cancel` | Start, stream, cancel |
| `GET /api/reports` · `GET /api/reports/{name}` | Saved reports |
| `POST /api/playground` | One-off prompt |
| `GET /api/settings` · `PUT /api/settings` | Preferences |
| `GET /api/plugins` · `POST /api/plugins/reload` | Installed plugins |
| `/api/plugins/<slug>/…` | Whatever a plugin's `register_routes` defines |

Only one run executes at a time — the local engine loads weights into memory, so overlapping
runs would compete for RAM and produce meaningless throughput numbers.

---

## Configuration

| Variable | Purpose |
|---|---|
| `LM_STUDIO_BASE_URL` | LM Studio endpoint (default `http://localhost:1234`) |
| `AUTO_TEST_TEMPERATURE` | Default sampling temperature |
| `AUTO_TEST_PROVIDER` | Default provider for CLI runs |
| `LOCAL_LLM_PATHS` | `os.pathsep`-separated extra directories to scan for `.gguf` weights |

Settings changed in the interface persist to `.core/user_settings.json` and are shared with
the CLI. Common LM Studio locations (`~/.lmstudio`, `~/.lmstudio/models`,
`~/Library/Application Support/lm-studio/models`) are scanned by default.

---

## Frontend development

```bash
python app.py --no-browser     # terminal 1 — API on :8765
cd web && npm run dev          # terminal 2 — UI on :5173 with hot reload
```

Vite proxies `/api` (including the event stream) through to the Python server, so both run
from one origin.

---

## Extending

**A new provider** — add a class in `.core/providers/` inheriting from `Provider`, implement
`list_models()` and `run_prompt()`, and register it in `.core/providers/__init__.py`. It
appears in the interface automatically.

**A new engine runtime** — add `.core/.engine/.<architecture>/<version>.py` defining an
`EngineRuntime` class that inherits from `BaseRuntime`. The loader picks it up when the
hardware matches.

---

## Troubleshooting

**"Frontend not built"** — run `cd web && npm install && npm run build`. The API and CLI work
without it.

**No models found** — put `.gguf` files in `models/`, add a path under Settings, or set
`LOCAL_LLM_PATHS`. For LM Studio, make sure the app is running with its API enabled.

**Port already in use** — `app.py` automatically tries the next 20 ports, or pass `--port`.

**Engine errors** — check Settings → Engine for the detected runtime, and confirm your
hardware drivers and Python dependencies are installed.

---

## License

MIT License. See `LICENSE` for details.
