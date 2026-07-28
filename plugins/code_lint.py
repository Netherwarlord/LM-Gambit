"""Static correctness checks on code found in answers.

Complements ``response_checks``: that plugin asks *whether* an answer contains
a code block, this one asks whether the code is any good. It abstains whenever
an answer has no code, so prose questions are unaffected and neither plugin
penalises the same thing twice.

**Nothing here executes model output.** Every check is static — the code is
parsed into an AST and inspected, never run — so a malicious or simply broken
snippet in a response cannot affect the machine doing the grading. That rules
out checks which need execution (does it return the right value?) and keeps the
ones that do not (is it valid, complete, and does it define what was asked for?).

Checks, by language:

*Python* — syntax and compilation, the signature the prompt demanded, stub
bodies (``pass`` / ``...`` / ``NotImplementedError``), undefined names, unused
imports, bare ``except``, mutable default arguments, and a missing docstring or
missing ``assert`` when the prompt asked for either.

*JSON* — parses, and reports the exact position when it does not.

*Everything else* — delimiter balance, which catches the truncated block that a
small model emits when it runs out of context.

Findings are kept per run so the plugin's own page can show them; see
``ui_contributions`` at the bottom for the interface it adds.
"""

from __future__ import annotations

import ast
import builtins
import json
import re
import textwrap
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from plugin_api import (
    Action,
    Grade,
    Markdown,
    NavItem,
    Page,
    Panel,
    RunRecord,
    SlotPanel,
    Stat,
    StatRow,
    Table,
    TestRecord,
)

NAME = "Code lint"
VERSION = "1.0.0"
DESCRIPTION = "Static analysis of code in answers — never executes it."
ENABLED = True


# --------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------


@dataclass
class Finding:
    severity: str  # "error" | "warning"
    code: str
    message: str
    line: Optional[int] = None


#: Per-run findings, keyed by test index. Reset by ``on_run_start``.
_FINDINGS: Dict[int, List[Finding]] = {}
_BLOCKS_SEEN: Dict[int, int] = {}

_ERROR_PENALTY = 0.25
_WARNING_PENALTY = 0.08


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

_FENCE = re.compile(r"```([A-Za-z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)

_PY_HINTS = ("python", "py", "python3")
_JSON_HINTS = ("json",)

# A prompt that names a signature is stating a hard requirement.
_PROMPT_SIGNATURE = re.compile(r"def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", re.MULTILINE)


#: Languages where a delimiter-balance check is meaningful. Prose and maths are
#: deliberately absent — models fence LaTeX and plain text constantly, and an
#: unmatched bracket in "$\max(30, 19)$" or a sentence is not a defect.
_BALANCED_LANGS = frozenset(
    {"javascript", "js", "typescript", "ts", "java", "c", "cpp", "c++", "go", "rust", "swift", "sql"}
)
_PY_STRUCTURE = re.compile(r"^\s*(?:def|class|import|from)\s+\w", re.MULTILINE)
#: An assert statement anywhere in the answer — fenced, indented or inline.
_ASSERT_IN_TEXT = re.compile(r"\bassert\s+[^\s,.;:]")


def _extract_blocks(text: str, prompt: str) -> List[Tuple[str, str]]:
    """Fenced blocks as (language, source), skipping anything not clearly code.

    Silence beats a false positive here. A block is only classified when the
    fence declares a language we handle, or the content is unmistakable — an
    unlabelled block of prose, maths or pseudo-code is dropped rather than
    guessed at, so it neither gets linted nor counts toward the block total.
    """
    wants_json = bool(re.search(r"\bvalid JSON\b|\bJSON object\b", prompt, re.IGNORECASE))
    blocks: List[Tuple[str, str]] = []

    for declared, body in _FENCE.findall(text):
        code = body.strip("\n")
        if not code.strip():
            continue
        lang = (declared or "").strip().lower()

        if lang in _PY_HINTS:
            blocks.append(("python", code))
        elif lang in _JSON_HINTS:
            blocks.append(("json", code))
        elif lang in _BALANCED_LANGS:
            blocks.append((lang, code))
        elif lang:
            continue  # a language we have no opinion about
        elif _PY_STRUCTURE.search(code):
            blocks.append(("python", code))
        elif wants_json and code.lstrip().startswith(("{", "[")):
            # Unlabelled, but the prompt demanded JSON, so a parse failure means
            # something. Without that demand this would just be a set or LaTeX.
            blocks.append(("json", code))

    return blocks


# --------------------------------------------------------------------------
# Python analysis
# --------------------------------------------------------------------------

_ALWAYS_BOUND = frozenset(dir(builtins)) | {
    "__name__", "__file__", "__doc__", "__package__", "self", "cls", "_",
}


def _bound_names(tree: ast.AST) -> set:
    """Every name bound anywhere in the module.

    Deliberately scope-insensitive. Merging all scopes means a name defined in
    one function and used in another is not reported, which loses a little
    precision — but it makes false positives very rare, and a linter that cries
    wolf on correct code is worse than useless for grading.
    """
    bound = set()
    for node in ast.walk(tree):
        # Lambdas bind arguments too. Missing them would flag the parameter of
        # every `key=lambda x: ...` as undefined — and sort keys are about the
        # most common thing a model writes.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args
            for group in (args.posonlyargs, args.args, args.kwonlyargs):
                bound.update(a.arg for a in group)
            for solo in (args.vararg, args.kwarg):
                if solo is not None:
                    bound.add(solo.arg)

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchStar) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            bound.add(node.rest)
    return bound


