# LM-Gambit v2.0.0 — Automated LLM Diagnostic Suite

LM-Gambit benchmarks local or remote Large Language Models against a suite of prompts you
author yourself. It runs each question one at a time, records throughput and latency for
every answer, and writes a markdown report you can grade.

## What 2.0.0 brings over 1.0.0

The Tkinter GUI is replaced by a React web interface served by a FastAPI backend.
Beyond the interface:

- **Named suites.** Questions live in five read-only built-in suites rather than one
  flat directory, and a run can draw from several at once, or from a subset of any.
  Custom suites are yours to edit; built-ins stay a stable baseline for comparison.
- **Three graders.** Two measure form — whether an answer did what it was told — and
  `answer_key` measures whether it was actually right, for the questions with an
  unambiguous answer.
- **A plugin framework.** Plugins add nav entries, pages and panels by describing them
  as data, so installing one never requires rebuilding the frontend.
- **Run history.** Reports are named `<model>__<timestamp>__<scope>__<n>q.md`, so runs
  no longer overwrite each other and each file records what it covered.

The `auto-test.py` CLI still drives the same engine the web interface does.

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
| **Testing Suites** | Browse every suite. Built-ins are read-only; duplicate one to get an editable custom copy, then add, reorder and delete questions in it. |
| **Reports** | Every saved report, with a per-question throughput chart, a metrics table and the full rendered markdown. |
| **Playground** | Send a single prompt without touching the suite or writing a report. |
| **Settings** | Default provider and temperature, model search paths, engine and folder information, and which plugins loaded. |

A run keeps streaming while you browse other views, and reattaches if you reload the page
mid-run.

---

## Writing questions

Questions are grouped into named **suites**, in two tiers:

```
.core/suites/<slug>/     built-in, ships with the app, READ-ONLY at runtime
    suite.json           {name, description, order}
    test1.txt ...
tests/<slug>/            custom, full CRUD, yours
```

Five built-in suites ship enabled — `language`, `reasoning-logic`, `math-code`,
`context-knowledge` and `safety` — 26 questions in total. They cannot be renamed, deleted
or edited: the API returns 409, not just a disabled button. That keeps them a stable
baseline for comparing models over time. **Duplicate** one to get an editable copy.

One `.txt` file is one prompt. The **entire file** is sent to the model, and its **first
non-empty line** doubles as the title in reports — so lead with the task:

```
Analyze the sentiment of the following customer review.

Review:
"I ordered the noise-cancelling headphones after ..."
```

Saving a custom suite rewrites its folder as `test1.txt … testN.txt` in the order shown, so
the web interface and `auto-test.py` always agree.

### Question IDs

`filename` is unique only *within* a suite — every suite has a `test1.txt`. A question is
identified by its qualified **`<suite>/<file>`** ID, and nothing anywhere keys off the bare
filename. This matters more than it looks: graders derive their whole rubric from the prompt
text, so handing one the wrong question's prompt produces a confident, plausible, entirely
wrong score with no error to notice.

### Running a subset

```bash
python auto-test.py --suites                       # list what is available
python auto-test.py -m <model> -t math-code        # one suite
python auto-test.py -m <model> -t language,safety  # several
python auto-test.py -m <model>                     # every BUILT-IN suite
```

A bare run covers the built-ins only, never custom suites — so it means the same thing on
every machine rather than depending on local scratch work. The Run page offers the same
choice, expandable to individual questions within each suite.

---

## Plugins

> **Full reference lives in the app at `/docs`** — hooks, the UI contribution
> vocabulary, worked examples, and a live view of what is installed. The
> summary below is enough to get started.

A plugin can grade answers, add sections to reports, expose HTTP endpoints, and
contribute interface — nav entries, whole pages, and panels on the built-in
views — without shipping a line of JavaScript or rebuilding the frontend.

Three ship enabled:

| Plugin | What it does |
| --- | --- |
| `response_checks` | Grades any answer against the constraints its own prompt states |
| `code_lint` | Static analysis of code blocks in answers. Never executes them |
| `answer_key` | Checks answers against known-correct content, where one exists |

The first two measure **form** — whether an answer did what it was told.
`answer_key` is the only one that asks whether it was **right**, and it only
covers questions with an unambiguous answer (16 of 26). The rest abstain, so a
high score reads as "correct where checkable, well-formed elsewhere".

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
| `ui_contributions()` | when the UI loads | Nav entries, pages and panels — see `/docs` |
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

### Contributing UI

Plugins describe interface as data and the app renders it, so installing one
never requires rebuilding the bundle:

```python
from plugin_api import Action, NavItem, Page, Panel, StatRow, Table

def ui_contributions():
    base = "/api/plugins/my_plugin"
    return [
        NavItem(label="My tool", path="/tool", icon="wrench", order=50),
        Page(path="/tool", title="My tool", blocks=[
            StatRow(source=f"{base}/stats"),
            Panel(title="Results", blocks=[
                Table(source=f"{base}/rows"),
                Action(label="Clear", post=f"{base}/clear", style="ghost"),
            ]),
        ]),
    ]
```

Blocks are `StatRow`, `Table`, `Markdown`, `Action` and `Panel`; surfaces are
`NavItem`, `Page` and `SlotPanel`. Any block may take inline data or a `source`
URL it fetches live. Paths are namespaced under `/x/<slug>/`, so plugins cannot
collide with each other or shadow a built-in route. Full vocabulary at `/docs`.

### The bundled graders

`plugins/answer_key.py` compares answers against `answers.json` files that sit
beside the questions, using `must_contain`, `must_contain_any`, `numbers` and
`regex` matchers scored as the fraction satisfied. No key means abstain.

Two rules govern what gets a key, both learned the hard way:

