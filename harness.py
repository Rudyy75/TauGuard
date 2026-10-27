"""
Tau-Bench CRM Harness CLI (Day 2)
Logs pass rate, pass^k reliability, variance across trials, latency, token consumption, and cost.
"""

import argparse
import json
import os
import sys
from pathlib import Path
import yaml
from rich.console import Console
from rich.table import Table

# Ensure Windows terminal doesn't crash on utf-8 characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

console = Console(highlight=False)

from src.envs.mock_retail import BENCHMARK_TASKS
from src.agents.tool_agent import OpenAIToolAgent
from src.harness.runner import run_benchmark_suite
from src.harness.metrics import aggregate_model_metrics


def load_config(config_path: str = "configs/models.yaml") -> dict:
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Agentic CRM Benchmark Evaluation Harness")
    parser.add_argument("--trials", type=int, default=3, help="Number of trials per task (default: 3)")
    parser.add_argument("--models", nargs="+", default=["qwen2.5-7b", "llama-3.1-8b", "mistral-7b"],
                        help="Model keys to benchmark from models.yaml")
    parser.add_argument("--output", type=str, default="results/run_output.json", help="Destination path for raw output JSON")
    parser.add_argument("--mock", action="store_true", help="Force deterministic simulation mode (zero cost/offline)")
    parser.add_argument("--config", type=str, default="configs/models.yaml", help="Path to models YAML config")
    args = parser.parse_args()

    cfg = load_config(args.config)
    models_cfg = cfg.get("models", {})

    console.print(f"[bold cyan]====================================================================[/bold cyan]")
    console.print(f"[bold green]   CRM AGENTIC BENCHMARK HARNESS (Tau-Bench Specification)[/bold green]")
    console.print(f"[bold cyan]====================================================================[/bold cyan]")
    console.print(f"[*] Trials per task: [bold]{args.trials}[/bold]")
    console.print(f"[*] Models selected: [bold]{', '.join(args.models)}[/bold]")
    console.print(f"[*] Simulation fallback mode: [bold]{args.mock}[/bold]\n")

    Path(os.path.dirname(args.output) or ".").mkdir(parents=True, exist_ok=True)

    all_models_summary = []
    full_benchmark_record = {
        "metadata": {
            "num_trials": args.trials,
            "tasks_count": len(BENCHMARK_TASKS),
            "mock_mode": args.mock
        },
        "models": {}
    }

    for m_key in args.models:
        m_info = models_cfg.get(m_key, {
            "name": m_key.upper(),
            "model_id": m_key,
            "cost_per_million_input": 0.15,
            "cost_per_million_output": 0.60
        })

        console.print(f"[bold yellow]>>> Evaluating Model: {m_info.get('name', m_key)}[/bold yellow]")

        agent = OpenAIToolAgent(
            name=m_info.get("name", m_key),
            model_id=m_info.get("model_id", m_key),
            mock_fallback=args.mock
        )

        task_results = run_benchmark_suite(
            agent=agent,
            tasks=BENCHMARK_TASKS,
            num_trials=args.trials,
            verbose=True
        )

        cost_cfg = {
            "cost_per_m_input": m_info.get("cost_per_million_input", 0.15),
            "cost_per_m_output": m_info.get("cost_per_million_output", 0.60)
        }

        metrics = aggregate_model_metrics(task_results, k_trials=args.trials, cost_config=cost_cfg)
        metrics["model_key"] = m_key
        metrics["model_name"] = m_info.get("name", m_key)
        all_models_summary.append(metrics)

        full_benchmark_record["models"][m_key] = {
            "info": m_info,
            "metrics": metrics,
            "task_results": task_results
        }
        console.print()

    # Save complete JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(full_benchmark_record, f, indent=2)

    console.print(f"[bold green][SUCCESS] Benchmark complete. Raw logs saved to: {args.output}[/bold green]\n")

    # Render summary table
    table = Table(title="Agentic CRM Benchmark Results (Multi-Trial Evaluation)")
    table.add_column("Model", style="bold white")
    table.add_column("Pass Rate (%)", style="cyan", justify="right")
    table.add_column(f"pass^{args.trials} (%)", style="bold green", justify="right")
    table.add_column("Variance (σ)", style="magenta", justify="right")
    table.add_column("Avg Latency (s)", style="yellow", justify="right")
    table.add_column("Avg Tokens", style="blue", justify="right")
    table.add_column("Est. Cost/Task ($)", style="white", justify="right")

    for s in all_models_summary:
        table.add_row(
            s["model_name"],
            f"{s['pass_rate_pct']:.1f}%",
            f"{s['pass_k_pct']:.1f}%",
            f"{s['mean_variance']:.3f}",
            f"{s['mean_latency_sec']:.2f}s",
            f"{s['mean_tokens_per_task']:.0f}",
            f"${s['mean_cost_per_task_usd']:.6f}"
        )

    console.print(table)


if __name__ == "__main__":
    main()
