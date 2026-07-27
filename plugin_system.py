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
from typing import Any, Callable, List, Optional, Tuple

from plugin_api import Grade, PluginInfo, RunRecord

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
)


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
        self.loaded = []
        if not self.plugin_dir.is_dir():
            return self.loaded

        _ensure_namespace(self.plugin_dir)

        for path in _candidate_paths(self.plugin_dir):
            slug = path.parent.name if path.name == "__init__.py" else path.stem
            self.loaded.append(self._load_one(slug, path))
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
        "",
        "| # | Question | Score | Grader | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]

    for test in record.tests:
        for entry in record.grades.get(test.index) or []:
            label = escape(entry.grade.label)
            score = f"{entry.grade.score:.0%}" + (f" ({label})" if label else "")
            lines.append(
                f"| {test.index} | {escape(test.title)} | {score} "
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
