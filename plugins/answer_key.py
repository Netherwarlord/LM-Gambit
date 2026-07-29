"""Grades answers against a per-suite key of expected content.

The two other graders measure **form** — whether an answer did what it was
told. This one is the only thing in the system that asks whether the answer was
*right*. Both matter, and they are kept apart deliberately: a model can follow
every instruction perfectly while asserting that a fabricated treaty is a
historical fact, and score full marks for it.

Keys live beside the questions they grade::

    .core/suites/<slug>/answers.json     ships with the built-in suites
    tests/<slug>/answers.json            optional, for custom suites

Only questions with an objectively checkable answer are keyed. Sentiment,
translation quality, bias and tone are judgement calls, and pattern-matching
them would manufacture exactly the false confidence this plugin exists to
remove. **No key means abstain**, which costs nothing.

Matchers, all optional, scored as the fraction satisfied:

===========================  =================================================
``must_contain``             every string present
``must_contain_any``         at least one present
``must_not_contain_any``     none present — **see the warning below**
``numbers``                  every value present, compared numerically so
                             ``1,911,492`` and ``1911492`` both match
``regex``                    pattern matches
===========================  =================================================

.. warning::

   ``must_not_contain_any`` is far more dangerous than it looks, and none of
   the shipped keys use it. A good diagnostic question routinely *requires*
   the model to name the wrong answer:

   * "Show why it is **not 50%**" — a correct answer says "50%".
   * "State the intuitive-but-wrong answer" — a correct answer says "24 days".
   * "**Quote** the exact text that carries it" — a correct answer quotes
     "DAN MODE ACTIVE" out of the jailbreak it is dissecting.

   All three were tried; the last failed a correct answer on its first live
   run. A substring match cannot tell quoting from doing. Prefer positive
   matchers, which caught every real failure so far.

A note on trusting this file: a wrong key is worse than no key, because it
fails correct answers with total confidence. Every value in the shipped keys
was recomputed independently before being written — brute-forcing the logic
grid and the CPM network, and re-deriving the Winograd referent, which had in
fact been recorded backwards.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin_api import Grade, RunRecord, TestRecord

NAME = "Answer key"
VERSION = "1.0.0"
DESCRIPTION = "Checks answers against known-correct content, where one exists."
ENABLED = True

_ROOT = Path(__file__).resolve().parent.parent
_BUILTIN_SUITES = _ROOT / ".core" / "suites"
_CUSTOM_SUITES = _ROOT / "tests"

#: Cache keyed by suite slug. Cleared at the start of every run so edits to a
#: key file take effect without restarting the server.
_CACHE: Dict[str, Dict[str, Any]] = {}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


# --------------------------------------------------------------------- keys


def _load_key(slug: str) -> Dict[str, Any]:
    if slug in _CACHE:
        return _CACHE[slug]

    data: Dict[str, Any] = {}
    for base in (_BUILTIN_SUITES, _CUSTOM_SUITES):
        path = base / slug / "answers.json"
        if not path.is_file():
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # a malformed key must not break a run
        if isinstance(loaded, dict):
            data = loaded
            break

    _CACHE[slug] = data
    return data


def _entry_for(test: TestRecord) -> Optional[Dict[str, Any]]:
    if not test.suite:
        return None
    entry = _load_key(test.suite).get(test.filename)
    return entry if isinstance(entry, dict) else None


# ----------------------------------------------------------------- matching

#: Grouped forms first so they win: ``1,911,492`` and ``1 911 492`` must be read
#: whole. Separators are only accepted when followed by exactly three digits —
#: treating a bare space as a separator merged neighbouring numbers, so
#: "1,911,492  2." was read as the single value 19114922.
_NUMBER_RE = re.compile(
    r"-?\d{1,3}(?:[,_ ]\d{3})+(?:\.\d+)?"
    r"|-?\d+(?:\.\d+)?"
)


def _numbers_in(text: str) -> List[float]:
    """Every number in the text, separators stripped.

    Models write the same value many ways — ``1,911,492``, ``1911492``,
    ``1 911 492`` — so comparison is numeric rather than textual.
    """
    values: List[float] = []
    for raw in _NUMBER_RE.findall(text):
        cleaned = raw.replace(",", "").replace("_", "").replace(" ", "").rstrip(".")
        if not cleaned or cleaned in {"-", "."}:
            continue
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def _has_number(target: float, present: List[float]) -> bool:
    # Relative tolerance so a rounded 30.399 still matches 30.39872, without
    # letting 32 match 33.
    return any(abs(value - target) <= max(0.005, abs(target) * 1e-6) for value in present)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def _evaluate(entry: Dict[str, Any], response: str) -> List[Check]:
    checks: List[Check] = []
    haystack = _normalise(response)
    numbers = _numbers_in(response)

    required = entry.get("must_contain") or []
    for needle in required:
        found = _normalise(str(needle)) in haystack
        checks.append(Check("must_contain", found, "" if found else f"missing {needle!r}"))

    any_of = entry.get("must_contain_any") or []
    if any_of:
        hit = next((n for n in any_of if _normalise(str(n)) in haystack), None)
        checks.append(
            Check(
                "must_contain_any",
                hit is not None,
                "" if hit else f"none of {[str(n) for n in any_of][:4]}",
            )
        )

    banned = entry.get("must_not_contain_any") or []
    for needle in banned:
        clean = _normalise(str(needle)) not in haystack
        checks.append(Check("must_not_contain", clean, "" if clean else f"contains {needle!r}"))

    for target in entry.get("numbers") or []:
        try:
            value = float(target)
        except (TypeError, ValueError):
            continue
        found = _has_number(value, numbers)
        checks.append(Check("numbers", found, "" if found else f"missing {target}"))

    pattern = entry.get("regex")
    if pattern:
        try:
            found = re.search(str(pattern), response) is not None
        except re.error:
            found = True  # a broken pattern must not fail a correct answer
        checks.append(Check("regex", found, "" if found else "expected pattern not found"))

    return checks


# ---------------------------------------------------------------- lifecycle

#: Per-run results, for the report section. Keyed by question index.
_RESULTS: Dict[int, Dict[str, Any]] = {}


def on_run_start(run: RunRecord) -> None:
    _RESULTS.clear()
    _CACHE.clear()


def grade(test: TestRecord):
    if not (test.response or "").strip():
        return None

    entry = _entry_for(test)
    if entry is None:
        return None  # nothing known to be correct here — abstain

    checks = _evaluate(entry, test.response or "")
    if not checks:
        return None

    passed = [c for c in checks if c.passed]
    failed = [c for c in checks if not c.passed]
    score = len(passed) / len(checks)

    _RESULTS[test.index] = {
        "suite": test.suite,
        "filename": test.filename,
        "title": test.title,
        "score": score,
        "failed": [c.detail for c in failed if c.detail],
        "note": str(entry.get("note", "")),
    }

    return Grade(
        score=score,
        label=f"{len(passed)}/{len(checks)} correct",
        notes="; ".join(c.detail for c in failed if c.detail) or "Matches the known answer.",
    )


def report_sections(run: RunRecord):
    if not _RESULTS:
        return None

    rows = []
    for index in sorted(_RESULTS):
        item = _RESULTS[index]
        detail = "; ".join(item["failed"]).replace("|", "\\|") or "—"
        rows.append(
            f"| {index} | `{item['suite']}/{item['filename']}` | "
            f"{item['score']:.0%} | {detail} |"
        )

    wrong = [i for i, item in _RESULTS.items() if item["score"] < 1.0]
    lead = (
        f"{len(_RESULTS)} question(s) had a known answer to check against; "
        f"{len(wrong)} did not fully match."
        if wrong
        else f"All {len(_RESULTS)} question(s) with a known answer matched it."
    )

    body = "\n".join(
        [
            lead,
            "",
            "Unlike the other graders, this one checks whether the answer was "
            "*right*, not whether it was well-formed. Questions without a key "
            "are abstained on rather than guessed at.",
            "",
            "| # | Question | Score | What was missing |",
            "| --- | --- | --- | --- |",
            *rows,
        ]
    )
    return [("## Answer key", body)]
