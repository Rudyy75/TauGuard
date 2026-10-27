"""
Statistical Metrics for Agent Evaluation Harness
Calculates pass rate, pass^k reliability, variance across trials, latency, token consumption, and cost.
"""

import math
import statistics
from typing import Any, Dict, List


def calculate_pass_k(trial_passes: List[int], k: int) -> float:
    """
    Calculate pass^k reliability metric.
    In tau-bench, pass^k represents the fraction of tasks where ALL k trials passed.
    """
    if not trial_passes:
        return 0.0
    return 1.0 if sum(trial_passes[:k]) == k else 0.0


def calculate_variance(trial_passes: List[int]) -> float:
    """Calculate sample standard deviation of pass/fail across trials."""
    if len(trial_passes) <= 1:
        return 0.0
    return statistics.stdev(trial_passes)


def calculate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    cost_per_m_input: float = 0.15,
    cost_per_m_output: float = 0.60
) -> float:
    """Compute estimated dollar cost based on token counts."""
    input_cost = (prompt_tokens / 1_000_000.0) * cost_per_m_input
    output_cost = (completion_tokens / 1_000_000.0) * cost_per_m_output
    return input_cost + output_cost


def aggregate_model_metrics(
    task_results: List[Dict[str, Any]],
    k_trials: int = 3,
    cost_config: Dict[str, float] = None
) -> Dict[str, Any]:
    """
    Aggregates trial results across all tasks for a specific model.
    """
    if cost_config is None:
        cost_config = {"cost_per_m_input": 0.15, "cost_per_m_output": 0.60}

    total_tasks = len(task_results)
    if total_tasks == 0:
        return {}

    all_trial_passes = []
    task_pass_rates = []
    pass_k_hits = 0
    task_variances = []

    total_latencies = []
    total_prompt_tokens = []
    total_completion_tokens = []
    total_tokens_list = []
    total_costs = []

    for item in task_results:
        trials = item.get("trials", [])
        passes = [1 if t.get("passed", False) else 0 for t in trials]
        all_trial_passes.extend(passes)

        # Per-task pass rate
        task_pr = sum(passes) / len(passes) if passes else 0.0
        task_pass_rates.append(task_pr)

        # pass^k check (did all k pass?)
        if len(passes) >= k_trials and sum(passes[:k_trials]) == k_trials:
            pass_k_hits += 1

        # Per-task trial variance
        var = calculate_variance(passes)
        task_variances.append(var)

        for t in trials:
            total_latencies.append(t.get("latency_seconds", 0.0))
            p_tok = t.get("usage", {}).get("prompt_tokens", 0)
            c_tok = t.get("usage", {}).get("completion_tokens", 0)
            t_tok = t.get("usage", {}).get("total_tokens", 0)

            total_prompt_tokens.append(p_tok)
            total_completion_tokens.append(c_tok)
            total_tokens_list.append(t_tok)

            cost = calculate_cost(
                p_tok,
                c_tok,
                cost_config.get("cost_per_m_input", 0.15),
                cost_config.get("cost_per_m_output", 0.60)
            )
            total_costs.append(cost)

    overall_pass_rate = (sum(all_trial_passes) / len(all_trial_passes)) * 100.0 if all_trial_passes else 0.0
    pass_k_rate = (pass_k_hits / total_tasks) * 100.0 if total_tasks else 0.0
    mean_variance = statistics.mean(task_variances) if task_variances else 0.0
    mean_latency = statistics.mean(total_latencies) if total_latencies else 0.0
    mean_tokens = statistics.mean(total_tokens_list) if total_tokens_list else 0.0
    mean_cost_per_task = statistics.mean(total_costs) if total_costs else 0.0

    return {
        "total_tasks": total_tasks,
        "k_trials": k_trials,
        "pass_rate_pct": round(overall_pass_rate, 2),
        "pass_k_pct": round(pass_k_rate, 2),
        "mean_variance": round(mean_variance, 4),
        "mean_latency_sec": round(mean_latency, 2),
        "mean_tokens_per_task": round(mean_tokens, 1),
        "mean_cost_per_task_usd": round(mean_cost_per_task, 6)
    }
