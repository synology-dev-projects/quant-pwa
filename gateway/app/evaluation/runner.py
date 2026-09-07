"""
Quant AI Agent Evaluation Runner CLI (AGENT-01)
Command-line runner and reporting engine for Quant AI agent evaluation.
Supports deterministic mock benchmarks ($0.00 cost) and live model benchmarks.

Usage:
  python -m app.evaluation.runner
  python -m app.evaluation.runner --fuzz
  python -m app.evaluation.runner --category routing
  python -m app.evaluation.runner --strict
  python -m app.evaluation.runner --live
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Optional, List, Tuple

# Ensure stdout/stderr handles UTF-8 on Windows consoles safely
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.evaluation.models import EvaluationCategory, BenchmarkReport
from app.evaluation.dataset import get_golden_dataset, generate_fuzzed_test_cases
from app.evaluation.evaluator import AgentEvaluator


# Terminal ANSI Colors
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_GREEN = "\033[92m"
C_RED = "\033[91m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_DIM = "\033[2m"


def format_report_terminal(report: BenchmarkReport) -> str:
    lines = []
    lines.append("================================================================================")
    lines.append(f"{C_BOLD}{C_CYAN}  QUANT AI AGENT BENCHMARK EVALUATION HARNESS (AGENT-01){C_RESET}")
    lines.append(f"  Benchmark ID: {C_BOLD}{report.benchmark_id}{C_RESET} | Mode: {C_BOLD}{report.mode.upper()}{C_RESET} | Timestamp: {report.timestamp[:19]}")
    lines.append("================================================================================")
    lines.append(f"{'CATEGORY':<22} | {'CASES':<6} | {'PASS':<6} | {'FAIL':<6} | {'ACCURACY':<9} | {'GATE':<8}")
    lines.append("-----------------------+--------+--------+--------+-----------+---------")
    
    for cat_name, score in report.category_scores.items():
        gate_str = f"{C_GREEN}[PASS]{C_RESET}" if score.gate_passed else f"{C_RED}[FAIL]{C_RESET}"
        acc_str = f"{score.accuracy_pct:.1f}%"
        if score.accuracy_pct >= score.threshold_pct:
            acc_colored = f"{C_GREEN}{acc_str:<9}{C_RESET}"
        else:
            acc_colored = f"{C_RED}{acc_str:<9}{C_RESET}"
            
        lines.append(
            f"{cat_name:<22} | {score.total:<6} | {score.passed:<6} | {score.failed:<6} | {acc_colored} | {gate_str}"
        )
        
    lines.append("-----------------------+--------+--------+--------+-----------+---------")
    verdict_colored = f"{C_GREEN}[PASSED]{C_RESET}" if report.verdict == "PASSED" else f"{C_RED}[FAILED]{C_RESET}"
    lines.append(
        f"{C_BOLD}{'OVERALL TOTALS':<22} | {report.total_cases:<6} | {report.passed_cases:<6} | {report.failed_cases:<6} | {report.overall_accuracy_pct:.1f}%{'':<4} | {verdict_colored}{C_RESET}"
    )
    lines.append("================================================================================")

    # Violations breakdown
    failed_results = [r for r in report.results if not r.passed]
    if failed_results:
        lines.append(f"\n{C_BOLD}{C_RED}FAILED TEST CASES & VIOLATIONS ({len(failed_results)}):{C_RESET}")
        for r in failed_results:
            lines.append(f"  [X] {C_BOLD}{r.case_id}{C_RESET} [{r.category.value}] - {r.name}:")
            for v in r.violations:
                lines.append(f"      {C_RED}* {v}{C_RESET}")
    else:
        lines.append(f"\n{C_BOLD}{C_GREEN}[OK] All quality gates & invariants satisfied. Zero regressions detected.{C_RESET}")

    lines.append("================================================================================\n")
    return "\n".join(lines)


def format_report_markdown(report: BenchmarkReport) -> str:
    lines = []
    lines.append(f"# Quant AI Agent Benchmark Report: `{report.benchmark_id}`")
    lines.append(f"- **Execution Mode**: `{report.mode}`")
    lines.append(f"- **Timestamp**: `{report.timestamp}`")
    lines.append(f"- **Overall Verdict**: **`{report.verdict}`**")
    lines.append(f"- **Overall Accuracy**: `{report.overall_accuracy_pct}%` ({report.passed_cases}/{report.total_cases} passed)")
    lines.append("\n## Category Scorecards\n")
    lines.append("| Category | Total | Passed | Failed | Accuracy | Gate Threshold | Gate Status |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    for cat_name, score in report.category_scores.items():
        gate_icon = "[PASS]" if score.gate_passed else "[FAIL]"
        lines.append(
            f"| `{cat_name}` | {score.total} | {score.passed} | {score.failed} | **{score.accuracy_pct}%** | {score.threshold_pct}% | {gate_icon} |"
        )

    lines.append("\n## Test Case Details\n")
    lines.append("| ID | Category | Name | Status | Duration (ms) | Violations |")
    lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for r in report.results:
        status_str = "PASS" if r.passed else "FAIL"
        violations_str = "<br>".join(r.violations) if r.violations else "-"
        lines.append(f"| `{r.case_id}` | `{r.category.value}` | {r.name} | {status_str} | {r.duration_ms:.1f} | {violations_str} |")

    return "\n".join(lines)


def run_evaluation(
    category_filter: Optional[str] = None,
    include_fuzz: bool = False,
    live_mode: bool = False,
    strict: bool = False,
    output_dir: Optional[str] = None
) -> Tuple[BenchmarkReport, int]:
    """
    Executes the agent evaluation benchmark suite and writes output reports.
    Returns (report, exit_code).
    """
    cat_enum = None
    if category_filter and category_filter.lower() != "all":
        try:
            cat_enum = EvaluationCategory(category_filter.lower())
        except ValueError:
            print(f"[ERROR] Unknown category: {category_filter}. Available: {[e.value for e in EvaluationCategory]}", file=sys.stderr)
            return None, 1

    dataset = get_golden_dataset(cat_enum)
    if include_fuzz:
        fuzzed = generate_fuzzed_test_cases()
        if cat_enum:
            fuzzed = [c for c in fuzzed if c.category == cat_enum]
        dataset.extend(fuzzed)

    evaluator = AgentEvaluator(live_mode=live_mode, strict=strict)
    report = evaluator.run_suite(dataset)
    report.summary_markdown = format_report_markdown(report)

    # Determine report directory
    target_out_dir = Path(output_dir) if output_dir else Path("evaluation_reports")
    target_out_dir.mkdir(parents=True, exist_ok=True)

    # Write JSON and Markdown reports
    ts_slug = report.benchmark_id.replace("BM-", "")
    json_path = target_out_dir / f"eval_report_{ts_slug}.json"
    md_path = target_out_dir / f"eval_report_{ts_slug}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report.summary_markdown)

    exit_code = 0 if report.verdict == "PASSED" else 1
    return report, exit_code


def main():
    parser = argparse.ArgumentParser(description="Quant AI Agent Evaluation & Benchmarking Harness (AGENT-01)")
    parser.add_argument("--category", default="all", help="Category filter: routing, tool_accuracy, safety_directives, multi_turn, latency_sla, all")
    parser.add_argument("--fuzz", action="store_true", help="Include dynamic synthetic fuzzing test cases")
    parser.add_argument("--live", action="store_true", help="Execute live Gemini API calls instead of deterministic mock")
    parser.add_argument("--strict", action="store_true", help="Enforce 95%% minimum accuracy across all categories")
    parser.add_argument("--output", default="evaluation_reports", help="Directory to save evaluation reports")
    parser.add_argument("--json-only", action="store_true", help="Emit raw JSON benchmark report to stdout")

    args = parser.parse_args()

    report, exit_code = run_evaluation(
        category_filter=args.category,
        include_fuzz=args.fuzz,
        live_mode=args.live,
        strict=args.strict,
        output_dir=args.output
    )

    if not report:
        sys.exit(1)

    if args.json_only:
        print(report.model_dump_json(indent=2))
    else:
        print(format_report_terminal(report))
        print(f"Reports saved to: {args.output}/ (eval_report_{report.benchmark_id.replace('BM-', '')}.json & .md)")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
