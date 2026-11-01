"""
Grader Exploit 1: The Zero-Action (No-Op) Agent
Tests whether the target-state action grader gives an action score to an agent that calls no tools.
"""

import copy
from typing import Any, Dict, List
from src.envs.mock_retail import MockRetailEnvironment, BENCHMARK_TASKS
from src.envs.grader import TauBenchGrader


class NoOpAgent:
    """Agent that refuses to call any tools, responding only with canned text."""
    def act(self, messages: List[Dict[str, Any]], tools_schema: Any = None) -> Dict[str, Any]:
        return {
            "content": "Thank you for contacting customer support. We are looking into your request. Have a wonderful day!",
            "tool_calls": None,
            "usage": {"prompt_tokens": 50, "completion_tokens": 15, "total_tokens": 65}
        }


def audit_no_op_exploit():
    print("=" * 70)
    print("GRADER AUDIT 1: Testing No-Op (Zero-Action) Agent Vulnerability")
    print("=" * 70)
    
    agent = NoOpAgent()
    passed_tasks = []
    
    for task in BENCHMARK_TASKS:
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)
        
        # Agent outputs stock canned message
        res = agent.act([{"role": "user", "content": task["user_goal"]}])
        final_db = copy.deepcopy(env.db)
        
        grade = TauBenchGrader.grade(
            initial_db=initial_db,
            final_db=final_db,
            conversation_history=[
                {"role": "user", "content": task["user_goal"]},
                {"role": "assistant", "content": res["content"]}
            ],
            final_response=res["content"],
            task=task
        )
        
        expected_action = task.get("expected_action")
        print(f"Task: {task['id']:<8} | Category: {task.get('category'):<32} | "
              f"r_action: {grade['r_action']} | r_output: {grade['r_output']} | Passed: {grade['passed']}")
        
        if grade["r_action"] == 1.0:
            passed_tasks.append((task["id"], task.get("category"), grade["passed"]))

    print("-" * 70)
    print(f"SUMMARY: {len(passed_tasks)} / {len(BENCHMARK_TASKS)} tasks awarded r_action = 1.0 to an agent that did NOTHING.")
    for tid, cat, full_pass in passed_tasks:
        print(f"  -> Task {tid} ({cat}): r_action=1.0 (Full pass: {full_pass})")
    
    print("\nRoot Cause Analysis:")
    print("For read-only inquiries or policy rejections, the target state already matches the initial state.")
    print("This proves an r_action false positive; the full reward may still fail the separate output check.")


if __name__ == "__main__":
    audit_no_op_exploit()
