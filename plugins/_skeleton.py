"""LM-Gambit plugin skeleton — copy this file to start a new plugin.

    cp plugins/_skeleton.py plugins/my_plugin.py

Files starting with ``_`` are ignored by the loader, so this template never
runs. Rename it (no leading underscore) and it loads on the next server start.

Every hook below is OPTIONAL. Delete the ones you don't need — a plugin that
only defines ``grade`` is perfectly valid. Anything you leave undefined is
simply never called.

If a hook raises, LM-Gambit logs it and carries on. Your plugin stays loaded
and its other hooks keep firing, so a bug in one grader can't break a run.
"""

from plugin_api import (
    Action,
    Grade,
    Markdown,
    NavItem,
    Page,
    Panel,
    RunRecord,
    SlotPanel,
    Stat,
    StatRow,
    Table,
    TestRecord,
)

# --------------------------------------------------------------------------
# Metadata — all optional. NAME is what shows up in Settings → Plugins.
# --------------------------------------------------------------------------

NAME = "My Plugin"
VERSION = "1.0.0"
DESCRIPTION = "One line describing what this plugin does."
ENABLED = True  # flip to False to keep the file but stop loading it


def register() -> None:
    """One-time setup, called once when the plugin loads.

    Open a database, read a config file, check that a CLI tool you depend on
    exists. Raising here disables the plugin and shows the error in Settings.
    """


# --------------------------------------------------------------------------
# Grading — score an answer
# --------------------------------------------------------------------------


def grade(test: TestRecord):
    """Score one answer, or return None to abstain.

    Abstaining is normal and costs nothing: a grader that only understands
    SwiftUI questions should return None for everything else, and those
    questions simply won't count toward the average.

    This is never called for a question the provider failed on — there is no
    answer to judge. Use `on_test_complete` if you need to see failures too.

    You may return:
        None             abstain — this grader has no opinion
        0.0 – 1.0        a bare score
        True / False     shorthand for 1.0 / 0.0
        Grade(...)       a score plus a label and notes shown in the report

    `test` gives you:
        test.index                 1-based position in the run
        test.total                 how many questions the run covers
        test.title                 first line of the prompt
        test.filename              e.g. "test3.txt" — NOT unique across suites
        test.suite                 owning suite slug, e.g. "math-code"
        test.question_id           "<suite>/<file>" — the unique identifier
        test.prompt                the full prompt text sent to the model
        test.ok                    False if the provider errored
        test.response              the model's answer (None when ok is False)
        test.error                 the provider error (None when ok is True)
        test.metrics               raw provider metrics dict
        test.tokens_per_second     convenience accessors over metrics
        test.total_tokens
        test.time_to_first_token
    """
    # Only judge questions this plugin actually understands.
    if "swift" not in test.prompt.lower():
        return None

    has_code_block = "```" in test.response
    return Grade(
        score=1.0 if has_code_block else 0.3,
        label="has code" if has_code_block else "prose only",
        notes="Checked that the answer contains a fenced code block.",
    )


# --------------------------------------------------------------------------
# Run lifecycle — react to a run starting, progressing and finishing
# --------------------------------------------------------------------------


def on_run_start(run: RunRecord) -> None:
    """Fired once, before the first question is sent."""
    print(f"[my_plugin] starting {run.total} questions against {run.model_label}")


def on_test_complete(test: TestRecord) -> None:
    """Fired after each question, before the next one starts.

    This runs on the run's worker thread, so slow work here delays the next
    question. Keep it quick, or hand it off to a thread of your own.
    """


def on_run_complete(run: RunRecord) -> None:
    """Fired once when the run ends — including when cancelled or failed.

    Check `run.status`: "completed", "cancelled" or "failed". Useful for
    notifications, CSV logs, or copying `run.report_path` somewhere else.

        run.summary        {"average_tokens_per_second": ..., "passed": ...}
        run.overall_score  mean of graded questions, or None if nothing graded
        run.score_for(3)   score for question 3, or None
        run.tests          every TestRecord from the run
        run.report_path    Path to the generated markdown report
    """
    score = run.overall_score
    if score is not None:
        print(f"[my_plugin] {run.model_label} scored {score:.0%}")


# --------------------------------------------------------------------------
# Report — add your own markdown to the generated report
# --------------------------------------------------------------------------


