"""Plugin loader for LM-Gambit.

Drop a ``.py`` file (or a package directory) into ``plugins/`` and it is picked
up at startup. Copy ``plugins/_skeleton.py`` to begin — it documents every hook.

Hooks a plugin may define, all optional:

===========================  ==================================================
``grade(test)``              Score one answer. Return a float, a ``Grade``, or
                             ``None`` to abstain.
``on_run_start(run)``        Fired once when a run begins.
``on_test_complete(test)``   Fired after each question, before the next starts.
``on_run_complete(run)``     Fired once when a run ends (also on cancel/failure).
``report_sections(run)``     Return extra markdown appended to the report.
``register_routes(router)``  Add FastAPI routes under ``/api/plugins/<slug>``.
===========================  ==================================================

Design notes
------------
* Modules load under a synthetic ``lmgambit_plugins`` package. Loading them by
  bare stem would put e.g. ``plugins/config.py`` into ``sys.modules["config"]``
  and shadow the engine's own ``.core/config.py``, since ``.core`` is on
  ``sys.path`` and imported flat.
* Every load and every hook call is isolated. One bad plugin is reported and
  skipped; it never takes down a run or the server.
* Hook results are returned, not discarded, so hooks can contribute data.
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from plugin_api import (
    UI_SLOTS,
    Grade,
    NavItem,
    Page,
    PluginInfo,
    RunRecord,
    SlotPanel,
    ui_payload,
)

ROOT_DIR = Path(__file__).resolve().parent
PLUGIN_DIR = ROOT_DIR / "plugins"
NAMESPACE = "lmgambit_plugins"

HOOK_NAMES = (
    "grade",
    "on_run_start",
    "on_test_complete",
    "on_run_complete",
    "report_sections",
    "register_routes",
    "ui_contributions",
)

#: Plugin pages live under this prefix so they can never shadow a core route.
UI_PATH_PREFIX = "/x"


@dataclass
class LoadedPlugin:
    slug: str
    name: str
    version: str
    description: str
    path: Path
    enabled: bool
    module: Optional[types.ModuleType] = None
    error: Optional[str] = None

    @property
    def hooks(self) -> List[str]:
        if self.module is None:
            return []
        return [hook for hook in HOOK_NAMES if callable(getattr(self.module, hook, None))]

    def info(self) -> PluginInfo:
        return PluginInfo(
            name=self.name,
            slug=self.slug,
            version=self.version,
            description=self.description,
            path=str(self.path),
            enabled=self.enabled and self.error is None,
            hooks=self.hooks,
            error=self.error,
        )


def _ensure_namespace(plugin_dir: Path) -> None:
    """Create the synthetic parent package plugins are loaded beneath."""
    package = sys.modules.get(NAMESPACE)
    if package is None:
        package = types.ModuleType(NAMESPACE)
        package.__doc__ = "Namespace for locally installed LM-Gambit plugins."
        sys.modules[NAMESPACE] = package
    package.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]


def _candidate_paths(plugin_dir: Path) -> List[Path]:
    """Single-file plugins and package directories, ignoring ``_`` prefixes."""
    if not plugin_dir.is_dir():
        return []

    candidates: List[Path] = []
    for entry in sorted(plugin_dir.iterdir()):
        if entry.name.startswith((".", "_")) or entry.name == "__pycache__":
            continue
        if entry.is_file() and entry.suffix == ".py":
            candidates.append(entry)
        elif entry.is_dir() and (entry / "__init__.py").is_file():
            candidates.append(entry / "__init__.py")
    return candidates


class PluginManager:
    """Discovers plugins and dispatches hooks to them."""

    def __init__(self, plugin_dir: Optional[Path] = None, *, auto_load: bool = True) -> None:
        self.plugin_dir = Path(plugin_dir) if plugin_dir else PLUGIN_DIR
        self.loaded: List[LoadedPlugin] = []
        if auto_load:
            self.load()

    # ------------------------------------------------------------- discovery

    def load(self) -> List[LoadedPlugin]:
        """(Re)discover everything in the plugin directory."""
        # Routes registered at startup close over the module object that
        # existed then. Reloading swaps in a new module for every other hook
        # but leaves those handlers reading the old one's globals, so they can
        # quietly serve stale state. Nothing here can rebind them — say so.
        had_routes = {plugin.slug for plugin in self.loaded if "register_routes" in plugin.hooks}

        self.loaded = []
        if not self.plugin_dir.is_dir():
            return self.loaded

        _ensure_namespace(self.plugin_dir)

        for path in _candidate_paths(self.plugin_dir):
            slug = path.parent.name if path.name == "__init__.py" else path.stem
            self.loaded.append(self._load_one(slug, path))

        stale = sorted(had_routes & {plugin.slug for plugin in self.active})
        if stale:
            print(
                f"[plugins] {', '.join(stale)} reloaded, but its HTTP routes still point at the "
                "previously loaded module and may serve stale state. Restart the server to rebind them.",
                file=sys.stderr,
            )

        return self.loaded

    def _load_one(self, slug: str, path: Path) -> LoadedPlugin:
        record = LoadedPlugin(
            slug=slug,
            name=slug.replace("_", " ").title(),
            version="0.0.0",
            description="",
            path=path,
            enabled=True,
        )

        module_name = f"{NAMESPACE}.{slug}"
        is_package = path.name == "__init__.py"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                path,
                submodule_search_locations=[str(path.parent)] if is_package else None,
            )
            if spec is None or spec.loader is None:
                record.error = "Could not create a module spec for this file."
                return record

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            record.error = _last_line(traceback.format_exc())
            return record

        record.module = module
        record.name = str(getattr(module, "NAME", record.name))
        record.version = str(getattr(module, "VERSION", "0.0.0"))
        record.description = str(getattr(module, "DESCRIPTION", ""))
        record.enabled = bool(getattr(module, "ENABLED", True))

        # `register()` is the place for one-time setup, if a plugin needs any.
        register = getattr(module, "register", None)
        if record.enabled and callable(register):
            try:
                register()
            except Exception:
                record.error = f"register() failed: {_last_line(traceback.format_exc())}"
                record.enabled = False

        return record

    # -------------------------------------------------------------- querying

    @property
    def active(self) -> List[LoadedPlugin]:
        return [p for p in self.loaded if p.enabled and p.error is None and p.module is not None]

    def info(self) -> List[PluginInfo]:
        return [plugin.info() for plugin in self.loaded]

    def with_hook(self, hook: str) -> List[LoadedPlugin]:
        return [p for p in self.active if callable(getattr(p.module, hook, None))]

    # -------------------------------------------------------------- dispatch

    def emit(self, hook: str, *args: Any, **kwargs: Any) -> None:
        """Fire a hook for its side effects, ignoring return values."""
        self.collect(hook, *args, **kwargs)

    def collect(self, hook: str, *args: Any, **kwargs: Any) -> List[Tuple[LoadedPlugin, Any]]:
        """Call a hook on every plugin defining it and keep non-None results.

        A plugin that raises is reported on stderr and skipped for this call
        only — it stays loaded for subsequent hooks.
        """
        results: List[Tuple[LoadedPlugin, Any]] = []
        for plugin in self.with_hook(hook):
            callback: Callable[..., Any] = getattr(plugin.module, hook)
            try:
                value = callback(*args, **kwargs)
            except Exception:
                print(
                    f"[plugin:{plugin.slug}] {hook}() failed: {_last_line(traceback.format_exc())}",
                    file=sys.stderr,
                )
                continue
            if value is not None:
                results.append((plugin, value))
        return results

    # ------------------------------------------------------------------- ui

    def ui_manifest(self) -> Dict[str, Any]:
        """Collect every plugin's declared interface into one manifest.

        The frontend fetches this at startup and renders from it, so installing
        a plugin never requires rebuilding the UI. A plugin returning malformed
        contributions is skipped with a warning rather than breaking the app.
        """
        nav: List[Dict[str, Any]] = []
        pages: List[Dict[str, Any]] = []
        slots: Dict[str, List[Dict[str, Any]]] = {slot: [] for slot in UI_SLOTS}

        for plugin, value in self.collect("ui_contributions"):
            items = value if isinstance(value, (list, tuple)) else [value]
            for item in items:
                try:
                    self._add_contribution(plugin.slug, plugin.name, item, nav, pages, slots)
                except Exception:
                    print(
                        f"[plugin:{plugin.slug}] bad UI contribution {item!r}: "
                        f"{_last_line(traceback.format_exc())}",
                        file=sys.stderr,
                    )

        nav.sort(key=lambda entry: (entry.get("order", 100), entry.get("label", "")))
        for entries in slots.values():
            entries.sort(key=lambda entry: entry.get("order", 100))

        return {"nav": nav, "pages": pages, "slots": slots}

    @staticmethod
    def _add_contribution(
        slug: str,
        name: str,
        item: Any,
        nav: List[Dict[str, Any]],
        pages: List[Dict[str, Any]],
        slots: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        if isinstance(item, NavItem):
            entry = ui_payload(item)
            entry["path"] = plugin_ui_path(slug, item.path)
            entry["slug"] = slug
            nav.append(entry)
        elif isinstance(item, Page):
            entry = ui_payload(item)
            entry["path"] = plugin_ui_path(slug, item.path)
            entry["slug"] = slug
            entry["plugin"] = name
            pages.append(entry)
        elif isinstance(item, SlotPanel):
            if item.slot not in slots:
                raise ValueError(f"unknown slot {item.slot!r}; expected one of {', '.join(UI_SLOTS)}")
            slots[item.slot].append(
                {"slug": slug, "plugin": name, "order": item.order, "panel": ui_payload(item.panel)}
            )
        else:
            raise TypeError(f"expected NavItem, Page or SlotPanel, got {type(item).__name__}")

    def grade(self, test: Any) -> List[Tuple[str, Grade]]:
        """Run every grader over one answer, normalising the return values."""
        grades: List[Tuple[str, Grade]] = []
        for plugin, value in self.collect("grade", test):
            grade = _coerce_grade(value)
            if grade is None:
                print(
                    f"[plugin:{plugin.slug}] grade() returned {value!r}; "
                    "expected a number, a Grade, or None.",
                    file=sys.stderr,
                )
                continue
            grades.append((plugin.name, grade))
        return grades


def plugin_ui_path(slug: str, path: str) -> str:
    """Namespace a plugin's declared path under ``/x/``.

    A plugin may write ``"/lint"`` or the fully-qualified ``"/x/code_lint/lint"``
    and get the same result, so short paths stay readable while collisions
    between two plugins — or with a future core route — remain impossible.
    """
    cleaned = "/" + (path or "").strip("/")
    if cleaned.startswith(f"{UI_PATH_PREFIX}/"):
        return cleaned
    suffix = "" if cleaned == "/" else cleaned
    return f"{UI_PATH_PREFIX}/{slug}{suffix}"


def _last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1].strip() if lines else "unknown error"


def _coerce_grade(value: Any) -> Optional[Grade]:
    """Accept a Grade, a number, a bool, or a dict from a grader."""
    if isinstance(value, Grade):
        return value
    if isinstance(value, bool):
        return Grade(score=1.0 if value else 0.0, label="pass" if value else "fail")
    if isinstance(value, (int, float)):
        return Grade(score=float(value))
    if isinstance(value, dict) and "score" in value:
        try:
            return Grade(
                score=float(value["score"]),
                label=str(value.get("label", "")),
                notes=str(value.get("notes", "")),
            )
        except (TypeError, ValueError):
            return None
    return None


# --------------------------------------------------------------- report output
# These live here rather than in the server so the CLI and the web interface
# produce byte-identical reports for the same run.


def letter_grade(score: float) -> str:
    for threshold, letter in (
        (0.97, "A+"), (0.93, "A"), (0.90, "A-"),
        (0.87, "B+"), (0.83, "B"), (0.80, "B-"),
        (0.77, "C+"), (0.73, "C"), (0.70, "C-"),
        (0.67, "D+"), (0.60, "D"),
    ):
        if score >= threshold:
            return letter
    return "F"


def _suite_breakdown(record: RunRecord, graders: List[str]) -> List[str]:
    """A suite × grader table of mean scores.

    Worth its own table because a run now spans several suites, and a single
    overall number hides where a model actually struggled. It also fixes a
    misleading reading of abstentions: a grader that only understands code
    abstains on most of a mixed run, which looks like weak coverage against the
    whole suite list but is exactly right per-suite — "100% of math-code, not
    applicable elsewhere". Abstentions show as `—`, never as a zero.
    """
    order: List[str] = []
    per_suite: Dict[str, List[Any]] = {}
    for test in record.tests:
        slug = getattr(test, "suite", "") or "(unassigned)"
        if slug not in per_suite:
            per_suite[slug] = []
            order.append(slug)
        per_suite[slug].append(test)

    # A single suite adds no information the overall line does not already give.
    if len(order) < 2:
        return []

    header = ["| Suite | Questions | Score |", "| --- | --- | --- |"]
    if graders:
        header = [
            "| Suite | Questions | Score | " + " | ".join(graders) + " |",
            "| --- | --- | --- |" + " --- |" * len(graders),
        ]

    rows: List[str] = []
    for slug in order:
        tests = per_suite[slug]
        scores = [s for s in (record.score_for(t.index) for t in tests) if s is not None]
        mean = sum(scores) / len(scores) if scores else None
        cells = [
            f"`{slug}`",
            str(len(tests)),
            f"{mean:.0%} ({letter_grade(mean)})" if mean is not None else "—",
        ]
        for grader in graders:
            values = [
                entry.grade.score
                for t in tests
                for entry in (record.grades.get(t.index) or [])
                if entry.grader == grader
            ]
            cells.append(
                f"{sum(values) / len(values):.0%} ({len(values)}/{len(tests)})" if values else "—"
            )
        rows.append("| " + " | ".join(cells) + " |")

    return [
        "",
        "**By suite**",
        "",
        *header,
        *rows,
        "",
        "A `—` means every grader abstained there, not a zero. Abstentions never "
        "count against a score.",
    ]


def render_grade_section(record: RunRecord) -> Optional[str]:
    """Render grades as the report's Qualitative Analysis block."""
    overall = record.overall_score
    if overall is None:
        return None

    graders = sorted({entry.grader for entries in record.grades.values() for entry in entries})

    def escape(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ").strip()

    lines = [
        f"**Overall score: {overall:.0%} ({letter_grade(overall)})** "
        f"— graded by {', '.join(f'`{g}`' for g in graders)}.",
        "",
        "Scores come from plugins in `plugins/`, so they reflect whatever those "
        "plugins check — not a judgement of correctness. Review before relying on them.",
    ]

    lines.extend(_suite_breakdown(record, graders))

    lines.extend(
        [
            "",
            "**By question**",
            "",
            "| # | Suite | Question | Score | Grader | Notes |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    for test in record.tests:
        suite = escape(getattr(test, "suite", "") or "—")
        for entry in record.grades.get(test.index) or []:
            label = escape(entry.grade.label)
            score = f"{entry.grade.score:.0%}" + (f" ({label})" if label else "")
            lines.append(
                f"| {test.index} | `{suite}` | {escape(test.title)} | {score} "
                f"| {escape(entry.grader)} | {escape(entry.grade.notes) or '—'} |"
            )

    ungraded = [t for t in record.tests if not record.grades.get(t.index)]
    if ungraded:
        lines.extend(
            [
                "",
                f"*{len(ungraded)} question(s) were not graded — no plugin had an "
                "opinion on them. They are excluded from the overall score.*",
            ]
        )

    return "\n".join(lines)


def collect_report_sections(record: RunRecord, manager: "PluginManager") -> List[str]:
    """Normalize whatever `report_sections` hooks return into markdown blocks."""
    blocks: List[str] = []
    for _, value in manager.collect("report_sections", record):
        blocks.extend(_normalize_section(value))
    return blocks


def _normalize_section(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                heading, body = item
                parts.append(f"{heading}\n\n{body}")
        return parts
    return []


_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Process-wide plugin manager, created on first use."""
    global _manager
    if _manager is None:
        _manager = PluginManager()
    return _manager


def reload_plugins() -> List[LoadedPlugin]:
    """Re-scan the plugin directory. New routes still need a server restart."""
    return get_plugin_manager().load()
