"""Background execution of diagnostic runs with server-sent-event streaming.

The engine's ``run_suite`` is synchronous and blocking, so each run executes on
a worker thread. Progress is pushed back onto the asyncio loop through
``loop.call_soon_threadsafe`` and fanned out to any connected SSE subscribers.

Every event is also retained on the run, so a client that connects late (or
reconnects after a dropped connection) replays the full history before it
starts following the live feed.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from .core_bridge import (
    RESULTS_DIR,
    TemplateNotFoundError,
    TestRunError,
    append_sections,
    finalize_report_summary,
    replace_analysis_section,
    run_suite,
    sanitize_model_name,
)
from .plugins import (
    GradeEntry,
    build_run_record,
    build_test_record,
    collect_report_sections,
    get_plugin_manager,
    render_grade_section,
)

TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled"}
MAX_RUN_HISTORY = 20
KEEPALIVE_SECONDS = 15.0


class RunCancelled(Exception):
    """Raised inside the engine's progress callback to unwind a running suite.

    The engine has no cancellation hook of its own. Raising from the callback
    stops the loop cleanly between tests -- results already written to the
    report are kept and the summary is finalized with whatever completed.
    """


@dataclass
class TestOutcome:
    index: int
    title: str
    filename: str
    status: str
    elapsed: float
    response: Optional[str] = None
    error: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    grades: List[Dict[str, Any]] = field(default_factory=list)
    suite: str = ""

    @property
    def question_id(self) -> str:
        """Unique across suites. ``filename`` alone is not — see RunState."""
        return f"{self.suite}/{self.filename}" if self.suite else self.filename

    @property
    def score(self) -> Optional[float]:
        if not self.grades:
            return None
        return sum(g["score"] for g in self.grades) / len(self.grades)

    def as_event(self, total: int) -> Dict[str, Any]:
        return {
            "type": "test.completed",
            "index": self.index,
            "total": total,
            "title": self.title,
            "filename": self.filename,
            "suite": self.suite,
            "question_id": self.question_id,
            "status": self.status,
            "elapsed": round(self.elapsed, 2),
            "response": self.response,
            "error": self.error,
            "metrics": self.metrics,
            "grades": self.grades,
            "score": self.score,
        }


@dataclass
class RunState:
    id: str
    provider: str
    model_id: str
    model_label: str
    temperature: float
    total: int
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    report_name: Optional[str] = None
    error: Optional[str] = None
    outcomes: List[TestOutcome] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    subscribers: List["asyncio.Queue[Dict[str, Any]]"] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    grades: Dict[int, List[GradeEntry]] = field(default_factory=dict)
    #: Prompt text keyed by qualified ``"<suite>/<file>"`` ID.
    #:
    #: This was once keyed by bare filename. With several suites in one run
    #: that silently returns the wrong question's text: graders derive their
    #: entire rubric from the prompt, so a collision yields confident,
    #: plausible, wrong scores with no error anywhere. Never key by filename.
    prompts_by_id: Dict[str, str] = field(default_factory=dict)

    @property
    def completed(self) -> int:
        return len(self.outcomes)

    @property
    def overall_score(self) -> Optional[float]:
        scores = [o.score for o in self.outcomes if o.score is not None]
        return sum(scores) / len(scores) if scores else None

    def summary(self) -> Dict[str, Any]:
        ok = [o for o in self.outcomes if o.status == "ok" and o.metrics]
        if ok:
            avg_tps = sum(float(o.metrics.get("tokens_per_second", 0)) for o in ok) / len(ok)
            avg_ttft = sum(float(o.metrics.get("time_to_first_token", 0)) for o in ok) / len(ok)
            total_tokens = sum(int(o.metrics.get("total_tokens", 0)) for o in ok)
        else:
            avg_tps = avg_ttft = 0.0
            total_tokens = 0
        overall = self.overall_score
        return {
            "average_tokens_per_second": round(avg_tps, 2),
            "average_time_to_first_token": round(avg_ttft, 2),
            "total_tokens": total_tokens,
            "passed": len([o for o in self.outcomes if o.status == "ok"]),
            "failed": len([o for o in self.outcomes if o.status == "error"]),
            "overall_score": round(overall, 4) if overall is not None else None,
            "graded": len([o for o in self.outcomes if o.score is not None]),
        }

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "provider": self.provider,
            "model_id": self.model_id,
            "model_label": self.model_label,
            "temperature": self.temperature,
            "total": self.total,
            "completed": self.completed,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "report_name": self.report_name,
            "error": self.error,
            "summary": self.summary(),
        }


def _prompt_key(prompt: Dict[str, str]) -> str:
    """Qualified ID for a prompt dict as the loader produces it."""
    qualified = prompt.get("id")
    if qualified:
        return str(qualified)
    suite = prompt.get("suite", "")
    filename = prompt.get("filename", "")
    return f"{suite}/{filename}" if suite else filename


def _format_sse(event: Dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


class RunManager:
    """Owns the lifecycle of diagnostic runs.

    Only one run may be active at a time: the local engine loads model weights
    into memory, so overlapping runs would compete for RAM and produce
    meaningless throughput numbers.
    """

    def __init__(self) -> None:
        self._runs: "OrderedDict[str, RunState]" = OrderedDict()
        self._active_id: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ query

    def get(self, run_id: str) -> Optional[RunState]:
        with self._lock:
            return self._runs.get(run_id)

    def active(self) -> Optional[RunState]:
        with self._lock:
            if self._active_id is None:
                return None
            return self._runs.get(self._active_id)

    def history(self) -> List[RunState]:
        with self._lock:
            return list(reversed(self._runs.values()))

    # ------------------------------------------------------------------ start

    def start(
        self,
        *,
        provider_name: str,
        model_id: str,
        model_label: str,
        temperature: float,
        prompts: List[Dict[str, str]],
        loop: asyncio.AbstractEventLoop,
    ) -> RunState:
        with self._lock:
            if self._active_id is not None:
                active = self._runs.get(self._active_id)
                if active is not None and active.status == "running":
                    raise RuntimeError(
                        f"A run is already in progress ({active.model_label}). "
                        "Cancel it before starting another."
                    )

            run = RunState(
                id=uuid.uuid4().hex[:12],
                provider=provider_name,
                model_id=model_id,
                model_label=model_label,
                temperature=temperature,
                total=len(prompts),
                prompts_by_id={
                    _prompt_key(p): p.get("prompt", "") for p in prompts
                },
            )
            self._runs[run.id] = run
            self._active_id = run.id
            while len(self._runs) > MAX_RUN_HISTORY:
                oldest, _ = next(iter(self._runs.items()))
                if oldest == self._active_id:
                    break
                self._runs.pop(oldest)

        run.events.append(
            {
                "type": "run.started",
                "run": run.as_dict(),
                "tests": [
                    {"index": i, "title": p["title"], "filename": p["filename"]}
                    for i, p in enumerate(prompts, start=1)
                ],
            }
        )

        thread = threading.Thread(
            target=self._worker,
            args=(run, prompts, loop),
            name=f"lm-gambit-run-{run.id}",
            daemon=True,
        )
        thread.start()
        return run

    def cancel(self, run_id: str) -> bool:
        run = self.get(run_id)
        if run is None or run.status != "running":
            return False
        run.cancel_event.set()
        return True

    # ----------------------------------------------------------------- worker

    def _worker(
        self,
        run: RunState,
        prompts: List[Dict[str, str]],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        last_tick = time.time()

        def progress_callback(
            index: int,
            total: int,
            prompt: Dict[str, str],
            result: Dict[str, Any],
        ) -> None:
            nonlocal last_tick
            now = time.time()
            elapsed = now - last_tick
            last_tick = now

            if "error" in result:
                outcome = TestOutcome(
                    index=index,
                    title=prompt.get("title", f"Test {index}"),
                    filename=prompt.get("filename", f"test{index}"),
                    suite=prompt.get("suite", ""),
                    status="error",
                    elapsed=elapsed,
                    error=str(result["error"]),
                )
            else:
                metrics = result.get("metrics") or {}
                outcome = TestOutcome(
                    index=index,
                    title=prompt.get("title", f"Test {index}"),
                    filename=prompt.get("filename", f"test{index}"),
                    suite=prompt.get("suite", ""),
                    status="ok",
                    elapsed=elapsed,
                    response=str(result.get("response", "")),
                    metrics=dict(metrics),
                )

            run.outcomes.append(outcome)
            self._grade(run, outcome)

            # Plugins observe the question after grading, so on_test_complete
            # sees the same record the report will.
            record = build_test_record(
                outcome,
                total=run.total,
                prompt_text=run.prompts_by_id.get(outcome.question_id, ""),
            )
            get_plugin_manager().emit("on_test_complete", record)

            self._publish(loop, run, outcome.as_event(total))

            if run.cancel_event.is_set():
                raise RunCancelled

        get_plugin_manager().emit(
            "on_run_start",
            build_run_record(run, prompts_by_id=run.prompts_by_id),
        )

        try:
            report_path = run_suite(
                provider_name=run.provider,
                model_id=run.model_id,
                temperature=run.temperature,
                progress_callback=progress_callback,
                prompts=prompts,
            )
        except RunCancelled:
            self._finalize_partial_report(run)
            run.status = "cancelled"
            run.finished_at = time.time()
            self._apply_plugin_report(run)
            self._publish(
                loop,
                run,
                {"type": "run.cancelled", "run": run.as_dict()},
            )
        except (TestRunError, TemplateNotFoundError) as exc:
            run.status = "failed"
            run.error = str(exc)
            run.finished_at = time.time()
            self._publish(
                loop,
                run,
                {"type": "run.failed", "message": str(exc), "run": run.as_dict()},
            )
        except Exception as exc:  # noqa: BLE001 - surface engine faults to the UI
            run.status = "failed"
            run.error = f"{type(exc).__name__}: {exc}"
            run.finished_at = time.time()
            self._publish(
                loop,
                run,
                {"type": "run.failed", "message": run.error, "run": run.as_dict()},
            )
        else:
            run.status = "completed"
            run.report_name = report_path.name
            run.finished_at = time.time()
            self._apply_plugin_report(run)
            self._publish(
                loop,
                run,
                {"type": "run.completed", "run": run.as_dict()},
            )
        finally:
            with self._lock:
                if self._active_id == run.id:
                    self._active_id = None
            get_plugin_manager().emit("on_run_complete", self._record(run))

    # ---------------------------------------------------------------- plugins

    def _report_path(self, run: RunState) -> Path:
        return RESULTS_DIR / f"automated_report_{sanitize_model_name(run.model_label)}.md"

    def _record(self, run: RunState):
        path = self._report_path(run)
        return build_run_record(
            run,
            prompts_by_id=run.prompts_by_id,
            report_path=path if path.exists() else None,
        )

    def _grade(self, run: RunState, outcome: TestOutcome) -> None:
        """Run grader plugins over one answer and attach the results.

        Graders run on this worker thread, so a slow grader delays the next
        question. That is deliberate: grading is part of the run, and the
        report should not be finalized before it lands.

        Questions the provider failed are never graded — there is no answer to
        judge, and scoring them would let one careless plugin drag down the
        overall score. Plugins that want to react to failures use
        ``on_test_complete``, which fires for every question.
        """
        if outcome.status != "ok":
            return

        record = build_test_record(
            outcome,
            total=run.total,
            prompt_text=run.prompts_by_id.get(outcome.question_id, ""),
        )
        graded = get_plugin_manager().grade(record)
        if not graded:
            return

        run.grades[outcome.index] = [
            GradeEntry(grader=name, grade=grade) for name, grade in graded
        ]
        outcome.grades = [
            {
                "grader": name,
                "score": grade.score,
                "label": grade.label,
                "notes": grade.notes,
            }
            for name, grade in graded
        ]

    def _apply_plugin_report(self, run: RunState) -> None:
        """Write grades and plugin sections into the finished report."""
        report_path = self._report_path(run)
        if not report_path.exists():
            return

        record = self._record(run)
        manager = get_plugin_manager()

        grade_markdown = render_grade_section(record)
        if grade_markdown:
            try:
                replace_analysis_section(report_path, grade_markdown)
            except OSError:
                pass

        try:
            sections = collect_report_sections(record, manager)
        except Exception:  # noqa: BLE001 - a plugin fault must not fail the run
            sections = []

        if sections:
            try:
                append_sections(report_path, sections)
            except OSError:
                pass

    def _finalize_partial_report(self, run: RunState) -> None:
        """Write the summary block for a run that stopped early."""
        report_path = RESULTS_DIR / f"automated_report_{sanitize_model_name(run.model_label)}.md"
        if not report_path.exists():
            return
        results: List[Dict[str, Any]] = []
        for outcome in run.outcomes:
            if outcome.status == "ok" and outcome.metrics:
                results.append({"response": outcome.response, "metrics": outcome.metrics})
            else:
                results.append({"error": outcome.error or "cancelled"})
        try:
            finalize_report_summary(report_path, results)
        except (OSError, KeyError):
            return
        run.report_name = report_path.name

    # -------------------------------------------------------------- streaming

    def _publish(
        self,
        loop: asyncio.AbstractEventLoop,
        run: RunState,
        event: Dict[str, Any],
    ) -> None:
        """Hand an event from the worker thread to the event loop."""
        try:
            loop.call_soon_threadsafe(self._emit, run, event)
        except RuntimeError:
            # Loop already closed (server shutting down); keep the history only.
            run.events.append(event)

    @staticmethod
    def _emit(run: RunState, event: Dict[str, Any]) -> None:
        run.events.append(event)
        for queue in list(run.subscribers):
            queue.put_nowait(event)

    async def stream(self, run_id: str) -> AsyncIterator[str]:
        run = self.get(run_id)
        if run is None:
            yield _format_sse({"type": "run.failed", "message": "Unknown run id."})
            return

        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        # Subscribing and snapshotting in the same synchronous block guarantees
        # no event is delivered twice or dropped between the two.
        run.subscribers.append(queue)
        history = list(run.events)

        try:
            for event in history:
                yield _format_sse(event)
                if event["type"] in TERMINAL_EVENTS:
                    return

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                yield _format_sse(event)
                if event["type"] in TERMINAL_EVENTS:
                    return
        finally:
            if queue in run.subscribers:
                run.subscribers.remove(queue)


run_manager = RunManager()
