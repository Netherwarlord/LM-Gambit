import re
import textwrap
from pathlib import Path
from typing import Dict, List

from config import TESTS_DIR


def _natural_key(path: Path) -> List[object]:
    parts = re.split(r"(\d+)", path.stem)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def load_test_prompts() -> List[Dict[str, str]]:
    """Load prompt files from the tests directory."""
    if not TESTS_DIR.exists():
        return []

    prompt_entries: List[Dict[str, str]] = []

    for prompt_path in sorted(TESTS_DIR.glob("*.txt"), key=_natural_key):
        try:
            raw_text = prompt_path.read_text(encoding="utf-8")
        except OSError:
            continue

        prompt_text = textwrap.dedent(raw_text).strip()
        if not prompt_text:
            continue

        title = prompt_path.stem
        for line in prompt_text.splitlines():
            stripped_line = line.strip()
            if stripped_line:
                title = stripped_line
                break

        prompt_entries.append(
            {
                "title": title,
                "prompt": prompt_text,
                "filename": prompt_path.name,
            }
        )

    return prompt_entries
