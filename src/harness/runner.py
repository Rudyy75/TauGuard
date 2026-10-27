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
from src.agents.tool_agent import OpenAIToolAgent
from src.agents.mock_user import UserSimulator


def run_single_task_trial(
    task: Dict[str, Any],
    agent: OpenAIToolAgent,
    env: MockRetailEnvironment,
    max_turns: int = 8
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
                "You are an expert customer service CRM agent. You have access to tools to lookup orders, "
                "cancel orders, process returns, and update shipping addresses. "
                "Adhere strictly to corporate policies: orders delivered >30 days ago cannot be returned, "
                "and shipped orders cannot be cancelled directly. Always verify customer details when modifying records."
            )
        }
    ]

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    start_time = time.time()
    final_agent_response = ""

    # Start with initial customer goal
    user_msg, is_done = user_sim.respond("")
    messages.append({"role": "user", "content": user_msg})

    for turn in range(max_turns):
        if is_done:
            break

        # Step 1: Agent decides next action
        action_res = agent.act(messages=messages, tools_schema=RETAIL_TOOLS_SCHEMA)

        # Accumulate usage
        if "usage" in action_res:
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                total_usage[k] += action_res["usage"].get(k, 0)

        # Step 2: Handle tool calls or assistant message
        if action_res.get("tool_calls"):
            # Add assistant message with tool calls to conversation
            messages.append({
                "role": "assistant",
                "content": action_res.get("content") or "",
                "tool_calls": action_res["tool_calls"]
            })

            # Execute all tool calls
            for tc in action_res["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                except Exception:
                    args = {}

                tool_result = env.execute_tool(tool_name, args)

                # Append tool response
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "call_default"),
                    "name": tool_name,
                    "content": json.dumps(tool_result)
                })

            # Let agent respond after tool results
            post_tool_res = agent.act(messages=messages, tools_schema=RETAIL_TOOLS_SCHEMA)
            if "usage" in post_tool_res:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    total_usage[k] += post_tool_res["usage"].get(k, 0)

            final_agent_response = post_tool_res.get("content") or ""
            messages.append({"role": "assistant", "content": final_agent_response})

        else:
            final_agent_response = action_res.get("content") or ""
            messages.append({"role": "assistant", "content": final_agent_response})

        # Step 3: Customer simulator reaction
        user_reply, is_done = user_sim.respond(final_agent_response)
        messages.append({"role": "user", "content": user_reply})

    latency_seconds = time.time() - start_time
    final_db_snapshot = copy.deepcopy(env.db)

    # Step 4: Grade trial
    grade_result = TauBenchGrader.grade(
        initial_db=initial_db_snapshot,
        final_db=final_db_snapshot,
        conversation_history=messages,
        final_response=final_agent_response,
        task=task
    )

    return {
        "task_id": task["id"],
        "category": task.get("category"),
        "reward": grade_result["reward"],
        "passed": grade_result["passed"],
        "r_action": grade_result["r_action"],
        "r_output": grade_result["r_output"],
        "action_diagnostics": grade_result["action_diagnostics"],
        "output_diagnostics": grade_result["output_diagnostics"],
        "policy_violations": list(env.policy_violations),
        "latency_seconds": round(latency_seconds, 3),
        "usage": total_usage,
        "transcript_turns": len(messages),
        "final_response": final_agent_response
    }


def run_benchmark_suite(
    agent: OpenAIToolAgent,
    tasks: Optional[List[Dict[str, Any]]] = None,
    num_trials: int = 3,
    verbose: bool = True
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
        env = MockRetailEnvironment()

        for trial_idx in range(num_trials):
            env.reset()
            trial_res = run_single_task_trial(task=task, agent=agent, env=env)
            trial_res["trial_index"] = trial_idx
            trials_data.append(trial_res)

        suite_results.append({
            "task_id": task_id,
            "category": task.get("category"),
            "description": task.get("description"),
            "trials": trials_data
        })

    return suite_results
