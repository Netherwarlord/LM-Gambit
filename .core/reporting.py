import hashlib
import re
import textwrap
from pathlib import Path
from typing import Dict, List, Optional

from config import RESULTS_DIR, TEMPLATE_PATH, TEMP_DIR
from markdown_linter import infer_language_from_prompt, lint_response_markdown

_TEMPLATE_CACHE: Optional[str] = None


class TemplateNotFoundError(FileNotFoundError):
    pass


def load_template() -> str:
    """Load the test block template from disk, caching the content."""
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is None:
        if not TEMPLATE_PATH.exists():
            raise TemplateNotFoundError(
                f"Template file not found at '{TEMPLATE_PATH}'. Please create it before running tests."
            )
        _TEMPLATE_CACHE = TEMPLATE_PATH.read_text(encoding="utf-8")
    return _TEMPLATE_CACHE


def has_unclosed_code_block(markdown_text: str) -> bool:
    """Check if markdown text ends inside an unclosed triple-backtick block."""
    fence_count = markdown_text.count("```")
    return fence_count % 2 == 1


def render_response_block(result: Dict[str, object], *, language_hint: str) -> str:
    """Render the response portion of the template based on the result payload."""
    if "error" in result:
        return "\n".join(["### Response:", f"**ERROR:** {result['error']}", ""])

    cleaned_response = lint_response_markdown(result["response"], language_hint=language_hint)

    section_lines = ["### Response:"]
    if cleaned_response:
        section_lines.append("")
        section_lines.append(cleaned_response)
    section_lines.append("")
    return "\n".join(section_lines)


def render_test_block(
    prompt_info: Dict[str, str],
    result: Dict[str, object],
    index: int,
) -> str:
    """Populate the test block template with data for a single test."""
    template = load_template()

    metrics = result.get("metrics", {}) if "error" not in result else {}

    ttft_value = metrics.get("time_to_first_token") if metrics else None
    language_hint = infer_language_from_prompt(prompt_info["prompt"])

    replacements = {
        "{{TEST_NUMBER}}": str(index),
        "{{TEST_TITLE}}": prompt_info.get("title", f"Test {index}"),
        "{{SOURCE_FILENAME}}": prompt_info.get("filename", "unknown"),
        "{{PROMPT_CONTENT}}": prompt_info["prompt"].strip(),
        "{{RESPONSE_BLOCK}}": render_response_block(result, language_hint=language_hint).rstrip(),
        "{{METRIC_TOKENS_PER_SECOND}}": (
            str(metrics.get("tokens_per_second", "N/A"))
            if metrics
            else "N/A"
        ),
        "{{METRIC_TOTAL_TOKENS}}": (
            str(metrics.get("total_tokens", "N/A"))
            if metrics
            else "N/A"
        ),
        "{{METRIC_TTFT}}": (
            f"{ttft_value}s" if isinstance(ttft_value, (int, float)) else "N/A"
        ),
        "{{METRIC_STOP_REASON}}": (
            str(metrics.get("stop_reason", "N/A"))
            if metrics
            else "N/A"
        ),
    }

    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)

    return rendered.rstrip() + "\n\n"


def sanitize_model_name(model_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", model_name.strip())
    return sanitized or "unknown-model"


def initialize_report_file(model_label: str) -> Path:
    """Create the markdown report shell and return its path."""
    sanitized = sanitize_model_name(model_label)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / f"automated_report_{sanitized}.md"

    header = textwrap.dedent(
        f"""
        # Automated Diagnostic Report: {model_label}

        ---

        ## Performance Summary

        <!--SUMMARY_START-->
        * **Average Tokens/s:** TBD
        * **Average Time to First Token:** TBD
        * **Total Tokens Generated:** TBD
        <!--SUMMARY_END-->

        ## Qualitative Analysis

        *(Manual grading and analysis of the responses is required to determine the final letter grade.)*

        ---

        """
    ).lstrip()

    report_path.write_text(header, encoding="utf-8")
    return report_path


def append_test_result(
    report_path: Path,
    prompt_info: Dict[str, str],
    result: Dict[str, object],
    index: int,
) -> None:
    """Append a single test section to the markdown report."""
    block_content = render_test_block(prompt_info, result, index)

    slug_base = re.sub(r"[^A-Za-z0-9._-]+", "-", prompt_info.get("title", f"test-{index}")).strip("-")
    if not slug_base:
        slug_base = f"test-{index}"
    slug_hash = hashlib.sha1(slug_base.encode("utf-8")).hexdigest()[:8]
    truncated_slug = slug_base[:48]
    title_slug = f"{truncated_slug}-{slug_hash}"
    temp_file = TEMP_DIR / f"{index:03d}_{title_slug}.md"

    try:
        temp_file.write_text(block_content, encoding="utf-8")
    except OSError:
        pass

    block_text = temp_file.read_text(encoding="utf-8") if temp_file.exists() else block_content
    if has_unclosed_code_block(block_text):
        block_text = block_text.rstrip() + "\n```\n"

    separator = "\n\n---\n\n"
    existing_tail = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    needs_separator = existing_tail and not existing_tail.endswith(separator)

    with report_path.open("a", encoding="utf-8") as report_file:
        if existing_tail and has_unclosed_code_block(existing_tail):
            report_file.write("\n```\n\n")
        if needs_separator and existing_tail:
            report_file.write(separator)
        report_file.write(block_text)

    if temp_file.exists():
        try:
            temp_file.unlink()
        except OSError:
            pass


def finalize_report_summary(report_path: Path, results: List[Dict[str, object]]) -> None:
    """Update the performance summary placeholder once all tests have run."""
    valid_results = [r for r in results if "error" not in r]

    if valid_results:
        total_tok_s = sum(r["metrics"]["tokens_per_second"] for r in valid_results)
        total_ttft = sum(r["metrics"]["time_to_first_token"] for r in valid_results)
        total_tokens = sum(r["metrics"]["total_tokens"] for r in valid_results)
        avg_tok_s = round(total_tok_s / len(valid_results), 2)
        avg_ttft = round(total_ttft / len(valid_results), 2)
    else:
        avg_tok_s = avg_ttft = total_tokens = 0

    summary_block = textwrap.dedent(
        f"""
        * **Average Tokens/s:** {avg_tok_s}
        * **Average Time to First Token:** {avg_ttft}s
        * **Total Tokens Generated:** {total_tokens}
        """
    ).strip()

    content = report_path.read_text(encoding="utf-8")
    updated_content = re.sub(
        r"<!--SUMMARY_START-->.*?<!--SUMMARY_END-->",
        f"<!--SUMMARY_START-->\n{summary_block}\n<!--SUMMARY_END-->",
        content,
        flags=re.DOTALL,
    )
    report_path.write_text(updated_content, encoding="utf-8")
