from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from config import CORE_DIR

SETTINGS_PATH = CORE_DIR / "user_settings.json"

_DEFAULT_LOCAL_PATHS: List[str] = []
for candidate in (
    Path.home() / ".lmstudio",
    Path.home() / ".lmstudio/models",
    Path.home() / "Library/Application Support/lm-studio/models",
):
    normalized = str(candidate)
    if normalized not in _DEFAULT_LOCAL_PATHS:
        _DEFAULT_LOCAL_PATHS.append(normalized)

_DEFAULT_SETTINGS: Dict[str, object] = {
    "local_model_paths": _DEFAULT_LOCAL_PATHS,
}


def load_settings() -> Dict[str, object]:
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULT_SETTINGS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_SETTINGS)
    if not isinstance(data, dict):
        return dict(_DEFAULT_SETTINGS)
    merged = dict(_DEFAULT_SETTINGS)
    merged.update(data)
    return merged


def save_settings(settings: Dict[str, object]) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")


def get_local_model_paths() -> List[str]:
    settings = load_settings()
    paths = settings.get("local_model_paths", [])
    if not isinstance(paths, list):
        return []
    result: List[str] = []
    for entry in paths:
        if isinstance(entry, str) and entry.strip():
            normalized = str(Path(entry).expanduser())
            if normalized not in result:
                result.append(normalized)
    return result


def set_local_model_paths(paths: List[str]) -> None:
    settings = load_settings()
    normalized: List[str] = []
    for entry in paths:
        if isinstance(entry, str) and entry.strip():
            candidate = str(Path(entry).expanduser())
            if candidate not in normalized:
                normalized.append(candidate)
    settings["local_model_paths"] = normalized
    save_settings(settings)