def _imported_names(tree: ast.AST) -> Dict[str, int]:
    names: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    continue
                names[(alias.asname or alias.name).split(".")[0]] = node.lineno
    return names


def _is_excerpt(code: str) -> bool:
    """True when the block is an indented quotation of code shown elsewhere.

    Detected by dedenting: if the source only parses once its common leading
    whitespace is removed, it was lifted out of an enclosing block rather than
    written as a standalone program. Such a block is skipped entirely — not
    linted, and not used for name resolution, since the names it references are
    defined in the full version somewhere else in the answer.
    """
    dedented = textwrap.dedent(code)
    if dedented == code:
        return False
    try:
        ast.parse(dedented)
    except SyntaxError:
        return False
    return True


def _is_stub(node: ast.AST) -> bool:
    """A function body that does nothing — the shape of an unfinished answer."""
    body = [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    if not body:
        return True
    if len(body) > 1:
        return False
    only = body[0]
    if isinstance(only, ast.Pass):
        return True
    if isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant) and only.value.value is Ellipsis:
        return True
    if isinstance(only, ast.Raise):
        exc = only.exc
        target = exc.func if isinstance(exc, ast.Call) else exc
        return isinstance(target, ast.Name) and target.id == "NotImplementedError"
    return False


def _lint_python(sources: List[str], prompt: str) -> List[Finding]:
    """Lint every Python block in one answer as a single program.

    Answers routinely split an implementation and its tests across two fenced
    blocks. Checking each block in isolation would then report the function as
    "used but never defined" in the second and "not defined" for the signature
    check — both wrong. Syntax and compilation stay per-block so line numbers
    and a single broken block stay meaningful, but every name-resolution check
    runs against the union.
    """
    findings: List[Finding] = []
    trees: List[ast.AST] = []
    multi = len(sources) > 1

    for position, code in enumerate(sources, start=1):
        where = f" in block {position}" if multi else ""
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            # An indented fragment is an excerpt, not a broken program. Prompts
            # routinely ask a model to quote "the precise line that is wrong",
            # and it fences exactly that — `    return a`. Reporting it as a
            # syntax error punishes the answer for doing what was asked.
            if _is_excerpt(code):
                continue
            findings.append(Finding("error", "syntax", f"Syntax error{where}: {exc.msg}", exc.lineno))
            continue
        try:
            compile(tree, "<answer>", "exec")
        except (SyntaxError, ValueError) as exc:
            findings.append(
                Finding("error", "compile", f"Does not compile{where}: {exc}", getattr(exc, "lineno", None))
            )
        trees.append(tree)

    if not trees:
        return findings

    def walk_all():
        for tree in trees:
            yield from ast.walk(tree)

    functions = [n for n in walk_all() if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    # --- the signature the prompt demanded -------------------------------
    required = _PROMPT_SIGNATURE.search(prompt)
    if required:
        want_name = required.group(1)
        match = next((f for f in functions if f.name == want_name), None)
        if match is None:
            findings.append(
                Finding("error", "signature", f"Prompt requires a function named `{want_name}`; not defined")
            )
        else:
            want_params = [
                p.split(":")[0].split("=")[0].strip()
                for p in required.group(2).split(",")
                if p.strip() and p.strip() not in {"self", "cls"}
            ]
            got_params = [a.arg for a in match.args.posonlyargs + match.args.args if a.arg not in {"self", "cls"}]
            if want_params and got_params != want_params:
                findings.append(
                    Finding(
                        "error",
                        "signature",
                        f"`{want_name}` takes {got_params or 'no arguments'}; "
                        f"the prompt specifies {want_params}",
                        match.lineno,
                    )
                )

    # --- stubs ------------------------------------------------------------
    for func in functions:
        if _is_stub(func):
            findings.append(
                Finding("error", "stub", f"`{func.name}` has no implementation", func.lineno)
            )

    # --- undefined names --------------------------------------------------
    bound = _ALWAYS_BOUND.union(*(_bound_names(tree) for tree in trees))
    reported = set()
    for node in walk_all():
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id not in bound and node.id not in reported:
                reported.add(node.id)
                findings.append(
                    Finding("error", "undefined", f"`{node.id}` is used but never defined", node.lineno)
                )

    # --- unused imports ---------------------------------------------------
    used = {n.id for n in walk_all() if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    used |= {n.attr for n in walk_all() if isinstance(n, ast.Attribute)}
    merged_imports: Dict[str, int] = {}
    for tree in trees:
        merged_imports.update(_imported_names(tree))
    for name, lineno in merged_imports.items():
        if name not in used:
            findings.append(Finding("warning", "unused-import", f"`{name}` imported but unused", lineno))

    # --- classic smells ---------------------------------------------------
    for node in walk_all():
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            findings.append(Finding("warning", "bare-except", "Bare `except:` swallows every error", node.lineno))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + [d for d in node.args.kw_defaults if d]:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        Finding("warning", "mutable-default", f"`{node.name}` has a mutable default argument", node.lineno)
                    )

    # --- things the prompt explicitly asked the code to contain ----------
    lowered = prompt.lower()
    if "docstring" in lowered and functions:
        # "with type hints and a docstring" is about the implementation. Test
        # helpers the model added on its own are not what was being asked for.
        undocumented = [
            f.name
            for f in functions
            if not ast.get_docstring(f) and not f.name.startswith(("test_", "_"))
        ]
        if undocumented:
            findings.append(
                Finding("warning", "docstring", f"Prompt asked for a docstring; missing on {', '.join(undocumented)}")
            )
    return findings


# --------------------------------------------------------------------------
# Other languages
# --------------------------------------------------------------------------

_PAIRS = {"(": ")", "[": "]", "{": "}"}


def _lint_json(code: str) -> List[Finding]:
    try:
        json.loads(code)
    except (json.JSONDecodeError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        return [Finding("error", "json", f"Invalid JSON: {exc}", line)]
    return []


def _lint_delimiters(code: str) -> List[Finding]:
    """Balance check, ignoring anything inside a string or comment."""
    stack: List[str] = []
    quote: Optional[str] = None
    escaped = False
    for char in code:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in _PAIRS:
            stack.append(char)
        elif char in _PAIRS.values():
            if not stack or _PAIRS[stack.pop()] != char:
                return [Finding("error", "delimiters", f"Unbalanced `{char}` — the block looks truncated")]
    if stack:
        return [Finding("error", "delimiters", f"Unclosed `{stack[-1]}` — the block looks truncated")]
    return []


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------


def _analyse(test: TestRecord) -> Tuple[List[Finding], int]:
    blocks = _extract_blocks(test.response or "", test.prompt)
    findings: List[Finding] = []

    # Python is analysed as one program; see _lint_python.
    python_sources = [code for lang, code in blocks if lang == "python"]
    if python_sources:
        findings.extend(_lint_python(python_sources, test.prompt))

    for lang, code in blocks:
        if lang == "json":
            findings.extend(_lint_json(code))
        elif lang != "python":
            findings.extend(_lint_delimiters(code))

    # "Did the answer include tests?" is a content question, not a structural
    # one. Models very often write them as inline spans — `assert fib(0) == 0`
    # — rather than in a fenced block, and those are still tests. Searching the
    # whole response avoids calling a correct answer incomplete over formatting.
    if python_sources and re.search(r"\bassert\b", test.prompt, re.IGNORECASE):
        if not _ASSERT_IN_TEXT.search(test.response or ""):
            findings.append(
                Finding("warning", "tests", "Prompt asked for assert-based tests; none present")
            )

    return findings, len(blocks)


def grade(test: TestRecord):
    if not (test.response or "").strip():
        return None

    findings, block_count = _analyse(test)
    if block_count == 0:
        return None  # no code — response_checks already covers its absence

    _FINDINGS[test.index] = findings
    _BLOCKS_SEEN[test.index] = block_count

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    # A block that will not even parse is not partially correct.
    if any(f.code == "syntax" for f in errors):
        score = 0.0
    else:
        score = max(0.0, 1.0 - _ERROR_PENALTY * len(errors) - _WARNING_PENALTY * len(warnings))

    if not findings:
        label, notes = f"{block_count} block(s) clean", "No static issues found."
    else:
        label = f"{len(errors)} error(s), {len(warnings)} warning(s)"
        notes = "; ".join(
            f"L{f.line} {f.message}" if f.line else f.message for f in (errors + warnings)[:6]
        )

    return Grade(score=score, label=label, notes=notes)


def on_run_start(run: RunRecord) -> None:
    _FINDINGS.clear()
    _BLOCKS_SEEN.clear()


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def report_sections(run: RunRecord):
    if not _FINDINGS:
        return None

    rows = []
    for test in run.tests:
        for finding in _FINDINGS.get(test.index, []):
            detail = finding.message.replace("|", "\\|")
            line = finding.line or "—"
            rows.append(
                f"| {test.index} | {finding.severity} | `{finding.code}` | {line} | {detail} |"
            )

    total_blocks = sum(_BLOCKS_SEEN.values())
    if not rows:
        body = f"All {total_blocks} code block(s) passed every static check."
    else:
        body = "\n".join(
            [
                f"{len(rows)} finding(s) across {total_blocks} code block(s). "
                "Nothing here was executed — these are parse-level results only.",
                "",
                "| # | Severity | Rule | Line | Detail |",
                "| --- | --- | --- | --- | --- |",
                *rows,
            ]
        )
    return [("## Code lint", body)]


# --------------------------------------------------------------------------
# HTTP — data for this plugin's own UI
# --------------------------------------------------------------------------


def _stats_payload() -> dict:
    errors = sum(1 for fs in _FINDINGS.values() for f in fs if f.severity == "error")
    warnings = sum(1 for fs in _FINDINGS.values() for f in fs if f.severity == "warning")
    blocks = sum(_BLOCKS_SEEN.values())
    clean = sum(1 for index, fs in _FINDINGS.items() if not fs)
    graded = len(_FINDINGS) or 1
    return {
        "stats": [
            {"label": "Code blocks", "value": blocks, "hint": "found in answers", "tone": "default"},
            {"label": "Errors", "value": errors, "hint": "parse or correctness",
             "tone": "bad" if errors else "good"},
            {"label": "Warnings", "value": warnings, "hint": "style and smells",
             "tone": "warn" if warnings else "good"},
            {"label": "Clean answers", "value": f"{clean / graded:.0%}",
             "hint": f"{clean} of {len(_FINDINGS)} with code", "tone": "good" if clean == len(_FINDINGS) else "default"},
        ]
    }


def _rows_payload() -> dict:
    rows = [
        [index, f.severity, f.code, f.line or "—", f.message]
        for index in sorted(_FINDINGS)
        for f in _FINDINGS[index]
    ]
    return {
        "columns": ["Question", "Severity", "Rule", "Line", "Detail"],
        "rows": rows,
        "empty": "No findings yet — run the suite against a model that writes code.",
    }


def register_routes(router) -> None:
    @router.get("/stats")
    async def stats() -> dict:
        return _stats_payload()

    @router.get("/rows")
    async def rows() -> dict:
        return _rows_payload()

    @router.post("/clear")
    async def clear() -> dict:
        _FINDINGS.clear()
        _BLOCKS_SEEN.clear()
        return {"message": "Cleared stored lint findings.", "refresh": True}


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------


def ui_contributions():
    """A nav entry, a full page, and a summary panel on the Run view."""
    base = "/api/plugins/code_lint"
    return [
        NavItem(label="Code lint", path="/lint", icon="bug", hint="Static checks on code in answers", order=45),
        Page(
            path="/lint",
            title="Code lint",
            subtitle="Static analysis of code blocks found in model answers. Nothing is executed.",
            blocks=[
                StatRow(source=f"{base}/stats"),
                Panel(
                    title="Findings",
                    subtitle="From the most recent run in this server session.",
                    blocks=[
                        Table(source=f"{base}/rows"),
                        Action(label="Clear findings", post=f"{base}/clear", style="ghost", icon="trash"),
                    ],
                ),
                Panel(
                    title="What this checks",
                    blocks=[
                        Markdown(
                            text=(
                                "**Python** — syntax, compilation, the signature the prompt demanded, "
                                "stub bodies, undefined names, unused imports, bare `except`, mutable "
                                "default arguments, and missing docstrings or asserts when asked for.\n\n"
                                "**JSON** — parses, with the failure position when it does not.\n\n"
                                "**Anything else** — delimiter balance, which catches truncated blocks.\n\n"
                                "> Code is parsed, never run. Execution-dependent correctness "
                                "(does it return the right answer?) is out of scope by design."
                            )
                        )
                    ],
                ),
            ],
        ),
        SlotPanel(
            slot="run.aside",
            order=40,
            panel=Panel(
                title="Code lint",
                subtitle="Updates as the run progresses.",
                blocks=[StatRow(source=f"{base}/stats")],
            ),
        ),
    ]
