from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from config import (
    DEFAULT_PROVIDER_NAME,
    DEFAULT_TEMPERATURE,
    TEMPLATE_PATH,
    ensure_directories,
    reset_temp_directory,
)
from prompts import load_test_prompts
from reporting import (
    TemplateNotFoundError,
    append_test_result,
    finalize_report_summary,
    initialize_report_file,
)
from providers import LocalEngineProvider, ModelInfo, ProviderError, get_provider
from settings import get_local_model_paths


class TestRunError(Exception):
    pass


def _choose_model(models: List[ModelInfo], requested_id: Optional[str]) -> ModelInfo:
    if not models:
        raise TestRunError("No models available from provider.")

    if requested_id:
        for model in models:
            if model.id == requested_id:
                return model
        raise TestRunError(f"Model '{requested_id}' not found for the selected provider.")

    return models[0]


def run_suite(
    *,
    provider_name: Optional[str] = None,
    model_id: Optional[str] = None,
    temperature: Optional[float] = None,
    progress_callback: Optional[Callable[[int, int, Dict[str, str], Dict[str, object]], None]] = None,
) -> Path:
    """Run the diagnostic test suite and return the generated report path."""
    ensure_directories()
    reset_temp_directory()

    provider_name = provider_name or DEFAULT_PROVIDER_NAME
    provider_kwargs = {}
    if provider_name == LocalEngineProvider.name:
        custom_paths = [Path(p).expanduser() for p in get_local_model_paths()]
        provider_kwargs["search_paths"] = [path for path in custom_paths if path]

    try:
        provider = get_provider(provider_name, **provider_kwargs)
    except ProviderError as exc:
        raise TestRunError(str(exc)) from exc

    try:
        models = provider.list_models()
    except ProviderError as exc:
        raise TestRunError(str(exc)) from exc

    model = _choose_model(models, model_id)

    if not TEMPLATE_PATH.exists():
        raise TestRunError(
            "Template file missing. Please create '.core/templates/test-block.md' before running tests."
        )

    prompts = load_test_prompts()
    if not prompts:
        raise TestRunError("No test prompts found in the 'tests' directory.")

    report_path = initialize_report_file(model.display_name)
    all_results: List[Dict[str, object]] = []
    selected_temperature = temperature if temperature is not None else DEFAULT_TEMPERATURE

    total_tests = len(prompts)

    for index, prompt in enumerate(prompts, start=1):
        result = provider.run_prompt(model.id, prompt["prompt"], temperature=selected_temperature)
        all_results.append(result)
        append_test_result(report_path, prompt, result, index)
        if progress_callback:
            progress_callback(index, total_tests, prompt, result)

    finalize_report_summary(report_path, all_results)
    return report_path


def safe_run() -> int:
    """CLI helper for running the suite with basic error handling."""
    def _print_progress(index: int, total: int, prompt: Dict[str, str], result: Dict[str, object]) -> None:
        status = "FAILED" if "error" in result else "DONE"
        filename_label = prompt.get("filename", f"test{index}")
        title = prompt.get("title", f"Test {index}")
        print(f"Running {title} [{filename_label}] ({index}/{total})... {status}")

    print(f"Starting automated diagnostic run with provider '{DEFAULT_PROVIDER_NAME}'…")

    try:
        report_path = run_suite(progress_callback=_print_progress)
    except TestRunError as exc:
        print(f"Error: {exc}")
        return 1
    except TemplateNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"\n✅ Success! Report saved to '{report_path.name}'.")
    return 0


if __name__ == "__main__":
    sys.exit(safe_run())
