"""Requirement coverage grader.

Scores an answer on whether it actually used the API symbols the question asked
for. Prompts in this suite name their requirements in backticks —
``func generateFizzBuzz(upTo max: Int) -> [String]``, ``actor``, ``@Observable``
— which makes them checkable without any language-specific parsing.

Two wrinkles this handles:

* **Negated requirements.** "Do not use the old ``INIntent`` based system" names
  a symbol that must be *absent*. Treating every backticked span as required
  would penalise a correct answer, so the sentence around each span is checked
  for a negation first.
* **Abstaining.** A question with no backticked requirements gets no score
  rather than a bad one. Abstentions are excluded from the average.

This is a starting point, not a final rubric — copy it and encode whatever
"correct" means for your own suite.
"""

import re

from plugin_api import Grade, RunRecord, TestRecord

NAME = "Requirement coverage"
VERSION = "1.0.0"
DESCRIPTION = "Checks that answers use the API symbols each question asks for."
ENABLED = True

# A backticked span is a requirement only if it looks like an identifier or a
# signature — this filters out prose asides and single punctuation marks.
_BACKTICK = re.compile(r"`([^`\n]{2,120})`")

# Markers that flip a requirement into a prohibition. Both an auxiliary-verb
# negation ("should not use", "must never rely on", "doesn't need") and a set of
# fixed phrases, since prompts word this many different ways.
_NEGATION_RE = re.compile(
    r"\b(?:do|does|did|should|shall|must|will|would|can|could|may)\s*(?:n[o']t|not|never)\b"
    r"|\bn't\b",
    re.IGNORECASE,
)
_NEGATION_PHRASES = (
    "avoid",
    "instead of",
    "rather than",
    "without using",
    "no longer",
    "deprecated",
    "stop using",
    "get rid of",
    "remove the",
    "not the old",
    "old system",
)


def _is_negated(sentence: str) -> bool:
    lowered = sentence.lower()
    return bool(_NEGATION_RE.search(lowered)) or any(p in lowered for p in _NEGATION_PHRASES)

_CODE_VERBS = ("write", "implement", "create", "refactor", "provide", "build", "generate")


def _sentences(text: str):
    return re.split(r"(?<=[.!?])\s+|\n{2,}", text)


def _requirements(prompt: str):
    """Split backticked spans into (required, forbidden) symbol lists."""
    required: list[str] = []
    forbidden: list[str] = []

    for sentence in _sentences(prompt):
        negated = _is_negated(sentence)
        for raw in _BACKTICK.findall(sentence):
            symbol = raw.strip()
            # Skip spans that are only punctuation or whitespace.
            if not symbol or not any(ch.isalnum() or ch in "@\\/" for ch in symbol):
                continue
            bucket = forbidden if negated else required
            if symbol not in bucket:
                bucket.append(symbol)

    # A symbol demanded somewhere and banned elsewhere is ambiguous — drop it.
    contested = set(required) & set(forbidden)
    return (
        [s for s in required if s not in contested],
        [s for s in forbidden if s not in contested],
    )


def grade(test: TestRecord):
    if not test.response:
        return None

    required, forbidden = _requirements(test.prompt)
    wants_code = any(verb in test.prompt.lower() for verb in _CODE_VERBS)

    if not required and not forbidden and not wants_code:
        return None  # nothing checkable — abstain

    response = test.response
    checks: list[bool] = []
    problems: list[str] = []

    for symbol in required:
        present = symbol in response
        checks.append(present)
        if not present:
            problems.append(f"missing `{symbol}`")

    for symbol in forbidden:
        absent = symbol not in response
        checks.append(absent)
        if not absent:
            problems.append(f"used forbidden `{symbol}`")

    if wants_code:
        has_block = "```" in response
        checks.append(has_block)
        if not has_block:
            problems.append("no fenced code block")

    if not checks:
        return None

    score = sum(checks) / len(checks)
    met = sum(checks)

    return Grade(
        score=score,
        label=f"{met}/{len(checks)} checks",
        notes="; ".join(problems) if problems else "All stated requirements met.",
    )


def report_sections(run: RunRecord):
    """Call out the questions where requirements were missed."""
    misses = []
    for test in run.tests:
        for entry in run.grades.get(test.index, []):
            if entry.grader == NAME and entry.grade.score < 1.0:
                misses.append((test, entry.grade))

    if not misses:
        return None

    lines = [
        "These questions did not use every API symbol the prompt asked for. "
        "Verify by hand before treating them as failures — a model may solve the "
        "problem a different but valid way.",
        "",
        "| # | Question | Score | Problem |",
        "| --- | --- | --- | --- |",
    ]
    for test, grade in misses:
        problem = grade.notes.replace("|", "\\|")
        title = test.title.replace("|", "\\|")
        lines.append(f"| {test.index} | {title} | {grade.score:.0%} | {problem} |")

    return [("## Requirement coverage", "\n".join(lines))]
