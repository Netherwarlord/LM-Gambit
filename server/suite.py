"""Reading and writing the prompt suite in ``tests/``.

The engine treats every ``tests/*.txt`` file as one prompt and derives its title
from the first non-empty line, ordering files by a natural sort of their names.
To keep the web editor and the ``auto-test.py`` CLI in perfect agreement, saving
rewrites the directory as ``test1.txt`` … ``testN.txt`` in the order shown in
the builder. That makes add / remove / reorder unambiguous for both entrypoints.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .core_bridge import TESTS_DIR, load_test_prompts


class SuiteError(Exception):
    """Raised when the suite on disk cannot be read or written."""


def derive_title(prompt: str, fallback: str) -> str:
    for line in prompt.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return fallback


def list_tests() -> List[Dict[str, str]]:
    """Return the suite exactly as the engine sees it."""
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    return load_test_prompts()


def find_tests(filenames: List[str]) -> List[Dict[str, str]]:
    """Return the prompts matching ``filenames``, preserving suite order."""
    wanted = set(filenames)
    selected = [prompt for prompt in list_tests() if prompt["filename"] in wanted]
    missing = wanted - {prompt["filename"] for prompt in selected}
    if missing:
        raise SuiteError(f"Unknown test file(s): {', '.join(sorted(missing))}")
    return selected


def save_suite(prompts: List[str]) -> List[Dict[str, str]]:
    """Replace the suite with ``prompts`` and return the resulting tests."""
    cleaned = [text.strip() for text in prompts]
    for position, text in enumerate(cleaned, start=1):
        if not text:
            raise SuiteError(f"Question {position} is empty. Remove it or add a prompt.")

    TESTS_DIR.mkdir(parents=True, exist_ok=True)

    target_names = {f"test{index}.txt" for index in range(1, len(cleaned) + 1)}
    written: List[Path] = []

    for index, text in enumerate(cleaned, start=1):
        path = TESTS_DIR / f"test{index}.txt"
        try:
            path.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            raise SuiteError(f"Could not write {path.name}: {exc}") from exc
        written.append(path)

    for stale in TESTS_DIR.glob("*.txt"):
        if stale.name not in target_names:
            try:
                stale.unlink()
            except OSError:
                continue

    return list_tests()
