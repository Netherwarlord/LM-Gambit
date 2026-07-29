"""Tidy a model's answer for display in the report.

This only ever affects the **report**. Graders receive the raw provider output,
never anything from this module — see ``reporting.render_response_block``, the
sole caller.

The module exists because early models emitted code as bare indented text with
no markdown fences, which rendered as an unreadable wall. Two things have
changed since: models now fence their own code reliably, and the question suite
is mostly prose, mathematics and JSON rather than code.

That makes aggressive auto-fencing a liability. The previous implementation
classified **line by line** and started a new fence whenever the classification
flipped, so a bare JSON object — indented lines alternating with unindented
ones — came out shredded across several bogus code blocks, and any sentence
containing parentheses was fenced as if it were source.

So the rule now is conservative: an answer is either wholly code or wholly not,
and anything ambiguous is left exactly as the model wrote it. A report that
under-formats is honest; one that mangles the answer is worse than useless,
because it misrepresents what the model actually produced.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Tuple

__all__ = ["infer_language_from_prompt", "lint_response_markdown"]


# Ordered: the first match wins, so "swiftui" must precede "swift".
_LANGUAGE_HINTS: List[Tuple[str, str]] = [
    ("swiftui", "swift"),
    ("swift", "swift"),
    ("objective-c", "objective-c"),
    ("objc", "objective-c"),
    ("kotlin", "kotlin"),
    ("typescript", "typescript"),
    ("javascript", "javascript"),
    ("node.js", "javascript"),
    ("python", "python"),
    ("rust", "rust"),
    ("go", "go"),
    ("c#", "csharp"),
    ("c++", "cpp"),
    ("java", "java"),
    ("sql", "sql"),
]

#: Language names that are also ordinary English words. "Do not go back and
#: edit Stage 1" is not a request for Go, and "a swift response" is not Swift.
#: These match only capitalised, which is how the language is written in
#: practice, or via an unambiguous ``-lang`` alias.
_AMBIGUOUS = {"go", "rust", "swift"}

#: Whole-word matchers for the table above.
#:
#: Substring matching was silently wrong in a way that only showed on prose:
#: "algorithm", "ago" and "cargo" all contain "go", and "rusty" contains
#: "rust", so an arithmetic question was labelled as Go source. Tokens carrying
#: punctuation (``c++``, ``c#``, ``node.js``) cannot take a trailing ``\b``,
#: since ``\b`` needs a word character on the inside of the boundary.
_LANGUAGE_PATTERNS: List[Tuple[re.Pattern, str]] = []
for _token, _language in _LANGUAGE_HINTS:
    _lead = r"\b" if _token[0].isalnum() else ""
    _trail = r"\b" if _token[-1].isalnum() else ""
    if _token in _AMBIGUOUS:
        _body = f"(?:{re.escape(_token.capitalize())}|{re.escape(_token)}lang)"
        _LANGUAGE_PATTERNS.append((re.compile(_lead + _body + _trail), _language))
    else:
        _LANGUAGE_PATTERNS.append(
            (re.compile(_lead + re.escape(_token) + _trail, re.IGNORECASE), _language)
        )


_CODE_SYMBOLS = set("{}();[]=<>+-*/&|%!@")
_CODE_PREFIXES = (
    "func ", "def ", "class ", "struct ", "enum ", "protocol ", "extension ",
    "import ", "from ", "let ", "var ", "const ", "guard ", "switch ",
    "public ", "private ", "internal ", "fileprivate ", "override ",
    "async ", "await ", "@", "#if", "#endif", "#include", "#define",
)
_COMMENT_PREFIXES = ("///", "//", "/*", "*/")
_BULLET_PREFIXES = ("- ", "* ", "+ ", "• ", "> ", "#")

#: Share of non-blank lines that must look like code before the whole answer is
#: fenced. Deliberately high: the cost of missing a fence is cosmetic, the cost
#: of fencing prose is a report that lies about the answer.
_CODE_RATIO = 0.85
_MIN_CODE_LINES = 2


def infer_language_from_prompt(prompt_text: str) -> str:
    """Infer a language hint from the prompt, or ``"text"`` when unsure.

    Only used to label fences the model left unlabelled, so a wrong answer is
    cosmetic — but it should not be confidently wrong on a question with no
    code in it at all.
    """
    for pattern, language in _LANGUAGE_PATTERNS:
        if pattern.search(prompt_text):
            return language
    return "text"


def lint_response_markdown(raw_text: str, *, language_hint: str = "text") -> str:
    """Normalise an answer's markdown without changing what it says."""
    if not raw_text:
        return ""

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text:
        return ""

    if "```" in text:
        return _normalize_existing_fences(text, language_hint)

    return _wrap_if_wholly_code(text, language_hint)


