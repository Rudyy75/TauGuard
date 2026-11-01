"""Build a dependency-free HTML report from a TauGuard Ollama run."""

import argparse
import html
import json
from pathlib import Path
import webbrowser


def latest_result() -> Path:
    candidates = sorted(Path("results").glob("ollama_live_*.json"))
    if not candidates:
        raise SystemExit("No results/ollama_live_*.json run artifacts found.")
    return candidates[-1]


def build_html(data: dict, source: str) -> str:
    metadata = data.get("metadata", {})
    models = data.get("models", {})
    task_count = int(metadata.get("tasks_count", 0))
    trials = int(metadata.get("num_trials", 1))
    episode_count = len(models) * task_count * trials
    failed = sum(
        int(metric.get("failed_model_calls", 0))
        for model in models.values()
        for evaluation in model.get("evaluations", {}).values()
        for metric in [evaluation.get("metrics", {})]
        if metric.get("grader_label") in (None, "Target-State Baseline")
    )
    valid = metadata.get("run_mode") == "ollama_live" and all(
        evaluation.get("metrics", {}).get("valid_for_comparison", False)
        for model in models.values()
        for key, evaluation in model.get("evaluations", {}).items()
        if key in ("tau_bench", "patched")
    ) and failed == 0

    rows = []
    for key, model in models.items():
        info = model.get("info", {})
        evaluations = model.get("evaluations", {})
        baseline = evaluations.get("tau_bench", {}).get("metrics", {})
        patched = evaluations.get("patched", {}).get("metrics", {})
        base_rate = float(baseline.get("pass_rate_pct", 0))
        patched_rate = float(patched.get("pass_rate_pct", 0))
        latency = float(patched.get("mean_latency_sec", baseline.get("mean_latency_sec", 0)) or 0)
        name = html.escape(str(info.get("name", key)))
        rows.append(
            f"<tr><th>{name}</th><td>{base_rate:.2f}%</td><td>{patched_rate:.2f}%</td>"
            f"<td>{patched_rate-base_rate:+.2f} pp</td><td>{float(patched.get('pass_k_pct', 0)):.2f}%</td>"
            f"<td>{latency:.2f} s</td></tr>"
        )

    status = "VERIFIED RUN METADATA" if valid else "CHECK RUN METADATA"
    badge = "verified" if valid else "unverified"
    created = html.escape(str(metadata.get("created_at_utc", "unknown")))
    source_label = html.escape(source)
    table_rows = "\n".join(rows) or "<tr><td colspan='6'>No model metrics found.</td></tr>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TauGuard | Agent benchmark report</title>
<style>
:root{{--bg:#0d1117;--panel:#161b22;--line:#30363d;--text:#e6edf3;--muted:#8b949e;--green:#3fb950;--blue:#58a6ff;--amber:#d29922}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px/1.6 system-ui,Segoe UI,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:42px 22px 60px}}h1{{font-size:clamp(2rem,5vw,3.2rem);margin:0}}h2{{margin:38px 0 12px;font-size:1.25rem}}p{{color:var(--muted)}}.kicker{{color:var(--green);font:600 .8rem ui-monospace,monospace;letter-spacing:.12em}}
.status{{display:inline-block;padding:3px 9px;border:1px solid var(--line);border-radius:99px;color:{'var(--green)' if valid else 'var(--amber)'};font:600 .75rem ui-monospace,monospace}}
.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:25px 0}}.card,section{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px}}.value{{display:block;font:700 1.8rem ui-monospace,monospace}}.label{{color:var(--muted);font-size:.82rem}}
.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;text-align:left}}th,td{{padding:12px;border-bottom:1px solid var(--line);white-space:nowrap}}thead th{{color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.06em}}td{{font: .9rem ui-monospace,monospace}}.note{{border-left:3px solid var(--blue);padding:12px 16px;background:#101923;color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}}.audit strong{{display:block}}.tag{{color:var(--green);font:600 .75rem ui-monospace,monospace}}footer{{margin-top:34px;color:var(--muted);font-size:.85rem}}a{{color:var(--blue)}}
@media(max-width:650px){{.cards{{grid-template-columns:repeat(2,1fr)}}.grid{{grid-template-columns:1fr}}main{{padding:28px 14px}}}}
</style></head><body><main>
<div class="kicker">LOCAL AGENT EVALUATION</div><h1>TauGuard</h1>
<p>Target-state scores can hide policy and execution failures. This report compares the baseline grader with TauGuard's policy-aware grader on a custom CRM benchmark.</p>
<span class="status">{status}</span>
<div class="cards"><div class="card"><span class="value">{len(models)}</span><span class="label">Local models</span></div>
<div class="card"><span class="value">{task_count}</span><span class="label">Tasks per model</span></div>
<div class="card"><span class="value">{episode_count}</span><span class="label">Model-task episodes</span></div>
<div class="card"><span class="value">{trials}</span><span class="label">Trials per task</span></div></div>
<div class="note">This run is marked {badge}. Run mode: <code>{html.escape(str(metadata.get('run_mode','unknown')))}</code>; failed model calls: <code>{failed}</code>. Timestamp: <code>{created}</code>.</div>
<h2>Model comparison</h2><section class="table-wrap"><table><thead><tr><th>Model</th><th>Target-state</th><th>Patched</th><th>Change</th><th>Patched pass-k</th><th>Mean latency/task</th></tr></thead><tbody>{table_rows}</tbody></table></section>
<h2>What the patched grader checks</h2><div class="grid">
<section class="audit"><strong>Activity on no-change tasks</strong><span class="tag">CHECK IMPLEMENTED</span><p>Requires order inspection when the expected state should remain unchanged.</p></section>
<section class="audit"><strong>Authentication and policy</strong><span class="tag">CHECK IMPLEMENTED</span><p>Scores recorded authorization and procedural violations as failures.</p></section>
<section class="audit"><strong>Unexpected state mutations</strong><span class="tag">CHECK IMPLEMENTED</span><p>Compares the initial and final CRM state for unapproved changes.</p></section>
<section class="audit"><strong>Customer-facing response facts</strong><span class="tag">GEMINI OPTIONAL · KEYWORD FALLBACK</span><p>Gemini semantic judging requires a local API key; otherwise exact keyword checks apply. This run uses its recorded grader configuration.</p></section>
</div>
<h2>Pipeline</h2><section>Customer request → local model → CRM tools → state, policy, and response graders → episode metrics</section>
<footer>Source: <code>{source_label}</code>. TauGuard is a small custom benchmark, not the official τ-bench implementation. Latency reflects the local hardware and includes model response time.</footer>
</main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", "-i", help="Run JSON; defaults to newest results/ollama_live_*.json")
    parser.add_argument("--output", "-o", default="dashboard.html")
    parser.add_argument("--open", action="store_true", dest="open_browser")
    args = parser.parse_args()
    source = Path(args.input) if args.input else latest_result()
    data = json.loads(source.read_text(encoding="utf-8"))
    output = Path(args.output)
    output.write_text(build_html(data, str(source)), encoding="utf-8")
    print(f"Wrote {output} from {source}")
    if args.open_browser:
        webbrowser.open(output.resolve().as_uri())


if __name__ == "__main__":
    main()
