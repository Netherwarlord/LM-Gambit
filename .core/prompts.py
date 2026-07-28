"""Prompt loading, kept as a thin façade over :mod:`suites`.

``tests/`` used to be a flat directory of ``test1.txt`` … ``testN.txt``. It is
now a set of named suites — built-ins under ``.core/suites/`` and custom ones
under ``tests/<slug>/`` — so every question carries a qualified ``<slug>/<file>``
ID. Two suites containing ``test1.txt`` is normal, and nothing downstream may
key off the bare filename.

This module survives so ``runner.py`` and anything importing
``load_test_prompts`` keep working; the logic lives in :mod:`suites`.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from suites import load_prompts

__all__ = ["load_test_prompts"]


def load_test_prompts(slugs: Optional[Sequence[str]] = None) -> List[Dict[str, str]]:
    """Questions to run.

    With no argument this is **every built-in suite**, deliberately excluding
    custom ones: a bare ``python auto-test.py`` should mean the same thing on
    every machine rather than depending on local scratch suites. Pass explicit
    slugs to include custom suites.
    """
    return load_prompts(slugs)
