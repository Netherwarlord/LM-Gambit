# Python tests

```bash
python tests_py/run_all.py            # everything
python tests_py/run_all.py gguf key   # only files matching those words
python tests_py/test_linter.py        # one file directly
```

Exits non-zero if anything fails, so it works as a CI entry point.

No third-party dependencies. `test_api.py` needs a running server
(`python app.py`) and the `requests` package the LM Studio provider already
uses; it prints `SKIP` and passes when the server is down, so the rest stay
useful offline.

| File | Covers |
| --- | --- |
| `test_answer_values.py` | The answer keys themselves, recomputed from scratch |
| `test_answer_key.py` | The correctness grader, both directions |
| `test_api.py` | Suites API, read-only guards, run selection |
| `test_code_lint.py` | Static code rules, and the false positives they must not repeat |
| `test_collision.py` | Qualified question IDs |
| `test_gguf.py` | GGUF header parsing and model classification |
| `test_linter.py` | Report rendering |
| `test_lmstudio.py` | LM Studio model listing, against stubbed HTTP |
| `test_reporting.py` | Report naming and the per-suite breakdown |

The UI tests live separately, under `web/src/**/*.test.tsx` — run them with
`cd web && npm test`.

## Why these are scripts rather than `unittest` cases

They exercise a diagnostic tool, so the output is read as much as the exit
code. `test_code_lint.py` is a table of which rules fire on which input, and
that is worth more when debugging a false positive than a row of dots.
`run_all.py` aggregates exit codes for the times you only want a verdict.

Each file runs in its own process. Several load plugins directly, which would
otherwise collide in `sys.modules`.

## `test_answer_values.py` is the one to keep honest

The other files test code. This one tests **data** — it recomputes every
numeric answer key with exact arithmetic and brute-force search, then asserts
the shipped `answers.json` agrees.

That matters because a wrong key fails correct work with total confidence,
which is the exact failure the answer-key grader exists to remove. It earned
its place immediately: the Winograd referent had been recorded backwards, and
shipping it would have marked every correct answer wrong.

If you add or edit a key, add the computation here too. A key nobody can
re-derive is a liability.
