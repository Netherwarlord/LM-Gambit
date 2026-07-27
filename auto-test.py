from __future__ import annotations
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / ".core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import argparse
import time
from runner import run_suite, TestRunError, TemplateNotFoundError
from providers import list_provider_names, get_provider
from config import DEFAULT_PROVIDER_NAME
from reporting import append_sections, replace_analysis_section

from plugin_api import GradeEntry, RunRecord, TestRecord
from plugin_system import (
    collect_report_sections,
    get_plugin_manager,
    render_grade_section,
)

def list_providers():
    print("Available providers:")
    for name in list_provider_names():
        print(f"  {name}")

def list_models(provider_name):
    try:
        provider = get_provider(provider_name)
        models = provider.list_models()
        print(f"Models for provider '{provider_name}':")
        for m in models:
            print(f"  {m.id}  ({m.display_name})")
    except Exception as e:
        print(f"Error listing models: {e}")

def print_usage():
    print("""
-h --help          Lists command cli usage instructions
-p <provider>      Sets the provider to connect to, uses local engine if unset
-m <model>         Sets the model to run tests with. (this should have the ability for tab autocompletion from the models found from the provider)
-l --list          Lists providers if used as the only flag, lists models found if used after -p
-t --test          defines the test suite to use for the run

usage example: python3 auto-test.py -m Qwen3-Coder-30B.gguf -t SwiftUI-Knowledge
""")

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-h', '--help', action='store_true')
    parser.add_argument('-p', type=str, metavar='PROVIDER', help='Provider to use')
    parser.add_argument('-m', type=str, metavar='MODEL', help='Model to use')
    parser.add_argument('-l', '--list', action='store_true', help='List providers or models')
    parser.add_argument('-t', type=str, metavar='TEST', help='Test suite to use (not yet implemented)')
    args = parser.parse_args()

    if args.help:
        print_usage()
        return 0

    if args.list:
        if args.p:
            list_models(args.p)
        else:
            list_providers()
        return 0

    provider = args.p or DEFAULT_PROVIDER_NAME
    model = args.m
    # args.t is parsed but not yet implemented in runner

    plugins = get_plugin_manager()
    for loaded in plugins.loaded:
        if loaded.error:
            print(f"Warning: plugin '{loaded.slug}' failed to load: {loaded.error}")

    records: list[TestRecord] = []
    grades: dict[int, list[GradeEntry]] = {}
    started_at = time.time()

    def _print_progress(index: int, total: int, prompt, result):
        status = "FAILED" if "error" in result else "DONE"
        filename_label = prompt.get("filename", f"test{index}")
        title = prompt.get("title", f"Test {index}")

        record = TestRecord(
            index=index,
            total=total,
            title=title,
            filename=filename_label,
            prompt=prompt.get("prompt", ""),
            ok="error" not in result,
            response=result.get("response") if "error" not in result else None,
            error=str(result["error"]) if "error" in result else None,
            metrics=dict(result.get("metrics") or {}),
        )
        records.append(record)

        # Same contract as the web interface: failed questions are never graded.
        scored = plugins.grade(record) if record.ok else []
        if scored:
            grades[index] = [GradeEntry(grader=n, grade=g) for n, g in scored]

        plugins.emit("on_test_complete", record)

        suffix = ""
        if index in grades:
            mean = sum(e.grade.score for e in grades[index]) / len(grades[index])
            suffix = f"  [score {mean:.0%}]"
        print(f"Running {title} [{filename_label}] ({index}/{total})... {status}{suffix}")

    print(f"Starting automated diagnostic run with provider '{provider}'…")
    plugins.emit(
        "on_run_start",
        RunRecord(
            id=f"cli-{int(started_at)}",
            provider=provider,
            model_id=model or "",
            model_label=model or "(provider default)",
            temperature=0.0,
            total=0,
            status="running",
            started_at=started_at,
        ),
    )
    try:
        report_path = run_suite(provider_name=provider, model_id=model, progress_callback=_print_progress)
    except TestRunError as exc:
        print(f"Error: {exc}")
        return 1
    except TemplateNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    _apply_plugins_to_report(report_path, records, grades, provider, model, started_at)

    print(f"\n✅ Success! Report saved to '{report_path.name}'.")
    return 0


def _apply_plugins_to_report(report_path, records, grades, provider, model, started_at) -> None:
    """Write grades and plugin sections into the report the CLI just produced.

    Mirrors what the web backend does, so a run graded through either entrypoint
    yields the same report.
    """
    plugins = get_plugin_manager()
    label = report_path.stem.replace("automated_report_", "")

    record = RunRecord(
        id=f"cli-{int(started_at)}",
        provider=provider,
        model_id=model or "",
        model_label=label,
        temperature=0.0,
        total=len(records),
        status="completed",
        started_at=started_at,
        finished_at=time.time(),
        report_path=report_path,
        summary={},
        tests=records,
        grades=grades,
    )

    grade_markdown = render_grade_section(record)
    if grade_markdown:
        try:
            replace_analysis_section(report_path, grade_markdown)
        except OSError:
            pass
        overall = record.overall_score
        if overall is not None:
            print(f"\nGraded {len(grades)}/{len(records)} questions — overall {overall:.0%}")

    try:
        sections = collect_report_sections(record, plugins)
    except Exception as exc:  # noqa: BLE001 - a plugin must not fail the CLI
        print(f"Warning: report_sections hook failed: {exc}")
        sections = []
    if sections:
        try:
            append_sections(report_path, sections)
        except OSError:
            pass

    plugins.emit("on_run_complete", record)

if __name__ == "__main__":
    raise SystemExit(main())