def report_sections(run: RunRecord):
    """Return extra markdown appended to the report, or None to add nothing.

    Return either a markdown string, or a list of (heading, body) pairs.
    Headings should start at `##` to sit alongside the built-in sections.
    """
    slowest = min(
        (t for t in run.tests if t.ok and t.tokens_per_second),
        key=lambda t: t.tokens_per_second,
        default=None,
    )
    if slowest is None:
        return None

    return [
        (
            "## Slowest question",
            f"`{slowest.filename}` — {slowest.title}\n\n"
            f"* **Throughput:** {slowest.tokens_per_second} tok/s",
        )
    ]


# --------------------------------------------------------------------------
# HTTP — expose your own API endpoints
# --------------------------------------------------------------------------


def register_routes(router) -> None:
    """Add FastAPI routes, mounted under /api/plugins/<filename-without-.py>.

    For a plugin saved as `plugins/my_plugin.py`, the route below is served at
    /api/plugins/my_plugin/ping. Routes are registered when the server starts,
    so adding or changing them requires a restart.

    Careful: reloading does not rebind routes. These handlers close over the
    module object that existed at startup, so after a plugin reload the new
    module handles grade() while these routes still read the old module's
    globals — serving stale state with no error to warn you. Restart the
    server after editing a plugin that defines this hook.
    """

    @router.get("/ping")
    async def ping() -> dict:
        return {"plugin": NAME, "version": VERSION, "status": "ok"}

    @router.get("/stats")
    async def stats() -> dict:
        """Shape a StatRow(source=...) expects back."""
        return {
            "stats": [
                {"label": "Checked", "value": 12, "hint": "this run", "tone": "good"},
                {"label": "Problems", "value": 0, "hint": "none found", "tone": "default"},
            ]
        }

    @router.post("/reset")
    async def reset() -> dict:
        """`message` raises a toast; `refresh` re-fetches sibling blocks."""
        return {"message": "Reset done.", "refresh": True}


# --------------------------------------------------------------------------
# UI — add pages, nav entries and panels
# --------------------------------------------------------------------------


def ui_contributions():
    """Describe interface for the app to render. Return a list, or None.

    You describe UI as *data* — never as code — so a plugin never ships
    JavaScript and the frontend is never rebuilt to install one.

    Blocks:
        StatRow(stats=[Stat(...)])   a row of headline numbers
        Table(columns=[], rows=[])   a column-headed table
        Markdown(text="...")         rendered markdown
        Action(label=, post=)        a button that POSTs to one of your routes
        Panel(title=, blocks=[])     a titled card wrapping other blocks

    Every data block accepts either inline values or `source="/api/plugins/..."`,
    which it fetches and re-fetches when an Action returns {"refresh": True}.

    Surfaces:
        NavItem   an entry in the left rail
        Page      a full page of your own
        SlotPanel a panel injected into a built-in page. Valid slots are
                  run.aside, reports.aside, suite.aside and settings.section

    Paths are namespaced under /x/<slug>/, so "/tool" below is served at
    /x/my_plugin/tool and cannot collide with another plugin or a core route.

    Full reference, including the icon names, lives in the app at /docs.
    """
    base = "/api/plugins/my_plugin"

    return [
        NavItem(label="My tool", path="/tool", icon="wrench", hint="What it does", order=50),
        Page(
            path="/tool",
            title="My tool",
            subtitle="One line about what this page shows.",
            blocks=[
                # Live numbers, re-fetched from your own endpoint.
                StatRow(source=f"{base}/stats"),
                Panel(
                    title="Details",
                    blocks=[
                        Table(
                            columns=["Question", "Result"],
                            rows=[[1, "ok"], [2, "ok"]],
                            empty="Run the suite to populate this.",
                        ),
                        Action(
                            label="Reset",
                            post=f"{base}/reset",
                            style="ghost",
                            icon="refresh",
                            confirm="Discard everything collected so far?",
                        ),
                    ],
                ),
                Panel(title="Notes", blocks=[Markdown(text="Supports **markdown**.")]),
            ],
        ),
        # A compact summary alongside the live run feed.
        SlotPanel(
            slot="run.aside",
            order=50,
            panel=Panel(
                title="My tool",
                blocks=[StatRow(stats=[Stat(label="Ready", value="yes", tone="good")])],
            ),
        ),
    ]
