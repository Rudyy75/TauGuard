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
    run_mode = metadata.get("run_mode", "unknown / legacy artifact")
    lines = [
        "# TauGuard Evaluation Results",
        "",
        f"> Run mode: {run_mode} · Tasks: {metadata.get('tasks_count', '?')} · "
        f"Trials per task: {metadata.get('num_trials', '?')}",
        "> Custom in-memory CRM benchmark; this is not the official tau-bench environment.",
        "",
        "| Model | Grader | Pass rate | pass-k | Variation | Latency | Failed calls | Live evidence |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for model_key, model in data.get("models", {}).items():
        name = model.get("info", {}).get("name", model_key)
        for grader_key, evaluation in model.get("evaluations", {}).items():
            metrics = evaluation.get("metrics", {})
            valid = run_mode == "ollama_live" and metrics.get("valid_for_comparison", False)
            lines.append(
                f"| {name} | {metrics.get('grader_label', grader_key)} | "
                f"{metrics.get('pass_rate_pct', 0):.1f}% | "
                f"{metrics.get('pass_k_pct', 0):.1f}% | "
                f"{metrics.get('mean_variance', 0):.3f} | "
                f"{metrics.get('mean_latency_sec', 0):.2f}s | "
                f"{metrics.get('failed_model_calls', 0)} | {'yes' if valid else 'no'} |"
            )
    lines.extend([
        "",
        "Pass-k is the share of tasks that pass on every one of the first k trials. Local inference cost is zero.",
        "The customer simulator is deterministic. The patched grader uses a keyword heuristic, not semantic judging.",
        "Treat these as exploratory results on this task suite, not a general model ranking.",
    ])
    if run_mode != "ollama_live":
        lines.insert(3, "> Not a live-model result. Only successful ollama_live runs count as model evidence.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate a concise report from a TauGuard run JSON")
    parser.add_argument("--input", type=str, required=True, help="Specific run JSON to summarize")
    parser.add_argument("--output", type=str, required=True, help="Markdown output path")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"[!] Input file not found: {args.input}")
        sys.exit(1)
    with open(args.input, "r", encoding="utf-8") as f:
        report = generate_markdown_report(json.load(f))
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "x", encoding="utf-8") as f:
        f.write(report)
    print(f"[SUCCESS] Report generated at: {args.output}")


if __name__ == "__main__":
    main()
