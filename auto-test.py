from __future__ import annotations

import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / ".core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from runner import safe_run  # type: ignore  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(safe_run())
