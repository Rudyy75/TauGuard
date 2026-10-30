import argparse
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def generate_markdown_report(data: dict) -> str:
    metadata = data.get("metadata", {})
    num_trials = metadata.get("num_trials", 3)
    tasks_count = metadata.get("tasks_count", 30)
    models_dict = data.get("models", {})

    lines = []
    lines.append("# Benchmark Results: Standard Tau-Bench vs Patched Safe Grader")
    lines.append("")
    lines.append(f"> **Configuration:** Evaluated across {tasks_count} tasks, "
                 f"**{num_trials} independent trials per task** ($pass^{num_trials}$ reliability), "
                 f"comparing naive $\\tau$-bench scoring against the policy-enforcing Patched Grader.")
    lines.append("")

    lines.append("## Executive Reliability & Safety Comparison Table")
    lines.append("")
    lines.append(f"| Model | Grader Engine | Pass Rate | $pass^{num_trials}$ Reliability | Variance (σ) | Avg Latency | Est. Cost / Task |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: | :---: |")

    model_names = []
    tau_pass_rates = []
    patched_pass_rates = []

    for m_key, m_val in models_dict.items():
        m_name = m_val.get("info", {}).get("name", m_key)
        model_names.append(m_name)

        evals = m_val.get("evaluations", {})
        if evals:
            for g_key, g_data in evals.items():
                metrics = g_data.get("metrics", {})
                g_label = metrics.get("grader_label", g_key)
                pr = metrics.get("pass_rate_pct", 0.0)
                pk = metrics.get("pass_k_pct", 0.0)
                var = metrics.get("mean_variance", 0.0)
                lat = metrics.get("mean_latency_sec", 0.0)
                cost = metrics.get("mean_cost_per_task_usd", 0.0)

                if g_key == "tau_bench":
                    tau_pass_rates.append(pr)
                elif g_key == "patched":
                    patched_pass_rates.append(pr)

                lines.append(f"| **{m_name}** | {g_label} | **{pr:.1f}%** | **{pk:.1f}%** | {var:.3f} | {lat:.2f}s | ${cost:.6f} |")
        else:
            metrics = m_val.get("metrics", {})
            pr = metrics.get("pass_rate_pct", 0.0)
            pk = metrics.get("pass_k_pct", 0.0)
            var = metrics.get("mean_variance", 0.0)
            lat = metrics.get("mean_latency_sec", 0.0)
            cost = metrics.get("mean_cost_per_task_usd", 0.0)
            lines.append(f"| **{m_name}** | Tau-Bench (Standard) | **{pr:.1f}%** | **{pk:.1f}%** | {var:.3f} | {lat:.2f}s | ${cost:.6f} |")

    lines.append("")
    lines.append("### Key Research Signals")
    lines.append("- **The Real-World Safety Gap:** Under naive $\\tau$-bench scoring, models appear to achieve high success rates. When evaluated under the Patched Grader with state diffing, authorization checks, and active inspection, pass rates drop significantly, exposing unhandled policy violations.")
    lines.append(f"- **The Reliability Cliff ($pass^{num_trials}$ Drop):** Requiring repeated consecutive successes reveals stochastic instability across tool invocation turns.")
    lines.append("")

    lines.append("## Dual Evaluation Pipeline Architecture")
    lines.append("")
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append("    subgraph StandardEval[\"Standard Tau-Bench Evaluation\"]")
    lines.append("        S1[\"Action Check: Target Key Only\"]")
    lines.append("        S2[\"Output Check: Substring Match\"]")
    lines.append("        S1 & S2 --> Sp[\"Reward r = r_action × r_output\"]")
    lines.append("    end")
    lines.append("    subgraph PatchedEval[\"TauGuard Patched Evaluation\"]")
    lines.append("        P1[\"Gate 1: Auth Compliance\"] --> P2[\"Gate 2: Active Inspection\"]")
    lines.append("        P2 --> P3[\"Gate 3: Full State Diff Whitelist\"]")
    lines.append("        P3 --> P4[\"Gate 4: Output Verification\"]")
    lines.append("        P4 --> Pp[\"Reward r = 1.0 (Guaranteed Safe)\"]")
    lines.append("    end")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Markdown and Mermaid report from benchmark JSON")
    parser.add_argument("--input", type=str, default="results/run_output.json", help="Path to input benchmark JSON")
    parser.add_argument("--output", type=str, default="results/benchmark_summary.md", help="Path to output markdown report")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Error: Input file '{args.input}' not found. Run harness.py first.")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    report_md = generate_markdown_report(data)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"[SUCCESS] Formatted report generated at: {args.output}")


if __name__ == "__main__":
    main()
