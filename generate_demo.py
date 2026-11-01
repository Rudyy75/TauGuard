"""Render a terminal-style SVG summary from a recorded Ollama run artifact."""

import argparse
from io import StringIO
import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from generate_dashboard import latest_result


def render(input_path: Path, output_path: Path) -> None:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    meta = data.get("metadata", {})
    models = data.get("models", {})
    # Keep Rich's Unicode output off the legacy Windows terminal encoding.
    console = Console(file=StringIO(), record=True, width=104, highlight=False, force_terminal=True)
    console.print(Panel("[bold green]TauGuard[/bold green] · Local CRM agent benchmark", border_style="cyan"))
    console.print(f"[dim]Recorded artifact: {input_path} | {meta.get('tasks_count', 0)} tasks × {meta.get('num_trials', 1)} trials[/dim]\n")

    table = Table(title="Target-State vs Policy-Aware Grader", border_style="dim")
    table.add_column("Model", style="bold")
    table.add_column("Target-state", justify="right")
    table.add_column("Patched", justify="right")
    table.add_column("Patched pass-k", justify="right")
    table.add_column("Latency / task", justify="right")
    for key, model in models.items():
        info = model.get("info", {})
        evaluations = model.get("evaluations", {})
        baseline = evaluations.get("tau_bench", {}).get("metrics", {})
        patched = evaluations.get("patched", {}).get("metrics", {})
        latency = patched.get("mean_latency_sec", baseline.get("mean_latency_sec", 0)) or 0
        table.add_row(
            str(info.get("name", key)),
            f"{baseline.get('pass_rate_pct', 0):.2f}%",
            f"{patched.get('pass_rate_pct', 0):.2f}%",
            f"{patched.get('pass_k_pct', 0):.2f}%",
            f"{latency:.2f}s",
        )
    console.print(table)
    console.print(Panel(
        "The patched grader adds activity, authorization/policy, and state-diff checks.\n"
        "Response grading uses Gemini only when configured; otherwise it uses keyword fallback.",
        title="What this measures", border_style="blue",
    ))
    console.print("[dim]Exploratory results for TauGuard's custom CRM task suite. Not official τ-bench results.[/dim]")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(console.export_svg(title="TauGuard recorded local benchmark report"), encoding="utf-8")
    print(f"Wrote {output_path} from {input_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Recorded run JSON; defaults to the newest Ollama run")
    parser.add_argument("--output", default="docs/demo.svg")
    args = parser.parse_args()
    render(Path(args.input) if args.input else latest_result(), Path(args.output))


if __name__ == "__main__":
    main()