def _normalize_existing_fences(text: str, language_hint: str) -> str:
    """Even up fence markers and label unlabelled ones. Content is untouched."""
    lines = text.split("\n")
    output: List[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            fence_marker = stripped[3:].strip()
            if in_fence:
                output.append("```")
                in_fence = False
            else:
                language = fence_marker or (language_hint if language_hint != "text" else "")
                output.append(f"```{language}" if language else "```")
                in_fence = True
        else:
            output.append(line)

    # A model that runs out of tokens mid-block leaves the fence open, which
    # would swallow everything rendered after it.
    if in_fence:
        output.append("```")

    return "\n".join(output).strip()


def _wrap_if_wholly_code(text: str, language_hint: str) -> str:
    """Fence the answer only if *all* of it is code. Otherwise return it as-is.

    Never emits more than one fence and never interleaves fenced and unfenced
    runs — that interleaving is precisely what shredded JSON answers before.
    """
    as_json = _as_json_block(text)
    if as_json is not None:
        return as_json

    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < _MIN_CODE_LINES:
        return text

    code_lines = [line for line in lines if _is_likely_code_line(line)]
    if len(code_lines) / len(lines) < _CODE_RATIO:
        return text

    # Ratio alone is not enough: a dense block of symbol-heavy prose can clear
    # it. Require at least one unambiguous structural marker as well.
    if not any(_has_strong_code_signal(line) for line in code_lines):
        return text

    language = language_hint if language_hint and language_hint != "text" else ""
    return f"```{language}\n{text.strip()}\n```"


def _as_json_block(text: str) -> Optional[str]:
    """One ```json fence when the answer is a single JSON value, else None.

    Several questions ask for bare JSON with no fence, and the model complies.
    Treating that as an unfenced blob is what caused it to be split apart.
    """
    candidate = text.strip()
    if not candidate.startswith(("{", "[")):
        return None
    try:
        json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return f"```json\n{candidate}\n```"


def _has_strong_code_signal(line: str) -> bool:
    stripped = line.strip()
    return (
        any(stripped.startswith(prefix) for prefix in _CODE_PREFIXES)
        or stripped.startswith(_COMMENT_PREFIXES)
        or stripped.endswith(("{", "}", ";", ":"))
        or bool(re.search(r"\)\s*(->|=>|\{)", stripped))
    )


def _is_likely_code_line(line: str) -> bool:
    """Whether one line looks like source.

    Two rules were removed from the original: "contains both parentheses" and
    "contains an equals sign". Both fire on ordinary English — "the vote (a
    delay)", "x = 5 in the worked example" — and between them they were enough
    to fence plain prose as code.
    """
    if line.startswith(("    ", "\t")):
        return True

    stripped = line.strip()
    if not stripped:
        return False

    # Markdown structure is prose, whatever punctuation it carries.
    if stripped.startswith(_BULLET_PREFIXES):
        return False
    if re.match(r"^\d+[.)]\s", stripped):
        return False

    if stripped.startswith(_COMMENT_PREFIXES):
        return True

    if any(stripped.startswith(prefix) for prefix in _CODE_PREFIXES):
        return True

    if stripped.endswith(("{", "}", ";")):
        return True

    if stripped.startswith(("}", "{")):
        return True

    if re.search(r"\)\s*(->|=>)", stripped):
        return True

    # Symbol density, as a last resort. Needs to be genuinely dense: prose with
    # a couple of brackets should not qualify.
    symbol_count = sum(1 for ch in stripped if ch in _CODE_SYMBOLS)
    letter_count = sum(1 for ch in stripped if ch.isalpha())
    return symbol_count >= 3 and symbol_count >= max(2, letter_count * 0.5)
