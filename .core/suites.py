"""Named test suites, in two tiers.

    .core/suites/<slug>/     built-in, ships with the app, READ-ONLY at runtime
        suite.json           {name, description, order}
        test1.txt ...
    tests/<slug>/            custom, full CRUD, user-owned

Built-in slugs are reserved, so a custom suite can never shadow one. That makes
``<slug>/<file>`` a globally unique question ID, which the rest of the system
depends on: a run may draw from several suites at once, and two suites both
containing ``test1.txt`` is the normal case rather than an edge case.

**Why the qualified ID matters.** Grading is driven entirely by the prompt text
a plugin receives. ``response_checks`` derives its whole rubric from it —
required literals, word budgets, JSON and table requirements, abstention
expectations — and ``code_lint`` reads the required signature out of it. If a
lookup keyed by bare filename returned the wrong suite's question, every grader
would still run happily and produce confident, plausible, entirely wrong
scores, with nothing anywhere to indicate a fault. Hence: never key anything by
bare filename.
"""

from __future__ import annotations

import json
import re
import shutil
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from config import BUILTIN_SUITES_DIR, TESTS_DIR

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$")
QUESTION_FILE_RE = re.compile(r"^test\d+\.txt$")


class SuiteError(Exception):
    """Raised when a suite cannot be read, written, or is not allowed to be."""


class ReadOnlySuiteError(SuiteError):
    """Raised on any attempt to modify a built-in suite. Maps to HTTP 409."""


@dataclass(frozen=True)
class Suite:
    slug: str
    name: str
    description: str
    order: int
    builtin: bool
    path: Path

    @property
    def count(self) -> int:
        return len(_question_files(self.path))


# ---------------------------------------------------------------- discovery


def _natural_key(path: Path) -> List[object]:
    parts = re.split(r"(\d+)", path.stem)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def _question_files(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (p for p in directory.glob("*.txt") if QUESTION_FILE_RE.match(p.name)),
        key=_natural_key,
    )


def _read_manifest(directory: Path, slug: str) -> Dict[str, object]:
    manifest_path = directory / "suite.json"
    data: Dict[str, object] = {}
    if manifest_path.is_file():
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}
    return {
        "name": str(data.get("name") or slug.replace("-", " ").title()),
        "description": str(data.get("description") or ""),
        "order": int(data.get("order") or 100) if str(data.get("order", "")).lstrip("-").isdigit() else 100,
    }


def _scan(root: Path, builtin: bool) -> List[Suite]:
    if not root.is_dir():
        return []
    suites: List[Suite] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith((".", "_")):
            continue
        if not SLUG_RE.match(entry.name):
            continue
        manifest = _read_manifest(entry, entry.name)
        suites.append(
            Suite(
                slug=entry.name,
                name=str(manifest["name"]),
                description=str(manifest["description"]),
                order=int(manifest["order"]),
                builtin=builtin,
                path=entry,
            )
        )
    return suites


def builtin_slugs() -> set:
    """Reserved slugs. A custom suite may never take one of these."""
    return {suite.slug for suite in _scan(BUILTIN_SUITES_DIR, builtin=True)}


def list_suites() -> List[Suite]:
    """Every suite, built-ins first, then custom — each by manifest order."""
    builtins = sorted(_scan(BUILTIN_SUITES_DIR, builtin=True), key=lambda s: (s.order, s.name))
    reserved = {s.slug for s in builtins}
    # A custom directory colliding with a built-in slug is ignored rather than
    # merged: silently shadowing a shipped suite would break question IDs.
    customs = sorted(
        (s for s in _scan(TESTS_DIR, builtin=False) if s.slug not in reserved),
        key=lambda s: (s.order, s.name),
    )
    return builtins + customs


def get_suite(slug: str) -> Suite:
    for suite in list_suites():
        if suite.slug == slug:
            return suite
    raise SuiteError(f"No suite named '{slug}'.")


def require_writable(slug: str) -> Suite:
    suite = get_suite(slug)
    if suite.builtin:
        raise ReadOnlySuiteError(
            f"'{suite.name}' is a built-in suite and cannot be modified. "
            f"Duplicate it to a custom suite first."
        )
    return suite


# ------------------------------------------------------------------ loading


def question_id(slug: str, filename: str) -> str:
    return f"{slug}/{filename}"


def split_question_id(qualified: str) -> tuple:
    """Split ``"<slug>/<file>"``. Rejects bare filenames explicitly."""
    if "/" not in qualified:
        raise SuiteError(
            f"'{qualified}' is not a qualified question ID. "
            "Expected '<suite>/<file>' — bare filenames are ambiguous across suites."
        )
    slug, _, filename = qualified.partition("/")
    return slug, filename


