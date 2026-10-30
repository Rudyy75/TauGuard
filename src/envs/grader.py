"""
Tau-Bench Style Grader Implementation
Implements r = r_action * r_output evaluation with state comparison and communication checks.
"""

from typing import Any, Dict, List, Optional, Tuple


class TauBenchGrader:
    """
    Standard Tau-Bench Grader.
    Reward r = r_action * r_output in {0, 1}.
    """

    @staticmethod
    def evaluate_action(
        initial_db: Dict[str, Any],
        final_db: Dict[str, Any],
        task: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates r_action.
        Inspects if final_db reflects the expected state modification defined in task['expected_action'].
        If task['expected_action'] is None (read-only task), r_action = 1 if no illegal modifications occurred.
        """
        expected_action = task.get("expected_action")
        diagnostics: Dict[str, Any] = {}

        if expected_action is None:
            # Read-only task: initial_db and final_db orders should be identical
            initial_orders = initial_db.get("orders", {})
            final_orders = final_db.get("orders", {})
            if initial_orders == final_orders:
                return 1.0, {"status": "read_only_clean_match"}
            else:
                return 0.0, {"status": "unauthorized_db_mutation", "details": "Read-only task had DB changes"}

        target_oid = expected_action["order_id"]
        target_field = expected_action["target_field"]
        target_value = expected_action["target_value"]

        order_in_final = final_db.get("orders", {}).get(target_oid)
        if not order_in_final:
            return 0.0, {"error": f"Target order {target_oid} missing in final state"}

        actual_value = order_in_final.get(target_field)
        if actual_value == target_value:
            # Additional check if expected refund matches
            if "expected_refund" in expected_action:
                expected_refund = expected_action["expected_refund"]
                actual_refund = order_in_final.get("refund_issued", 0.0)
                if abs(expected_refund - actual_refund) > 0.01:
                    return 0.0, {
                        "error": "refund_mismatch",
                        "expected": expected_refund,
                        "actual": actual_refund
                    }
            return 1.0, {"status": "action_matched", "field": target_field, "value": actual_value}
        else:
            return 0.0, {
                "error": "field_mismatch",
                "target_field": target_field,
                "expected": target_value,
                "actual": actual_value
            }

    @staticmethod
    def evaluate_output(
        conversation_history: List[Dict[str, str]],
        final_response: str,
        task: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculates r_output.
        Checks if required keywords or confirmation tokens were surfaced to the user.
        """
        expected_keywords = task.get("expected_output_keywords", [])
        if not expected_keywords:
            return 1.0, {"status": "no_output_constraints"}

        # Combine all assistant utterances for comprehensive search
        assistant_text = final_response.lower()
        for msg in conversation_history:
            if msg.get("role") == "assistant":
                assistant_text += " " + msg.get("content", "").lower()

        matched_keywords = []
        missing_keywords = []

        # Standard tau-bench criterion: requires at least one or all depending on task specification
        for kw in expected_keywords:
            if kw.lower() in assistant_text:
                matched_keywords.append(kw)
            else:
                missing_keywords.append(kw)

        # Passes if at least one key confirmation/token was provided
        if matched_keywords:
            return 1.0, {
                "status": "output_matched",
                "matched": matched_keywords,
                "missing": missing_keywords
            }
        else:
            return 0.0, {
                "status": "missing_required_communication",
                "missing": missing_keywords
            }

    @classmethod
    def grade(
        cls,
        initial_db: Dict[str, Any],
        final_db: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        final_response: str,
        task: Dict[str, Any],
        **kwargs
    ) -> Dict[str, Any]:
        """
        Full grading logic: r = r_action * r_output
        """
        r_action, action_diag = cls.evaluate_action(initial_db, final_db, task)
        r_output, output_diag = cls.evaluate_output(conversation_history, final_response, task)
        reward = float(r_action * r_output)

        return {
            "reward": reward,
            "r_action": r_action,
            "r_output": r_output,
            "action_diagnostics": action_diag,
            "output_diagnostics": output_diag,
            "passed": bool(reward == 1.0)
        }
