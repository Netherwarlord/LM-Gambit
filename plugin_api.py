"""Stable types passed to LM-Gambit plugins.

Plugins import from this module and nothing else in the project::

    from plugin_api import Grade, RunRecord, TestRecord

Everything here is a plain frozen dataclass, so plugins never touch engine or
server internals and keep working across refactors of either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["Grade", "GradeEntry", "RunRecord", "TestRecord", "PluginInfo"]


@dataclass(frozen=True)
class TestRecord:
    """One question and the model's answer to it."""

    index: int
    total: int
    title: str
    filename: str
    prompt: str
    ok: bool
    response: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    elapsed: float = 0.0

    @property
    def tokens_per_second(self) -> float:
        return float(self.metrics.get("tokens_per_second", 0) or 0)

    @property
    def total_tokens(self) -> int:
        return int(self.metrics.get("total_tokens", 0) or 0)

    @property
    def time_to_first_token(self) -> float:
        return float(self.metrics.get("time_to_first_token", 0) or 0)


@dataclass(frozen=True)
class Grade:
    """A score for one answer.

    ``score`` is clamped to 0.0–1.0. Return ``None`` from a grader instead of a
    ``Grade`` to abstain — abstentions never count against the average.
    """

    score: float
    label: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", max(0.0, min(1.0, float(self.score))))


@dataclass(frozen=True)
class GradeEntry:
    """A grade together with the plugin that produced it."""

    grader: str
    grade: Grade


@dataclass(frozen=True)
class RunRecord:
    """A whole diagnostic run, handed to lifecycle and report hooks."""

    id: str
    provider: str
    model_id: str
    model_label: str
    temperature: float
    total: int
    status: str
    started_at: float
    finished_at: Optional[float] = None
    report_path: Optional[Path] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    tests: List[TestRecord] = field(default_factory=list)
    grades: Dict[int, List[GradeEntry]] = field(default_factory=dict)

    def score_for(self, test_index: int) -> Optional[float]:
        """Mean score across every grader that scored this question."""
        entries = self.grades.get(test_index) or []
        if not entries:
            return None
        return sum(entry.grade.score for entry in entries) / len(entries)

    @property
    def overall_score(self) -> Optional[float]:
        """Mean of the per-question scores, over graded questions only."""
        scores = [s for s in (self.score_for(t.index) for t in self.tests) if s is not None]
        if not scores:
            return None
        return sum(scores) / len(scores)


@dataclass(frozen=True)
class PluginInfo:
    """What the server reports about a discovered plugin."""

    name: str
    slug: str
    version: str
    description: str
    path: str
    enabled: bool
    hooks: List[str] = field(default_factory=list)
    error: Optional[str] = None
