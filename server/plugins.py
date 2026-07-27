"""Bridge between the server's internals and the plugin API.

Plugins only ever see the frozen dataclasses in ``plugin_api``. This module does
the translation and owns the markdown rendering of grades, so nothing in the
plugin contract is coupled to how runs happen to be stored.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from plugin_api import Grade, GradeEntry, RunRecord, TestRecord  # noqa: E402
from plugin_system import (  # noqa: E402
    PluginManager,
    collect_report_sections,
    get_plugin_manager,
    letter_grade,
    render_grade_section,
)

if TYPE_CHECKING:  # pragma: no cover
    from .run_manager import RunState, TestOutcome

__all__ = [
    "Grade",
    "GradeEntry",
    "PluginManager",
    "RunRecord",
    "TestRecord",
    "build_run_record",
    "build_test_record",
    "collect_report_sections",
    "get_plugin_manager",
    "letter_grade",
    "render_grade_section",
]


def build_test_record(
    outcome: "TestOutcome",
    *,
    total: int,
    prompt_text: str,
) -> TestRecord:
    return TestRecord(
        index=outcome.index,
        total=total,
        title=outcome.title,
        filename=outcome.filename,
        prompt=prompt_text,
        ok=outcome.status == "ok",
        response=outcome.response,
        error=outcome.error,
        metrics=dict(outcome.metrics or {}),
        elapsed=outcome.elapsed,
    )


def build_run_record(
    run: "RunState",
    *,
    prompts_by_filename: Dict[str, str],
    report_path: Optional[Path] = None,
) -> RunRecord:
    tests = [
        build_test_record(
            outcome,
            total=run.total,
            prompt_text=prompts_by_filename.get(outcome.filename, ""),
        )
        for outcome in run.outcomes
    ]
    return RunRecord(
        id=run.id,
        provider=run.provider,
        model_id=run.model_id,
        model_label=run.model_label,
        temperature=run.temperature,
        total=run.total,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        report_path=report_path,
        summary=run.summary(),
        tests=tests,
        grades={index: list(entries) for index, entries in run.grades.items()},
    )
