from __future__ import annotations

import re
from typing import Iterable, List, Tuple

__all__ = ["infer_language_from_prompt", "lint_response_markdown"]


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

_CODE_SYMBOLS = set("{}();[]=<>+-*/.&|%!:@")
_CODE_PREFIXES = (
    "func ",
    "class ",
    "struct ",
    "enum ",
    "protocol ",
    "extension ",
    "import ",
    "let ",
    "var ",
    "guard ",
    "if ",
    "for ",
    "while ",
    "switch ",
    "case ",
    "return ",
    "init(",
    "init ",
    "deinit",
    "public ",
    "private ",
    "internal ",
    "fileprivate ",
    "override ",
    "@",
    "#if",
    "#endif",
    "#warning",
    "#error",
)

_COMMENT_PREFIXES = ("///", "//", "/*", "*/", "* ")
_BULLET_PREFIXES = ("- ", "* ", "+ ", "• ")


def infer_language_from_prompt(prompt_text: str) -> str:
    """Infer a reasonable language hint from the prompt text."""
    lowered = prompt_text.lower()
    for token, language in _LANGUAGE_HINTS:
        if token in lowered:
            return language
    return "text"


def lint_response_markdown(raw_text: str, *, language_hint: str = "text") -> str:
    """Normalize markdown so that only code segments are fenced and text stays plain."""
    if not raw_text:
        return ""

    text = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text:
        return ""

    if "```" in text:
        return _normalize_existing_fences(text, language_hint)

    return _auto_fence_code_segments(text, language_hint)


def _normalize_existing_fences(text: str, language_hint: str) -> str:
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

    if in_fence:
        output.append("```")

    result = "\n".join(output).strip()
    return result


def _auto_fence_code_segments(text: str, language_hint: str) -> str:
    lines = text.split("\n")
    segments: List[Tuple[str, List[str]]] = []
    current_lines: List[str] = []
    current_mode: str | None = None

    for line in lines:
        if _is_blank(line):
            if current_lines:
                current_lines.append(line)
            continue

        classification = "code" if _is_likely_code_line(line) else "text"

        if current_mode is None:
            current_mode = classification
            current_lines.append(line)
            continue

        if classification == current_mode:
            current_lines.append(line)
            continue

        segments.append((current_mode, current_lines))
        current_mode = classification
        current_lines = [line]

    if current_lines:
        segments.append((current_mode or "text", current_lines))

    cleaned_parts: List[str] = []
    for mode, block_lines in segments:
        block_text = "\n".join(block_lines).strip("\n")
        if not block_text:
            continue
        if mode == "code":
            cleaned_parts.append(_format_code_block(block_text, language_hint))
        else:
            cleaned_parts.append(block_text)

    return "\n\n".join(part for part in cleaned_parts if part).strip()


def _format_code_block(content: str, language_hint: str) -> str:
    language = language_hint if language_hint and language_hint != "text" else ""
    inner = content.strip("\n")
    return f"```{language}\n{inner}\n```"


def _is_blank(line: str) -> bool:
    return not line.strip()


def _is_likely_code_line(line: str) -> bool:
    if line.startswith(("    ", "\t")):
        return True

    stripped = line.strip()
    if not stripped:
        return False

    if stripped.startswith(_BULLET_PREFIXES):
        return False

    if stripped.startswith(_COMMENT_PREFIXES):
        return True

    if any(stripped.startswith(prefix) for prefix in _CODE_PREFIXES):
        return True

    if stripped.endswith(("{", "}", ";")):
        return True

    if stripped.startswith(("}", "{", "case ", "default:")):
        return True

    if "(" in stripped and ")" in stripped:
        return True

    if "=" in stripped:
        return True

    symbol_count = sum(1 for ch in stripped if ch in _CODE_SYMBOLS)
    letter_count = sum(1 for ch in stripped if ch.isalpha())
    if symbol_count >= 2 and symbol_count >= max(1, letter_count * 0.3):
        return True

    if re.search(r"\)\s*->", stripped):
        return True

    return False
