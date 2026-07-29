"""Every graded record must carry its own question's prompt.

Prompt text was once keyed by bare filename. Every suite ships a ``test1.txt``,
so a run drawing from two suites handed graders the wrong question's text —
and graders derive their entire rubric from the prompt, so the result was a
confident, plausible, wrong score with no error anywhere.

This is the regression guard. It also measures what the old scheme would have
done, so the failure stays concrete rather than theoretical.
"""

from __future__ import annotations

from _harness import Results, bootstrap

bootstrap()
from server.plugins import build_run_record  # noqa: E402
from server.run_manager import RunState, TestOutcome, _prompt_key  # noqa: E402
from suites import load_prompts  # noqa: E402

r = Results("Qualified question IDs")

# Two suites that both contain test1.txt — the collision case.
prompts = load_prompts(["language", "safety"])
filenames = [p["filename"] for p in prompts]

r.equal("drew from two suites", len(prompts), 10)
r.check("the collision is real: 'test1.txt' appears more than once",
        filenames.count("test1.txt") > 1, filenames.count("test1.txt"))

run = RunState(
    id="t", provider="p", model_id="m", model_label="m",
    temperature=0.0, total=len(prompts),
    prompts_by_id={_prompt_key(p): p.get("prompt", "") for p in prompts},
)
for index, prompt in enumerate(prompts, start=1):
    run.outcomes.append(
        TestOutcome(index=index, title=prompt["title"], filename=prompt["filename"],
                    suite=prompt["suite"], status="ok", elapsed=0.1,
                    response="answer", metrics={})
    )

record = build_run_record(run, prompts_by_id=run.prompts_by_id)

r.section("every record carries its own prompt")
mismatched = [t.question_id for t, original in zip(record.tests, prompts)
              if t.prompt != original["prompt"]]
r.check("no prompt mismatches", not mismatched, mismatched)

wrong_suite = [t.question_id for t, original in zip(record.tests, prompts)
               if t.suite != original["suite"]]
r.check("no suite mismatches", not wrong_suite, wrong_suite)
r.check("ids are qualified", all("/" in t.question_id for t in record.tests))
r.equal("ids are unique", len({t.question_id for t in record.tests}), len(prompts))

r.section("the old scheme, for comparison")
old_style = {p.get("filename", ""): p.get("prompt", "") for p in prompts}
would_break = sum(1 for p in prompts if old_style.get(p["filename"]) != p["prompt"])
r.check(f"bare-filename keying would misgrade {would_break} of {len(prompts)}",
        would_break > 0, "collision no longer reproducible — has the suite changed?")

raise SystemExit(r.finish())
