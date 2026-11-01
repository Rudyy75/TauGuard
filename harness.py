import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
import yaml
from rich.console import Console
from rich.table import Table

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

console = Console(highlight=False)

from src.envs.mock_retail import BENCHMARK_TASKS
from src.envs.grader import TauBenchGrader
from src.envs.patched_grader import PatchedTauBenchGrader
from src.envs.task_generator import generate_crm_benchmark
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
    parser.add_argument("--models", nargs="+", default=["qwen3-8b", "llama-3.1-8b", "mistral-7b"],
                        help="Ollama model keys from configs/models.yaml")
    parser.add_argument("--output", type=str, default=None, help="New JSON output path (existing files are never overwritten)")
    parser.add_argument("--mock", action="store_true", help="Force deterministic simulation mode (zero cost/offline)")
    parser.add_argument("--config", type=str, default="configs/models.yaml", help="Path to models YAML config")
    parser.add_argument("--grader", choices=["baseline", "patched", "both"], default="both",
                        help="Compare the target-state baseline, stricter patched grader, or both")
    parser.add_argument("--tasks-count", type=int, choices=[6, 10, 30], default=10,
                        help="Number of tasks: 6 canonical, 10 expanded (default), or 30")
    args = parser.parse_args()

    cfg = load_config(args.config)
    models_cfg = cfg.get("models", {})
    unknown_models = [key for key in args.models if key not in models_cfg]
    if unknown_models:
        parser.error(f"Unknown model key(s) in {args.config}: {', '.join(unknown_models)}")
    non_local = [key for key in args.models if models_cfg[key].get("provider") != "local"]
    if non_local:
        parser.error(f"Only configured local Ollama models are supported: {', '.join(non_local)}")

    # Select task suite
    if args.tasks_count == 6:
        tasks = BENCHMARK_TASKS
        initial_db = None
    else:
        tasks, initial_db = generate_crm_benchmark(num_tasks=args.tasks_count)

    graders_to_run = []
    if args.grader in ("baseline", "both"):
        graders_to_run.append(("Target-State Baseline", TauBenchGrader, "tau_bench"))
    if args.grader in ("patched", "both"):
        graders_to_run.append(("Patched (Safe)", PatchedTauBenchGrader, "patched"))

    console.print("[bold cyan]====================================================================[/bold cyan]")
    console.print("[bold green]   CRM AGENTIC BENCHMARK HARNESS (TauGuard Grader Comparison)[/bold green]")
    console.print("[bold cyan]====================================================================[/bold cyan]")
    console.print(f"[*] Trials per task: [bold]{args.trials}[/bold]")
    console.print(f"[*] Models selected: [bold]{', '.join(args.models)}[/bold]")
    console.print(f"[*] Tasks count:     [bold]{len(tasks)}[/bold]")
    console.print(f"[*] Grader modes:    [bold]{args.grader}[/bold]")
    run_mode = "deterministic_mock" if args.mock else "ollama_live"
    console.print(f"[*] Run mode: [bold]{run_mode}[/bold]\n")

    graders_for_run = [g_cls for _, g_cls, _ in graders_to_run]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output or f"results/{run_mode}_{timestamp}.json"
    if os.path.exists(output_path):
        raise FileExistsError(f"Refusing to overwrite existing results: {output_path}")

    Path(os.path.dirname(output_path) or ".").mkdir(parents=True, exist_ok=True)

    summary_rows = []
    full_benchmark_record = {
        "metadata": {
            "num_trials": args.trials,
            "tasks_count": len(tasks),
            "run_mode": run_mode,
            "grader_mode": args.grader,
            "created_at_utc": timestamp,
            "customer_simulator": "deterministic rule-based simulator",
            "fallback_enabled": bool(args.mock),
            "task_seed": 42 if args.tasks_count in (10, 30) else None
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
            temperature=m_info.get("temperature", 0.0),
            mock_fallback=args.mock
        )

        cost_cfg = {
            "cost_per_m_input": 0.0,
            "cost_per_m_output": 0.0
        }

        full_benchmark_record["models"][m_key] = {"info": m_info, "evaluations": {}}

        shared_task_results = run_benchmark_suite(
            agent=agent,
            tasks=tasks,
            num_trials=args.trials,
            verbose=False,
            grader_cls=graders_for_run,
            initial_db=initial_db
        )

        for g_label, g_cls, g_key in graders_to_run:
            console.print(f"  -> Scoring with: [cyan]{g_label}[/cyan]")
            task_results = shared_task_results

            metrics = aggregate_model_metrics(task_results, k_trials=args.trials, cost_config=cost_cfg, grader_key=g_key)
            metrics["model_name"] = m_info.get("name", m_key)
            metrics["grader_label"] = g_label
            metrics["valid_for_comparison"] = (not args.mock and metrics["failed_model_calls"] == 0)

            full_benchmark_record["models"][m_key]["evaluations"][g_key] = {
                "metrics": metrics,
                "task_results": task_results
            }

            summary_rows.append(metrics)

        console.print()

    # Save output JSON
    with open(output_path, "x", encoding="utf-8") as f:
        json.dump(full_benchmark_record, f, indent=2)

    console.print(f"[bold green][SUCCESS] Run complete. Saved to: {output_path}[/bold green]\n")

    # Render results table
    table = Table(title="TauGuard Custom Grader Comparison")
    table.add_column("Model", style="bold white")
    table.add_column("Grader Engine", style="cyan")
    table.add_column("Pass Rate (%)", style="bold yellow", justify="right")
    table.add_column(f"pass^{args.trials} (%)", style="bold green", justify="right")
    table.add_column("Variance (σ)", style="magenta", justify="right")
    table.add_column("Avg Latency", style="blue", justify="right")
    table.add_column("Valid live run", style="bold white")
    table.add_column("Est. Cost/Task", style="white", justify="right")

    for row in summary_rows:
        table.add_row(
            row["model_name"],
            row["grader_label"],
            f"{row['pass_rate_pct']:.1f}%",
            f"{row['pass_k_pct']:.1f}%",
            f"{row['mean_variance']:.3f}",
            f"{row['mean_latency_sec']:.2f}s",
            "yes" if row["valid_for_comparison"] else "no",
            f"${row['mean_cost_per_task_usd']:.6f}"
        )

    console.print(table)


if __name__ == "__main__":
    main()
