from __future__ import annotations
import sys
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent / ".core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

import argparse
from runner import run_suite, TestRunError, TemplateNotFoundError
from providers import list_provider_names, get_provider
from config import DEFAULT_PROVIDER_NAME

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

    def _print_progress(index: int, total: int, prompt, result):
        status = "FAILED" if "error" in result else "DONE"
        filename_label = prompt.get("filename", f"test{index}")
        title = prompt.get("title", f"Test {index}")
        print(f"Running {title} [{filename_label}] ({index}/{total})... {status}")

    print(f"Starting automated diagnostic run with provider '{provider}'…")
    try:
        report_path = run_suite(provider_name=provider, model_id=model, progress_callback=_print_progress)
    except TestRunError as exc:
        print(f"Error: {exc}")
        return 1
    except TemplateNotFoundError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"\n✅ Success! Report saved to '{report_path.name}'.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
