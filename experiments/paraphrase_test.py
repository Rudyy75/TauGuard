"""Compare exact and paraphrased output grading for the cancellation task.

With GEMINI_API_KEY configured, the patched grader uses Gemini and records that
provenance. Without a key (or if the request fails), it visibly uses keyword
fallback. No API key or HTTP request data is written to the result file.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.envs.mock_retail import BENCHMARK_TASKS
from src.envs.grader import TauBenchGrader
from src.envs.patched_grader import PatchedTauBenchGrader


CASES = [
    {
        "label": "Exact keyword wording",
        "text": "Order ord_001 has been cancelled and a refund of $149.99 will be issued.",
    },
    {
        "label": "Faithful paraphrase",
        "text": "I stopped order ord_001. We will return 149 dollars and 99 cents to your original payment method.",
    },
    {
        "label": "Rounded amount (should fail)",
        "text": "I stopped order ord_001 and confirmed a $150 credit to your original payment method.",
    },
    {
        "label": "Wrong order identifier (should fail)",
        "text": "I stopped order ord_002 and will refund exactly $149.99.",
    },
]


def load_local_env() -> None:
    """Load simple KEY=VALUE entries without requiring an extra package."""
    env_path = Path(".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("\"", "'"):
            value = value[1:-1]
        os.environ[key] = value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/semantic_judge_result.json")
    args = parser.parse_args()

    load_local_env()

    task = next(item for item in BENCHMARK_TASKS if item["id"] == "task_00")
    results = []
    for case in CASES:
        baseline_score, baseline_diag = TauBenchGrader.evaluate_output([], case["text"], task)
        patched_score, patched_diag = PatchedTauBenchGrader.evaluate_output([], case["text"], task)
        row = {
            "case": case["label"],
            "response": case["text"],
            "baseline_score": baseline_score,
            "baseline_diagnostics": baseline_diag,
            "patched_score": patched_score,
            "patched_diagnostics": patched_diag,
        }
        results.append(row)
        print(f"{case['label']}: baseline={baseline_score:.1f} patched={patched_score:.1f} "
              f"judge={patched_diag.get('judge', 'unknown')} status={patched_diag.get('status')}")
        if patched_diag.get("fallback_reason"):
            print(f"  fallback: {patched_diag['fallback_reason']}")
        elif patched_diag.get("reason"):
            print(f"  judge reason: {patched_diag['reason']}")

    judges = {row["patched_diagnostics"].get("judge", "unknown") for row in results}
    artifact = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": os.environ.get("GEMINI_MODEL_ID", "gemini-3.5-flash-lite"),
        "judge_used": next(iter(judges)) if len(judges) == 1 else "mixed",
        "note": "A keyword_fallback result is not evidence of semantic judging.",
        "results": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved diagnostics (no API key) to {output_path}")


def audit_paraphrase_sensitivity() -> None:
    main()


if __name__ == "__main__":
    main()
