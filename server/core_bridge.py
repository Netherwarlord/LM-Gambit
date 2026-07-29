"""Import shim for the ``.core`` engine package.

``.core`` is a hidden directory, so it cannot be imported as a normal package.
The CLI (``auto-test.py``) works around this by putting the directory on
``sys.path`` and importing its modules flat. We do the same thing here, in one
place, so the rest of the server can just ``from .core_bridge import run_suite``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CORE_DIR = ROOT_DIR / ".core"

if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

# ruff: noqa: E402  (imports must follow the sys.path mutation above)
from config import (  # type: ignore[import-not-found]
    DEFAULT_PROVIDER_NAME,
    DEFAULT_TEMPERATURE,
    MODELS_DIR,
    RESULTS_DIR,
    TEMPLATE_PATH,
    TESTS_DIR,
    ensure_directories,
)
from engine_loader import (  # type: ignore[import-not-found]
    EngineLoadError,
    detect_architecture,
    engine_warning,
    gpu_offload_supported,
    load_engine_class,
)
from prompts import load_test_prompts  # type: ignore[import-not-found]
from providers import (  # type: ignore[import-not-found]
    LocalEngineProvider,
    ModelInfo,
    Provider,
    ProviderError,
    get_provider,
    list_provider_names,
)
from reporting import (  # type: ignore[import-not-found]
    TemplateNotFoundError,
    append_sections,
    finalize_report_summary,
    replace_analysis_section,
    sanitize_model_name,
)
from runner import TestRunError, run_suite  # type: ignore[import-not-found]
from settings import (  # type: ignore[import-not-found]
    get_local_model_paths,
    load_settings,
    save_settings,
    set_local_model_paths,
)
from suites import (  # type: ignore[import-not-found]
    ReadOnlySuiteError,
    Suite,
    SuiteError,
    create_suite,
    delete_suite,
    duplicate_suite,
    find_prompts,
    get_suite,
    list_suites,
    load_prompts,
    load_suite_prompts,
    save_suite_tests,
    split_question_id,
    update_suite,
)

__all__ = [
    "CORE_DIR",
    "DEFAULT_PROVIDER_NAME",
    "EngineLoadError",
    "detect_architecture",
    "engine_warning",
    "gpu_offload_supported",
    "load_engine_class",
    "DEFAULT_TEMPERATURE",
    "MODELS_DIR",
    "ModelInfo",
    "Provider",
    "ProviderError",
    "RESULTS_DIR",
    "ROOT_DIR",
    "TEMPLATE_PATH",
    "TESTS_DIR",
    "TemplateNotFoundError",
    "TestRunError",
    "LocalEngineProvider",
    "append_sections",
    "ensure_directories",
    "finalize_report_summary",
    "replace_analysis_section",
    "get_local_model_paths",
    "get_provider",
    "list_provider_names",
    "load_settings",
    "load_test_prompts",
    "ReadOnlySuiteError",
    "Suite",
    "SuiteError",
    "create_suite",
    "delete_suite",
    "duplicate_suite",
    "find_prompts",
    "get_suite",
    "list_suites",
    "load_prompts",
    "load_suite_prompts",
    "save_suite_tests",
    "split_question_id",
    "update_suite",
    "run_suite",
    "sanitize_model_name",
    "save_settings",
    "set_local_model_paths",
]


def provider_kwargs(provider_name: str) -> dict:
    """Build constructor kwargs for a provider, mirroring the runner's logic."""
    if provider_name == LocalEngineProvider.name:
        custom_paths = [Path(p).expanduser() for p in get_local_model_paths()]
        return {"search_paths": [path for path in custom_paths if path]}
    return {}


def build_provider(provider_name: str) -> Provider:
    """Instantiate a provider with the correct per-provider configuration."""
    return get_provider(provider_name, **provider_kwargs(provider_name))
