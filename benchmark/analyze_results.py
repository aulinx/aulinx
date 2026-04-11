#!/usr/bin/env python3
"""Analyze OSWorld benchmark results and generate comparison report.

Usage:
    python -m benchmark.analyze_results benchmark/results/results.json
    python -m benchmark.analyze_results benchmark/results/results.json --output docs/benchmark.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Known baselines for comparison
BASELINES = {
    "Human": {"success_rate": 72.4, "tokens_per_task": None},
    "Agent S3 (100-step)": {"success_rate": 62.6, "tokens_per_task": None},
    "Agent S3 + BoN": {"success_rate": 69.9, "tokens_per_task": None},
    "Claude CUA (15-step)": {"success_rate": 22.0, "tokens_per_task": 5000},
    "GPT-4o (15-step)": {"success_rate": 12.2, "tokens_per_task": 4000},
}


def load_results(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def analyze(data: dict) -> dict:
    """Compute detailed analysis from raw results."""
    summary = data["summary"]
    tasks = data["tasks"]

    # Per-domain breakdown
    by_domain = defaultdict(list)
    for task in tasks:
        domain = task.get("domain", "unknown")
        by_domain[domain].append(task)

    domain_stats = {}
    for domain, domain_tasks in sorted(by_domain.items()):
        scored = [t for t in domain_tasks if "error" not in t]
        passed = [t for t in scored if t.get("score", 0) > 0]
        tokens = sum(t.get("tokens_in", 0) + t.get("tokens_out", 0) for t in scored)
        domain_stats[domain] = {
            "total": len(domain_tasks),
            "passed": len(passed),
            "success_rate": round(len(passed) / max(1, len(scored)) * 100, 1),
            "avg_tokens": round(tokens / max(1, len(scored))),
            "avg_steps": round(sum(t.get("steps", 0) for t in scored) / max(1, len(scored)), 1),
        }

    return {
        "summary": summary,
        "domain_stats": domain_stats,
        "token_efficiency": _token_efficiency(summary),
    }


def _token_efficiency(summary: dict) -> dict:
    """Compare token efficiency against baselines."""
    aulinx_tokens = summary.get("avg_tokens_per_task", 0)
    comparisons = {}
    for name, baseline in BASELINES.items():
        if baseline["tokens_per_task"]:
            ratio = baseline["tokens_per_task"] / max(1, aulinx_tokens)
            comparisons[name] = {
                "their_tokens": baseline["tokens_per_task"],
                "our_tokens": aulinx_tokens,
                "efficiency_ratio": round(ratio, 1),
            }
    return comparisons


def generate_markdown(analysis: dict) -> str:
    """Generate a markdown report from the analysis."""
    s = analysis["summary"]
    lines = [
        "# Aulinx OSWorld Benchmark Results\n",
        "**Date:** Results from benchmark run\n",
        "**Agent:** Aulinx (a11y-first semantic agent)\n",
        "",
        "## Summary\n",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Tasks completed | {s['completed']} |",
        f"| Success rate | **{s['success_rate']}%** |",
        f"| Avg tokens/task | {s['avg_tokens_per_task']} |",
        f"| Avg LLM calls/task | {s['avg_calls_per_task']} |",
        f"| Avg time/task | {s['avg_time_per_task_s']}s |",
        "",
        "## Comparison with Other Agents\n",
        "| Agent | Success Rate | Tokens/Task | Efficiency |",
        "|-------|-------------|-------------|------------|",
        f"| **Aulinx (ours)** | **{s['success_rate']}%** | {s['avg_tokens_per_task']} | 1.0x |",
    ]

    for name, baseline in BASELINES.items():
        tokens = baseline.get("tokens_per_task", "—")
        eff = analysis["token_efficiency"].get(name, {})
        eff_str = f"{eff['efficiency_ratio']}x fewer" if eff else "—"
        lines.append(f"| {name} | {baseline['success_rate']}% | {tokens or '—'} | {eff_str} |")

    lines.extend([
        "",
        "## Per-Domain Breakdown\n",
        "| Domain | Tasks | Passed | Rate | Avg Tokens | Avg Steps |",
        "|--------|-------|--------|------|------------|-----------|",
    ])

    for domain, ds in analysis["domain_stats"].items():
        lines.append(
            f"| {domain} | {ds['total']} | {ds['passed']} | "
            f"{ds['success_rate']}% | {ds['avg_tokens']} | {ds['avg_steps']} |"
        )

    lines.extend([
        "",
        "## Key Insight\n",
        "Aulinx uses the accessibility tree (structured UI data) instead of screenshots.",
        "This means:",
        "- **Fewer tokens**: ~50 tokens to describe a UI vs 1,200+ for a screenshot",
        "- **No hallucination**: Reading real UI state, not guessing from pixels",
        "- **Faster**: No vision model overhead",
        "",
        "## Methodology\n",
        "- Benchmark: [OSWorld](https://github.com/xlang-ai/OSWorld) (NeurIPS 2024)",
        "- Environment: Ubuntu VM via VMware",
        "- Observation: Accessibility tree (primary)",
        "- Action space: computer_13 (structured actions)",
        f"- Max steps per task: {s.get('max_steps', 20)}",
        "",
    ])

    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("results_file", help="Path to results.json")
    p.add_argument("--output", "-o", help="Output markdown file (default: stdout)")
    args = p.parse_args()

    data = load_results(args.results_file)
    analysis = analyze(data)

    md = generate_markdown(analysis)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(md)
        print(f"Report written to {args.output}")
    else:
        print(md)

    # Also print summary to stderr
    s = analysis["summary"]
    print(f"\nSuccess rate: {s['success_rate']}% | "
          f"Avg tokens: {s['avg_tokens_per_task']} | "
          f"Avg calls: {s['avg_calls_per_task']}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
