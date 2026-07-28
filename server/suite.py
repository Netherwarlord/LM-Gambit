"""Server-side access to named test suites.

The engine keeps suites in two tiers — read-only built-ins under
``.core/suites/`` and user-owned custom ones under ``tests/<slug>/`` — and this
module is the thin server layer over :mod:`suites` in the core.

Everything here speaks **qualified question IDs** (``"<suite>/<file>"``). Bare
filenames are ambiguous the moment a run draws from more than one suite, and
resolving one to the wrong question would hand a grader the wrong prompt and
produce a confident, wrong score in silence.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .core_bridge import (  # noqa: F401  (several are re-exported for the API)
    TESTS_DIR,
    ReadOnlySuiteError,
    Suite,
    SuiteError,
    create_suite,
    delete_suite,
    duplicate_suite,
    find_prompts,
    get_suite,
    list_suites,
    load_prompts,
    load_suite_prompts,
    save_suite_tests,
    split_question_id,
    update_suite,
)

__all__ = [
    "ReadOnlySuiteError",
    "Suite",
    "SuiteError",
    "create_suite",
    "delete_suite",
    "duplicate_suite",
    "get_suite",
    "list_suites",
    "load_suite_prompts",
    "resolve_selections",
    "save_suite_tests",
    "update_suite",
]


def resolve_selections(
    selections: Optional[Sequence[object]] = None,
    question_ids: Optional[Sequence[str]] = None,
) -> List[Dict[str, str]]:
    """Turn a run request into an ordered list of prompts.

    ``selections`` is a list of objects with ``.suite`` and optional
    ``.filenames``; a suite with no filenames contributes all of its questions.
    ``question_ids`` is the older flat form and must be fully qualified.
    Passing neither means every built-in suite.
    """
    if selections:
        prompts: List[Dict[str, str]] = []
        seen = set()
        for selection in selections:
            slug = getattr(selection, "suite", None) or ""
            get_suite(slug)  # raises SuiteError for an unknown slug
            filenames = getattr(selection, "filenames", None)
            chosen = (
                load_suite_prompts(slug)
                if not filenames
                else find_prompts([f"{slug}/{name}" for name in filenames])
            )
            for entry in chosen:
                if entry["id"] not in seen:
                    seen.add(entry["id"])
                    prompts.append(entry)
        return prompts

    if question_ids:
        bare = [qid for qid in question_ids if "/" not in qid]
        if bare:
            raise SuiteError(
                "Bare filenames are ambiguous across suites: "
                f"{', '.join(sorted(bare))}. Use '<suite>/<file>' IDs, or 'selections'."
            )
        return find_prompts(list(question_ids))

    return load_prompts(None)
