"""Report rendering: preserve content, fence only unambiguous code.

The renderer used to classify line by line and open a new fence whenever the
classification flipped, so bare JSON came out shredded across bogus code
blocks and any sentence containing parentheses was fenced as source. These
tests pin both directions: prose and JSON must survive byte-identical, and
genuinely unfenced code must still get fenced.
"""

from __future__ import annotations

import json

from _harness import Results, bootstrap

bootstrap()
from markdown_linter import infer_language_from_prompt, lint_response_markdown  # noqa: E402
from suites import load_prompts  # noqa: E402

r = Results("Report markdown rendering")

JSON_ANSWER = json.dumps(
    {
        "title": "Horse Domestication History",
        "sections": [
            {"heading": "Origins", "body": "Early herders kept them for milk.",
             "key_term": "herders"}
        ],
        "word_count": 180,
        "constraints_met": ["Output only JSON."],
    },
    indent=2,
)

r.section("the original bug: bare JSON with no fences")
out = lint_response_markdown(JSON_ANSWER, language_hint="text")
r.equal("exactly one fence pair", out.count("```"), 2)
body = out.split("```json\n", 1)[-1].rsplit("\n```", 1)[0]
r.check("JSON survives intact", json.loads(body) == json.loads(JSON_ANSWER))
r.check("labelled as json", out.startswith("```json"))

r.section("prose is never fenced")
PROSE = (
    'The committee postponed the vote (a procedural delay).\n'
    'The phrase "deferred the ballot" is closest (0.95 similarity).\n'
    'Scores were assigned as x = 5 in the worked example.'
)
r.check("prose with parentheses and '=' untouched",
        lint_response_markdown(PROSE, language_hint="text").strip() == PROSE.strip())

MARKDOWN = (
    "1. First identify the entity (a person).\n"
    "2. Then classify it.\n"
    "- Note: ambiguity is possible.\n"
    "> A quoted aside."
)
r.check("markdown lists and quotes untouched",
        lint_response_markdown(MARKDOWN, language_hint="text").strip() == MARKDOWN.strip())

MATHS = (
    "We compute the derivative step by step.\n"
    "First multiply 4827 by 6 to get 28962.\n"
    "Then add the partial products together."
)
r.check("worked arithmetic untouched",
        lint_response_markdown(MATHS, language_hint="text").strip() == MATHS.strip())

r.section("genuinely unfenced code still gets fenced")
CODE = (
    "def fib(n):\n"
    "    a, b = 0, 1\n"
    "    for i in range(n):\n"
    "        a, b = b, a + b\n"
    "    return a"
)
fenced = lint_response_markdown(CODE, language_hint="python")
r.equal("fenced exactly once", fenced.count("```"), 2)
r.check("labelled python", fenced.startswith("```python"))
r.check("code intact", CODE in fenced)

r.section("existing fences")
ALREADY = "Here you go:\n\n```python\nprint(1)\n```\n\nThat's it."
r.check("passes through unchanged",
        lint_response_markdown(ALREADY, language_hint="text").strip() == ALREADY.strip())
r.equal("an unterminated fence is closed",
        lint_response_markdown("Text\n\n```python\nprint(1)", language_hint="text").count("```"), 2)

r.section("language inference uses word boundaries")
for text, expected in [
    ("Explain the algorithm", "text"),          # contains "go"
    ("It was a long time ago", "text"),         # contains "go"
    ("the cargo was heavy", "text"),            # contains "go"
    ("a rusty nail", "text"),                   # contains "rust"
    ("Do not go back and edit Stage 1", "text"),
    ("a swift response is expected", "text"),
    ("Write a Python function", "python"),
    ("Write it in Go", "go"),
    ("Use Rust for this", "rust"),
    ("write it in golang", "go"),
    ("a C++ program", "cpp"),
    ("a C# program", "csharp"),
    ("build with Node.js", "javascript"),
    ("a SwiftUI view", "swift"),
]:
    r.equal(f"{text!r}", infer_language_from_prompt(text), expected)

r.section("against the real suite")
labelled = {p["id"]: infer_language_from_prompt(p["prompt"]) for p in load_prompts()}
non_text = {k: v for k, v in labelled.items() if v != "text"}
r.equal("only the two Python questions carry a language hint",
        set(non_text), {"math-code/test4.txt", "math-code/test5.txt"})

raise SystemExit(r.finish())