- **Verify the value before writing it.** `tests_py/test_answer_values.py`
  recomputes every numeric key from scratch. It exists because one key was
  recorded backwards, and shipping it would have failed every correct answer.
- **Prefer checks that can only pass wrongly, never fail wrongly.** No key uses
  a negative matcher: this suite is full of questions that require naming the
  wrong answer — *"show why it is not 50%"*, *"quote the exact text"* — so a
  banned substring penalises correct work.

`plugins/code_lint.py` statically analyses code blocks in answers — syntax,
compilation, the signature the prompt demanded, stub bodies, undefined names,
unused imports and more. It **never executes model output**; every check is
parse-level, so a broken or hostile snippet cannot affect the grading machine.
It abstains on answers with no code.

`plugins/response_checks.py` ships enabled. It grades **any** answer — prose,
maths, JSON, translation, code — by deriving a rubric from the prompt itself
rather than from a hard-coded per-question key. Nothing in it is domain-specific.

It reads the prompt for constraints the answer can be measured against, then
scores each as a fraction rather than a pass/fail:

| Check | Fires when the prompt… |
| --- | --- |
| `structure/json` | asks for valid JSON — the answer must parse |
| `structure/table` | asks for a table |
| `structure/code` | names a language or a `def`, or forbids a code fence |
| `coverage/enumerated` | lists numbered deliverables or `PART`/`STAGE` blocks |
| `coverage/keyterms` | backticks a symbol or quotes a key/heading to emit |
| `constraint/forbidden` | bans a symbol ("do not use `INIntent`") |
| `constraint/length` | states one unambiguous word budget |
| `behaviour/abstention` | unconditionally requires a refusal or an "I don't know" |
| `quality/degeneration` | always — catches looping, truncation, empty output |
| `quality/substance` | always — catches one-line non-answers |

Only applicable checks count toward the score, so a prompt that never mentions
JSON is never scored on JSON. Three deliberate conservatisms keep it from
punishing correct work:

- A word budget is enforced **only when it unambiguously covers the whole
  answer**. A prompt asking for two summaries of different lengths skips the
  check rather than failing it.
- A **conditional** demand ("if the constraints are contradictory, say so") is
  never scored — whether the condition holds is exactly what the grader cannot
  determine. Only unconditional demands ("do not guess") count.
- **Multi-word quoted spans are ignored** as requirements. They are nearly
  always material being discussed — a line of the source text, or a manipulative
  phrase the answer is asked to quote back — not something to reproduce.

The report gains a `Compliance by check` table showing which dimensions the
model struggled with across the whole run, and a list of questions with unmet
constraints. A low score means the answer did not do what it was told, which is
not the same as being wrong — read the answer before treating it as a failure.

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

The CLI does not require the frontend to be built.

```bash
python auto-test.py -p "Local Engine" -m gemma-4-E2B-it-Q8_0 -t math-code
```

| Flag | Purpose |
|---|---|
| `-h, --help` | Usage instructions |
| `-p <provider>` | Provider to use (e.g. `"Local Engine"`, `"LM Studio"`) |
| `-m <model>` | Model by id or filename |
| `-l, --list` | List providers, or models when combined with `-p` |
| `-s, --suites` | List available suites |
| `-t, --test <slug>` | Suites to run — repeatable or comma-separated. Omit for every built-in |

Reports are written to `results/automated_report_<model>.md`.

---

## Tests

```bash
python tests_py/run_all.py     # 227 assertions
cd web && npm test             # 29 assertions
```

Both run in CI on every push — see [`.github/workflows/tests.yml`](.github/workflows/tests.yml).

The Python tests need only `requirements-ci.txt`, which omits
`llama-cpp-python`: it wants a C compiler, dominates install time, and nothing
in the test suite touches local inference. `tests_py/test_api.py` additionally
needs a running server and skips cleanly without one, so the rest stay useful
offline. Details in [`tests_py/README.md`](tests_py/README.md).

---

## Project structure

```
.core/                  Diagnostic engine (unchanged)
  providers/            Provider adapters (LM Studio, Local Engine)
  .engine/              Hardware runtimes (MLX, CUDA, ROCm, CPU)
  runner.py             Orchestrates a run and its report
  reporting.py          Markdown report generation
  prompts.py            Facade over suites.py (kept for the runner)
  suites.py             Named suites: discovery, loading, CRUD
  templates/            test-block.md — the per-question report template
server/                 FastAPI backend wrapping the engine
  core_bridge.py        Import shim for the hidden .core package
  api.py                REST endpoints
  run_manager.py        Background runs + server-sent-event streaming
  suite.py              Server layer over the core suite module
  plugins.py            Bridge between server internals and the plugin API
plugins/                Drop-in plugins — _skeleton.py is the starter template
plugin_api.py           Stable types plugins import
plugin_system.py        Plugin discovery and hook dispatch
tests_py/               Python tests — python tests_py/run_all.py
web/                    React + TypeScript interface (Vite)
models/                 Drop .gguf or MLX weights here (auto-discovered)
.core/suites/<slug>/    Built-in suites, read-only
tests/<slug>/           Custom suites, one prompt per .txt
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
2. **Prompt loading** — the selected suites, each in natural filename order, tagged with a qualified `<suite>/<file>` ID.
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
| `GET /api/suites` · `GET /api/suites/{slug}` | List suites, read one with its questions |
| `POST /api/suites` · `PUT /api/suites/{slug}` · `DELETE` | Create, rename, remove a custom suite (409 on built-ins) |
| `PUT /api/suites/{slug}/tests` | Replace a custom suite's questions (409 on built-ins) |
| `POST /api/suites/{slug}/duplicate` | Clone any suite into an editable custom one |
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
