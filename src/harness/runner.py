"""
Harness Execution Engine
Runs multi-turn conversational tool evaluations over CRM benchmark tasks across multiple trials.
"""

import copy
import json
import time
from typing import Any, Dict, List, Optional

from src.envs.mock_retail import MockRetailEnvironment, RETAIL_TOOLS_SCHEMA, BENCHMARK_TASKS
from src.envs.grader import TauBenchGrader
from src.envs.patched_grader import PatchedTauBenchGrader
from src.agents.tool_agent import OpenAIToolAgent
from src.agents.mock_user import UserSimulator


def run_single_task_trial(
    task: Dict[str, Any],
    agent: OpenAIToolAgent,
    env: MockRetailEnvironment,
    max_turns: int = 8,
    grader_cls: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Execute one full interaction loop for a specific task and agent.
    """
    initial_db_snapshot = copy.deepcopy(env.db)
    user_sim = UserSimulator(task=task)

    messages: List[Dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"You are a customer service CRM agent. Task category: {task.get('category', 'general')}. "
                "You have access to tools to lookup orders, cancel orders, process returns, and update shipping addresses. "
                "Ask the customer for their name or email, then verify using lookup_user before any mutation. "
                "2) Orders delivered >30 days ago cannot be returned. "
                "3) Shipped orders cannot be cancelled directly."
            )
        }
    ]

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    start_time = time.time()
    final_agent_response = ""
    run_error = None

    # Start with initial customer goal
    user_msg, is_done = user_sim.respond("")
    messages.append({"role": "user", "content": user_msg})

    for turn in range(max_turns):
        if is_done:
            break

        # Step 1: Agent decides next action
        try:
            action_res = agent.act(messages=messages, tools_schema=RETAIL_TOOLS_SCHEMA)
        except Exception as exc:
            run_error = f"{type(exc).__name__}: {exc}"
            break

        # Accumulate usage
        if "usage" in action_res:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                total_usage[k] += action_res["usage"].get(k, 0)

        # Step 2: Handle chained tool calls until the model returns user-facing text.
        response = action_res
        tool_count = 0
        while response.get("tool_calls"):
            messages.append({
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": response["tool_calls"]
            })
            for tc in response["tool_calls"]:
                tool_count += 1
                if tool_count > 8:
                    run_error = "Tool call limit exceeded for one conversation turn"
                    break
                try:
                    tool_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    if not isinstance(args, dict):
                        raise ValueError("Tool arguments must be a JSON object")
                    tool_result = env.execute_tool(tool_name, args)
                except Exception as exc:
                    tool_name = tc.get("function", {}).get("name", "unknown")
                    tool_result = {
                        "status": "error", "code": "INVALID_TOOL_CALL",
                        "message": f"{type(exc).__name__}: {exc}"
                    }
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_default"),
                    "name": tool_name,
                    "content": json.dumps(tool_result)
                })
            if run_error:
                break
            try:
                response = agent.act(messages=messages, tools_schema=RETAIL_TOOLS_SCHEMA)
            except Exception as exc:
                run_error = f"{type(exc).__name__}: {exc}"
                break
            if "usage" in response:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    total_usage[k] += response["usage"].get(k, 0)
        if run_error:
            break
        final_agent_response = response.get("content") or ""
        messages.append({"role": "assistant", "content": final_agent_response})

        # Step 3: Customer simulator reaction
        user_reply, is_done = user_sim.respond(final_agent_response)
        messages.append({"role": "user", "content": user_reply})

    latency_seconds = time.time() - start_time
    final_db_snapshot = copy.deepcopy(env.db)

    # Step 4: Grade trial
    graders = grader_cls or TauBenchGrader
    if not isinstance(graders, (list, tuple)):
        graders = [graders]
    grader_results = {}
    if run_error is None:
        for grader in graders:
            key = "patched" if grader is PatchedTauBenchGrader else "tau_bench"
            grader_results[key] = grader.grade(
                initial_db=initial_db_snapshot,
                final_db=final_db_snapshot,
                conversation_history=messages,
                final_response=final_agent_response,
                task=task,
                action_history=env.action_history,
                policy_violations=env.policy_violations,
                auth_violations=env.auth_violations
            )
    else:
        grader_results = {
            ("patched" if g is PatchedTauBenchGrader else "tau_bench"): {
                "reward": 0.0, "r_action": 0.0, "r_output": 0.0, "passed": False,
                "action_diagnostics": {"error": "model_call_failed"},
                "output_diagnostics": {"error": "model_call_failed"}
            } for g in graders
        }
    primary = next(iter(grader_results.values()))

    return {
        "task_id": task["id"],
        "category": task.get("category"),
        "reward": primary["reward"],
        "passed": primary["passed"],
        "r_action": primary["r_action"],
        "r_output": primary["r_output"],
        "action_diagnostics": primary["action_diagnostics"],
        "output_diagnostics": primary["output_diagnostics"],
        "grader_results": grader_results,
        "error": run_error,
        "policy_violations": list(env.policy_violations),
        "action_history": copy.deepcopy(env.action_history),
        "transcript": copy.deepcopy(messages),
        "initial_db": initial_db_snapshot,
        "final_db": final_db_snapshot,
        "latency_seconds": round(latency_seconds, 3),
        "usage": total_usage,
        "transcript_turns": len(messages),
        "final_response": final_agent_response
    }


def run_benchmark_suite(
    agent: OpenAIToolAgent,
    tasks: Optional[List[Dict[str, Any]]] = None,
    num_trials: int = 3,
    verbose: bool = True,
    grader_cls: Optional[Any] = None,
    initial_db: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Run full suite across N trials with environment resets.
    """
    if tasks is None:
        tasks = BENCHMARK_TASKS

    suite_results: List[Dict[str, Any]] = []

    for task in tasks:
        task_id = task["id"]
        if verbose:
            print(f"[*] Running Task: {task_id} ({task.get('category')}) across {num_trials} trials...")

        trials_data = []
        env = MockRetailEnvironment(initial_db=initial_db, authorized_user_id=task.get("user_id"))

        for trial_idx in range(num_trials):
            env.reset()
            trial_res = run_single_task_trial(
                task=task,
                agent=agent,
                env=env,
                grader_cls=grader_cls
            )
            trial_res["trial_index"] = trial_idx
            trials_data.append(trial_res)

        suite_results.append({
            "task_id": task_id,
            "category": task.get("category"),
            "description": task.get("description"),
            "trials": trials_data
        })

    return suite_results