def _load_one(suite: Suite, path: Path) -> Optional[Dict[str, str]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    text = textwrap.dedent(raw).strip()
    if not text:
        return None

    title = path.stem
    for line in text.splitlines():
        if line.strip():
            title = line.strip()
            break

    return {
        "id": question_id(suite.slug, path.name),
        "suite": suite.slug,
        "suite_name": suite.name,
        "filename": path.name,
        "title": title,
        "prompt": text,
    }


def load_suite_prompts(slug: str) -> List[Dict[str, str]]:
    """Every question in one suite, in natural filename order."""
    suite = get_suite(slug)
    loaded = (_load_one(suite, path) for path in _question_files(suite.path))
    return [entry for entry in loaded if entry is not None]


def load_prompts(slugs: Optional[Sequence[str]] = None) -> List[Dict[str, str]]:
    """Questions across several suites, concatenated in the given order.

    ``slugs=None`` means every built-in suite. Custom suites are deliberately
    excluded from that default so a bare run means the same thing on every
    machine instead of depending on local scratch work.
    """
    if slugs is None:
        chosen = [suite.slug for suite in list_suites() if suite.builtin]
    else:
        chosen = list(slugs)

    prompts: List[Dict[str, str]] = []
    for slug in chosen:
        prompts.extend(load_suite_prompts(slug))
    return prompts


def find_prompts(question_ids: Sequence[str]) -> List[Dict[str, str]]:
    """Resolve qualified IDs, preserving each suite's own ordering."""
    wanted = list(question_ids)
    by_suite: Dict[str, set] = {}
    for qualified in wanted:
        slug, filename = split_question_id(qualified)
        by_suite.setdefault(slug, set()).add(filename)

    selected: List[Dict[str, str]] = []
    for slug, filenames in by_suite.items():
        for entry in load_suite_prompts(slug):
            if entry["filename"] in filenames:
                selected.append(entry)

    missing = set(wanted) - {entry["id"] for entry in selected}
    if missing:
        raise SuiteError(f"Unknown question(s): {', '.join(sorted(missing))}")
    return selected


# --------------------------------------------------------------------- CRUD


def _validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not SLUG_RE.match(slug):
        raise SuiteError(
            f"'{slug}' is not a valid suite name. Use lowercase letters, digits "
            "and hyphens, 2-50 characters, not starting or ending with a hyphen."
        )
    if slug in builtin_slugs():
        raise SuiteError(f"'{slug}' is reserved by a built-in suite. Choose another name.")
    return slug


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "suite"


def _write_manifest(directory: Path, name: str, description: str, order: int) -> None:
    payload = {"name": name, "description": description, "order": order}
    (directory / "suite.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def create_suite(name: str, description: str = "", slug: Optional[str] = None) -> Suite:
    slug = _validate_slug(slug or slugify(name))
    directory = TESTS_DIR / slug
    if directory.exists():
        raise SuiteError(f"A suite named '{slug}' already exists.")
    directory.mkdir(parents=True)
    _write_manifest(directory, name.strip() or slug, description.strip(), 100)
    return get_suite(slug)


def update_suite(slug: str, *, name: Optional[str] = None, description: Optional[str] = None) -> Suite:
    suite = require_writable(slug)
    _write_manifest(
        suite.path,
        (name if name is not None else suite.name).strip() or suite.slug,
        (description if description is not None else suite.description).strip(),
        suite.order,
    )
    return get_suite(slug)


def delete_suite(slug: str) -> None:
    suite = require_writable(slug)
    shutil.rmtree(suite.path)


def save_suite_tests(slug: str, prompts: List[str]) -> List[Dict[str, str]]:
    """Replace a custom suite's questions, renumbered test1..testN."""
    suite = require_writable(slug)

    cleaned = [text.strip() for text in prompts]
    for position, text in enumerate(cleaned, start=1):
        if not text:
            raise SuiteError(f"Question {position} is empty. Remove it or add a prompt.")

    suite.path.mkdir(parents=True, exist_ok=True)
    keep = {f"test{index}.txt" for index in range(1, len(cleaned) + 1)}

    for index, text in enumerate(cleaned, start=1):
        target = suite.path / f"test{index}.txt"
        try:
            target.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            raise SuiteError(f"Could not write {target.name}: {exc}") from exc

    for stale in _question_files(suite.path):
        if stale.name not in keep:
            try:
                stale.unlink()
            except OSError:
                continue

    return load_suite_prompts(slug)


def duplicate_suite(slug: str, name: Optional[str] = None) -> Suite:
    """Clone any suite — built-in included — into an editable custom one.

    This is what keeps read-only from being a dead end: the shipped suites can
    be used as a starting point without ever being mutated in place.
    """
    source = get_suite(slug)
    new_name = (name or f"{source.name} (copy)").strip()

    base = _validate_slug(slugify(new_name))
    candidate, counter = base, 2
    while (TESTS_DIR / candidate).exists():
        candidate = f"{base}-{counter}"
        counter += 1

    directory = TESTS_DIR / candidate
    directory.mkdir(parents=True)
    _write_manifest(directory, new_name, source.description, 100)
    for path in _question_files(source.path):
        shutil.copy2(path, directory / path.name)

    return get_suite(candidate)
