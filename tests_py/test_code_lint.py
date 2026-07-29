"""Static code analysis: every rule fires, and none fires on correct work.

Six false positives were found in this grader during development, all with the
same root cause — assuming a formatting convention that real model output does
not follow. The second half of this file is the regression suite for those, and
it is the more important half: a linter that flags correct answers is worse
than no linter, because its findings look authoritative.
"""

from __future__ import annotations

from _harness import Results, load_plugin, record

cl = load_plugin("code_lint")
r = Results("Code lint")


def grade(prompt: str, response: str):
    return cl.grade(record(1, 1, "t", "test1.txt", "math-code", prompt, response))


def scores_below(label: str, prompt: str, response: str, ceiling: float) -> None:
    result = grade(prompt, response)
    r.check(label, result is not None and result.score < ceiling,
            None if result is None else result.score)


def scores_clean(label: str, prompt: str, response: str) -> None:
    result = grade(prompt, response)
    r.check(label, result is not None and result.score == 1.0,
            None if result is None else f"{result.score} — {result.notes}")


r.section("each rule fires")
scores_below("syntax error", "x", "```python\ndef f(:\n  return 1\n```", 0.5)
scores_below("stub body", "x", "```python\ndef solve(a):\n    pass\n```", 1.0)
scores_below("undefined name", "x",
             "```python\ndef f(a):\n    return a + qqq_undefined\n```", 1.0)
scores_below("unused import", "x",
             "```python\nimport os\ndef f():\n    return 1\n```", 1.0)
scores_below("bare except", "x",
             "```python\ndef f():\n    try:\n        return 1\n    except:\n        return 0\n```", 1.0)
scores_below("mutable default argument", "x",
             "```python\ndef f(a=[]):\n    return a\n```", 1.0)
scores_below("signature disagrees with the prompt",
             "Write def top_k_frequent(nums: list[int], k: int) -> list[int]:",
             "```python\ndef top_k_frequent(items):\n    return items\n```", 1.0)
scores_below("invalid JSON", "Output valid JSON", '```json\n{"a": 1,,}\n```', 1.0)
scores_below("unbalanced delimiters", "x",
             "```javascript\nfunction f() { return [1,2\n```", 1.0)
scores_below("missing docstring the prompt asked for", "include a docstring",
             "```python\ndef f():\n    return 1\n```", 1.0)

r.section("correct work is left alone")
scores_clean("matching signature",
             "Write def top_k_frequent(nums: list[int], k: int) -> list[int]:",
             "```python\ndef top_k_frequent(nums, k):\n    '''Doc.'''\n    return sorted(nums)[:k]\n```")
scores_clean("valid JSON", "Output valid JSON", '```json\n{"a": 1}\n```')

r.check("an answer with no code abstains",
        grade("Explain gravity", "Gravity is an attractive force between masses.") is None)

r.section("regressions: formatting real models actually use")
scores_clean(
    "implementation and tests in separate blocks",
    "Write def top_k_frequent(nums: list[int], k: int) -> list[int]: with assert tests",
    "Here is the function:\n\n```python\ndef top_k_frequent(nums, k):\n    '''Doc.'''\n"
    "    return sorted(nums)[:k]\n```\n\nAnd the tests:\n\n```python\n"
    "assert top_k_frequent([1,2,2], 1) == [1]\n```",
)
scores_clean(
    "lambda, comprehension and walrus bindings",
    "Write a function",
    "```python\nimport heapq\ndef f(items):\n    pairs = [(v, k) for k, v in items.items()]\n"
    "    pairs.sort(key=lambda x: (-x[0], x[1]))\n    squares = {n: n * n for n in range(3)}\n"
    "    if (total := sum(squares.values())) > 0:\n        return heapq.nlargest(1, pairs), total\n"
    "    return pairs, total\n```",
)
scores_clean(
    "assert tests written as inline code spans",
    "Fix def fib(n): and write three assert-based test cases. Include a docstring.",
    "Here is the fix:\n\n```python\ndef fib(n):\n    '''Doc.'''\n    return n\n```\n\n"
    "Tests:\n1. **Boundary (n=0):**\n   `assert fib(0) == 0`\n"
    "2. **Small (n=1):**\n   `assert fib(1) == 1`\n",
)
scores_clean(
    "a quoted excerpt beside the full function",
    "Identify the precise line that is wrong in def fib(n):",
    "The function is:\n\n```python\ndef fib(n):\n    a, b = 0, 1\n"
    "    for i in range(n):\n        a, b = b, a + b\n    return a\n```\n\n"
    "The precise line that is wrong:\n\n```python\n    return a\n```\n",
)

r.section("the regressions did not blunt the real checks")
scores_below("a genuine syntax error is still caught", "Write a python function",
             "```python\ndef f(:\n    return 1\n```", 0.5)
scores_below("genuinely absent tests are still flagged",
             "Fix def fib(n): and write three assert-based test cases. Include a docstring.",
             "```python\ndef fib(n):\n    '''Doc.'''\n    return n\n```\nNo tests provided.", 1.0)

raise SystemExit(r.finish())
