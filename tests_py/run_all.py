"""Run every Python test and summarise. No third-party dependencies.

    python tests_py/run_all.py           # everything
    python tests_py/run_all.py gguf      # only files matching "gguf"

Each test is a standalone script run in its own process, so one crashing
cannot take the rest with it, and each starts from a clean import state —
several load plugins directly, which would otherwise collide in sys.modules.

Exits non-zero if any test fails, so this works as a CI entry point.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    wanted = sys.argv[1:]
    tests = sorted(p for p in HERE.glob("test_*.py"))
    if wanted:
        tests = [p for p in tests if any(w in p.stem for w in wanted)]
    if not tests:
        print("no matching tests")
        return 1

    results: list[tuple[str, int, str]] = []
    for path in tests:
        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(HERE),
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        print(output.rstrip())

        # The last "N/M passed" line, or a SKIP notice, is the verdict.
        summary = next(
            (line.strip() for line in reversed(output.splitlines())
             if "passed" in line or line.strip().startswith("SKIP")),
            "no summary",
        )
        results.append((path.stem, proc.returncode, summary))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    failed = 0
    for name, code, summary in results:
        if "SKIP" in summary:
            status = "SKIP"
        elif code == 0:
            status = "ok"
        else:
            status = "FAIL"
            failed += 1
        print(f"  {status:<5} {name:<22} {summary}")

    print(f"\n{len(results) - failed}/{len(results)} files ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
