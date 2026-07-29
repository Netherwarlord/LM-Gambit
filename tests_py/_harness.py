"""Shared scaffolding for the Python tests. No third-party dependencies.

Lives in ``tests_py/`` rather than ``tests/`` because that name is taken: it
holds user-created custom suites, and mixing test code into it would be
confusing even though suite discovery only looks at directories.

Tests are plain scripts rather than ``unittest`` cases. They exercise a
diagnostic tool, so their output is read as much as their exit code — the
code-lint file, for instance, is a table of which rules fire on which input,
and that is worth more than a dot per assertion. ``run_all.py`` aggregates
exit codes for CI-style use.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / ".core"
SUITES = CORE / "suites"


def bootstrap() -> None:
    """Put the project and its hidden engine package on ``sys.path``.

    ``.core`` is a hidden directory, so it cannot be imported as a package;
    the CLI and server both work around this the same way.
    """
    for path in (ROOT, CORE):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def load_plugin(name: str) -> Any:
    """Import a plugin directly, bypassing the plugin manager.

    Keeps a test focused on the grader's own logic rather than on discovery,
    and avoids the manager's module caching between test files.
    """
    bootstrap()
    path = ROOT / "plugins" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_test_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def record(index: int, total: int, title: str, filename: str, suite: str,
           prompt: str, response: str):
    """Build a TestRecord the way the runner does, for grader tests."""
    bootstrap()
    from plugin_api import TestRecord  # noqa: PLC0415 - needs bootstrap first

    return TestRecord(
        index=index, total=total, title=title, filename=filename,
        suite=suite, prompt=prompt, ok=True, response=response,
    )


class Results:
    """Counts checks and prints them grouped, then reports an exit code."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.passed = 0
        self.failed = 0
        print(f"\n{title}")
        print("=" * len(title))

    def section(self, name: str) -> None:
        print(f"\n-- {name} --")

    def check(self, label: str, condition: Any, detail: Any = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  PASS  {label}")
            return True
        self.failed += 1
        suffix = f"  ({detail})" if detail != "" else ""
        print(f"  FAIL  {label}{suffix}")
        return False

    def equal(self, label: str, actual: Any, expected: Any) -> bool:
        return self.check(label, actual == expected, f"got {actual!r}, want {expected!r}")

    def finish(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed" + (f", {self.failed} FAILED" if self.failed else ""))
        return 1 if self.failed else 0


def server_available(base: str = "http://localhost:8765") -> Optional[str]:
    """Return an error string if the API is not reachable, else None."""
    try:
        import requests  # noqa: PLC0415 - optional, only for the API tests
    except ImportError:
        return "requests is not installed"
    try:
        requests.get(f"{base}/api/health", timeout=3).raise_for_status()
    except Exception as exc:  # noqa: BLE001 - any failure means "not usable"
        return f"cannot reach {base} ({type(exc).__name__})"
    return None
