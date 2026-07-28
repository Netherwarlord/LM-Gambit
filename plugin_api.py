"""Stable types passed to LM-Gambit plugins.

Plugins import from this module and nothing else in the project::

    from plugin_api import Grade, RunRecord, TestRecord

Everything here is a plain frozen dataclass, so plugins never touch engine or
server internals and keep working across refactors of either.
"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

__all__ = [
    # grading
    "Grade",
    "GradeEntry",
    "RunRecord",
    "TestRecord",
    "PluginInfo",
    # ui blocks
    "Stat",
    "StatRow",
    "Table",
    "Markdown",
    "Action",
    "Panel",
    # ui surfaces
    "NavItem",
    "Page",
    "SlotPanel",
    "UI_SLOTS",
    "ui_payload",
]


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
    #: Slug of the suite this question came from. Empty only for records built
    #: by older callers. ``filename`` is unique *within* a suite but not across
    #: them — several suites ship a ``test1.txt`` — so identify a question by
    #: ``question_id``, never by ``filename`` alone.
    suite: str = ""

    @property
    def question_id(self) -> str:
        """Globally unique ``"<suite>/<file>"`` identifier."""
        return f"{self.suite}/{self.filename}" if self.suite else self.filename

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


# ---------------------------------------------------------------------------
# UI contributions
# ---------------------------------------------------------------------------
# A plugin describes interface it wants to add; the React app renders it. The
# plugin never ships JavaScript and the frontend is never rebuilt to install
# one — the manifest is fetched at runtime from /api/plugins/ui.
#
# Every block may carry inline data *or* a ``source`` URL. With a source, the
# frontend fetches it and expects the same field names back as JSON, so a panel
# can be static, live, or refreshed by an Action without changing shape.


@dataclass(frozen=True)
class Stat:
    """One number with a caption, for a headline row."""

    label: str
    value: Union[str, int, float]
    hint: str = ""
    #: "default" | "good" | "warn" | "bad" — colours the value only.
    tone: str = "default"


@dataclass(frozen=True)
class StatRow:
    """A row of headline numbers."""

    stats: Sequence[Stat] = field(default_factory=tuple)
    source: Optional[str] = None
    kind: str = field(default="stat_row", init=False)


@dataclass(frozen=True)
class Table:
    """A column-headed table. ``rows`` are lists of cell strings."""

    columns: Sequence[str] = field(default_factory=tuple)
    rows: Sequence[Sequence[Any]] = field(default_factory=tuple)
    source: Optional[str] = None
    empty: str = "Nothing to show yet."
    kind: str = field(default="table", init=False)


@dataclass(frozen=True)
class Markdown:
    """Rendered markdown — the same renderer the reports use."""

    text: str = ""
    source: Optional[str] = None
    kind: str = field(default="markdown", init=False)


@dataclass(frozen=True)
class Action:
    """A button that POSTs to one of the plugin's own routes.

    The response may return ``{"message": ...}`` to show a toast, and/or
    ``{"refresh": true}`` to make sibling blocks re-fetch their sources.
    """

    label: str
    post: str
    confirm: Optional[str] = None
    #: "primary" | "ghost" | "danger"
    style: str = "primary"
    icon: Optional[str] = None
    kind: str = field(default="action", init=False)


@dataclass(frozen=True)
class Panel:
    """A titled card grouping other blocks."""

    title: str
    blocks: Sequence[Any] = field(default_factory=tuple)
    subtitle: str = ""
    kind: str = field(default="panel", init=False)


Block = Union[StatRow, Table, Markdown, Action, Panel]


@dataclass(frozen=True)
class NavItem:
    """An entry in the left rail."""

    label: str
    path: str
    #: Any lucide icon name the host allowlists; falls back to a puzzle piece.
    icon: str = "puzzle"
    hint: str = ""
    order: int = 100


@dataclass(frozen=True)
class Page:
    """A full page at ``path``, reachable from a NavItem or a direct link."""

    path: str
    title: str
    blocks: Sequence[Any] = field(default_factory=tuple)
    subtitle: str = ""


#: Injection points on the built-in pages.
UI_SLOTS = (
    "run.aside",
    "reports.aside",
    "suite.aside",
    "settings.section",
)


@dataclass(frozen=True)
class SlotPanel:
    """A Panel injected into a built-in page. ``slot`` must be in UI_SLOTS."""

    slot: str
    panel: Panel
    order: int = 100


def ui_payload(value: Any) -> Any:
    """Convert contribution dataclasses into JSON-safe structures.

    Recurses through sequences and nested blocks. Anything that is not a
    dataclass is passed through untouched, so plugins may hand back plain
    dicts and lists where that is simpler.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {key: ui_payload(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: ui_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [ui_payload(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
