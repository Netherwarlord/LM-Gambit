"""Report naming and the per-suite score breakdown.

Two things are pinned here. Names must stay parseable and must survive the
API's filename guard, since reports are fetched by name. And the breakdown must
show an abstention as an abstention: a grader that only understands code
abstains on most of a mixed run, which looks like weak coverage against the
whole suite list but is exactly right per suite.
"""

from __future__ import annotations

import re

from _harness import Results, bootstrap

bootstrap()
from plugin_api import Grade, GradeEntry, RunRecord, TestRecord  # noqa: E402
from plugin_system import letter_grade, render_grade_section  # noqa: E402
from reporting import build_report_name, describe_scope  # noqa: E402

r = Results("Report naming and grade rendering")

# The guard GET /api/reports/{name} applies before reading from disk.
NAME_GUARD = re.compile(r"^[A-Za-z0-9._-]+\.md$")

r.section("scope labels")
r.equal("a single suite keeps its slug", describe_scope(["math-code"]), "math-code")
r.equal("two suites collapse to a count", describe_scope(["math-code", "safety"]), "mixed2")
r.equal("no suites", describe_scope([]), "adhoc")
r.equal("every built-in suite",
        describe_scope(["language", "reasoning-logic", "math-code",
                        "context-knowledge", "safety"]), "all")

r.section("names survive the API filename guard")
for label, slugs, count in [
    ("gemma-4-E2B-it-Q8_0", ["math-code"] * 6, 6),
    ("gemma-4-E2B-it-Q8_0", ["safety"] * 4 + ["math-code"], 5),
    ("DeepSeek-R1-0528-Qwen3-8B-Q6_K", ["language"] * 6, 6),
    ("weird / model:name", [], 0),
]:
    name = build_report_name(label, slugs, count)
    r.check(f"{name}", bool(NAME_GUARD.match(name)))

r.section("names round-trip back to scope and count")
from server.api import _parse_report_name  # noqa: E402  (needs bootstrap)

name = build_report_name("gemma-4-E2B-it-Q8_0", ["math-code"] * 6, 6)
r.equal("parsed", _parse_report_name(name[:-3]), ("math-code", 6))
r.equal("a legacy name yields no false scope",
        _parse_report_name("automated_report_gemma-4-E2B-it-Q8_0"), ("", None))

r.section("per-suite breakdown")
tests, grades = [], {}
plan = [
    ("language", 3, [("Instruction compliance", 1.0)]),
    ("math-code", 3, [("Instruction compliance", 0.9), ("Code lint", 1.0)]),
    ("safety", 2, [("Instruction compliance", 0.85)]),
]
index = 0
for slug, count, graders in plan:
    for n in range(1, count + 1):
        index += 1
        tests.append(TestRecord(index=index, total=9, title=f"{slug} question {n}",
                                filename=f"test{n}.txt", suite=slug, prompt="p",
                                ok=True, response="r"))
        grades[index] = [GradeEntry(grader=g, grade=Grade(score=s)) for g, s in graders]

# One ungraded question, to prove abstentions are excluded rather than zeroed.
tests.append(TestRecord(index=9, total=9, title="ungraded", filename="test9.txt",
                        suite="language", prompt="p", ok=True, response="r"))

record = RunRecord(id="t", provider="p", model_id="m", model_label="m", temperature=0.0,
                   total=len(tests), status="completed", started_at=0.0,
                   tests=tests, grades=grades)
rendered = render_grade_section(record)

r.check("breakdown table present", "**By suite**" in rendered)
r.check("every suite appears",
        all(f"`{slug}`" in rendered for slug, _, _ in plan))
r.check("a grader that abstained on a suite shows as a dash, not zero",
        re.search(r"\|\s*`safety`\s*\|[^|]*\|[^|]*\|\s*—\s*\|", rendered) is not None,
        "expected '—' in the Code lint column for safety")
r.check("partial coverage is shown as graded/total", "(3/3)" in rendered)
r.check("ungraded questions are called out and excluded",
        "not graded" in rendered and "excluded from the overall score" in rendered)

r.section("a single-suite run omits the breakdown")
solo = RunRecord(id="t2", provider="p", model_id="m", model_label="m", temperature=0.0,
                 total=1, status="completed", started_at=0.0,
                 tests=[tests[0]], grades={1: grades[1]})
r.check("no table when it would only restate the overall line",
        "**By suite**" not in render_grade_section(solo))

r.section("letter grades")
for score, letter in [(1.0, "A+"), (0.95, "A"), (0.91, "A-"), (0.85, "B"),
                      (0.75, "C"), (0.67, "D+"), (0.65, "D"), (0.2, "F")]:
    r.equal(f"{score:.0%}", letter_grade(score), letter)

raise SystemExit(r.finish())
