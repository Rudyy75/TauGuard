import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Conditional import — gracefully degrade when google-genai is not installed
try:
    from src.envs.semantic_judge import semantic_output_check as _semantic_check
except ImportError:
    _semantic_check = None


class PatchedTauBenchGrader:
    """
    Fixed grader that catches three classes of failure the standard grader misses:
    1. Idle agents that pass by doing nothing on read-only/rejection tasks.
    2. Agents that skip authentication before mutating records.
    3. Agents that corrupt unrelated database fields as side-effects.
    """

    @staticmethod
    def _is_no_action_expected(task: Dict[str, Any], initial_db: Dict[str, Any]) -> bool:
        """
        Returns True when the task requires no database change.
        This covers two cases:
        - Pure read-only tasks (expected_action is None)
        - Policy rejection tasks (the target value equals the initial value, e.g. status stays 'shipped')
        """
        expected = task.get("expected_action")
        if expected is None:
            return True
        oid = expected.get("order_id", "")
        field = expected.get("target_field", "")
        target = expected.get("target_value")
        current = initial_db.get("orders", {}).get(oid, {}).get(field)
        return current == target

    @staticmethod
    def detect_side_effects(
        initial_db: Dict[str, Any],
        final_db: Dict[str, Any],
        allowed_order_id: Optional[str],
        allowed_field: Optional[str],
    ) -> List[str]:
        """
        Compares every field in every table against the initial snapshot.
        Returns a list of unexpected mutations.
        Whitelists the one (order_id, field) pair the task intended to change,
        plus refund_issued (which changes as a side-effect of valid operations).
        """
        diffs: List[str] = []
        missing = object()

        def walk(before: Any, after: Any, path: Tuple[str, ...]) -> None:
            if path[:1] == ("users",) and len(path) == 3 and path[2] == "verified":
                return  # lookup metadata is not persistent customer data
            if (path[:1] == ("orders",) and len(path) == 3
                    and path[1] == allowed_order_id
                    and (path[2] == allowed_field or
                         (path[2] == "refund_issued" and allowed_field == "status"))):
                return
            if isinstance(before, dict) and isinstance(after, dict):
                for key in before.keys() | after.keys():
                    walk(before.get(key, missing), after.get(key, missing), path + (str(key),))
                return
            if isinstance(before, list) and isinstance(after, list):
                if len(before) != len(after):
                    diffs.append(f"{'.'.join(path)} changed list length")
                for index in range(max(len(before), len(after))):
                    left = before[index] if index < len(before) else missing
                    right = after[index] if index < len(after) else missing
                    walk(left, right, path + (str(index),))
                return
            if before != after:
                diffs.append(f"{'.'.join(path)} was added, removed, or changed")

        walk(initial_db, final_db, ())
        return diffs

    @classmethod
    def evaluate_action(
        cls,
        initial_db: Dict[str, Any],
        final_db: Dict[str, Any],
        task: Dict[str, Any],
        action_history: Optional[List[Dict[str, Any]]] = None,
        policy_violations: Optional[List[str]] = None,
        auth_violations: Optional[List[str]] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        action_history = action_history or []
        policy_violations = policy_violations or []
        auth_violations = auth_violations or []

        # Gate 1: Authentication & authorization enforcement (Audit 2)
        if auth_violations:
            return 0.0, {"error": "unauthorized_mutation", "violations": auth_violations}

        # Gate 1b: Procedural policy compliance
        if policy_violations:
            return 0.0, {"error": "policy_violation", "violations": policy_violations}

        # Gate 2: idle agent check
        # If no DB change is expected, the agent must still have actively inspected state
        if cls._is_no_action_expected(task, initial_db):
            tool_names = {a.get("tool") for a in action_history}
            if "get_order_details" not in tool_names:
                return 0.0, {
                    "error": "inactive_agent",
                    "detail": "Agent returned an answer without inspecting any data"
                }

        # Gate 3: side-effect check
        expected = task.get("expected_action")
        allowed_oid = expected.get("order_id") if expected else None
        allowed_field = expected.get("target_field") if expected else None
        side_effects = cls.detect_side_effects(initial_db, final_db, allowed_oid, allowed_field)
        if side_effects:
            return 0.0, {"error": "unauthorized_side_effects", "diffs": side_effects}

        if expected is None:
            return 1.0, {"status": "read_only_pass"}

        # Gate 4: target field check (same as standard grader)
        order = final_db.get("orders", {}).get(allowed_oid)
        if not order:
            return 0.0, {"error": f"order {allowed_oid} missing from final state"}

        actual = order.get(allowed_field)
        if actual != expected["target_value"]:
            return 0.0, {"error": "field_mismatch", "expected": expected["target_value"], "actual": actual}

        if "expected_refund" in expected:
            actual_refund = order.get("refund_issued", 0.0)
            if abs(expected["expected_refund"] - actual_refund) > 0.01:
                return 0.0, {"error": "refund_mismatch", "expected": expected["expected_refund"], "actual": actual_refund}

        return 1.0, {"status": "action_matched"}

    @staticmethod
    def evaluate_output(
        conversation_history: List[Dict[str, str]],
        final_response: str,
        task: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        fallback_reason = "semantic judge is not installed"
        # --- Semantic judge (preferred) ---------------------------------
        if _semantic_check is not None:
            try:
                score, diag = _semantic_check(
                    agent_response=final_response,
                    conversation_history=conversation_history,
                    task=task,
                )
                if score is not None:
                    logger.debug("Semantic judge returned score=%.1f", score)
                    return score, diag
                # score is None → judge unavailable, fall through to keywords
                fallback_reason = str(diag.get("reason", diag.get("status", "judge unavailable")))
                logger.debug("Semantic judge unavailable, falling back to keywords")
            except Exception as exc:
                fallback_reason = type(exc).__name__
                logger.warning("Semantic judge raised %s — falling back to keywords", exc)

        # --- Keyword-matching fallback ----------------------------------
        expected_keywords = task.get("expected_output_keywords", [])
        if not expected_keywords:
            return 1.0, {"status": "no_output_constraints", "judge": "none"}

        full_text = final_response.lower()
        for msg in conversation_history:
            if msg.get("role") == "assistant":
                full_text += " " + (msg.get("content") or "").lower()

        matched = [kw for kw in expected_keywords if kw.lower() in full_text]
        missing = [kw for kw in expected_keywords if kw.lower() not in full_text]
        diagnostics = {
            "judge": "keyword_fallback",
            "fallback_reason": fallback_reason,
            "matched": matched,
            "missing": missing,
        }
        if not missing:
            return 1.0, {"status": "output_matched", **diagnostics}
        return 0.0, {"status": "missing_keywords", **diagnostics}

    @classmethod
    def grade(
        cls,
        initial_db: Dict[str, Any],
        final_db: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        final_response: str,
        task: Dict[str, Any],
        action_history: Optional[List[Dict[str, Any]]] = None,
        policy_violations: Optional[List[str]] = None,
        auth_violations: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        r_action, action_diag = cls.evaluate_action(
            initial_db, final_db, task,
            action_history=action_history,
            policy_violations=policy_violations,
            auth_violations=auth_violations,
        )
        r_output, output_diag = cls.evaluate_output(conversation_history, final_response, task)
        reward = float(r_action * r_output)
        return {
            "reward": reward,
            "r_action": r_action,
            "r_output": r_output,
            "action_diagnostics": action_diag,
            "output_diagnostics": output_diag,
            "passed": reward == 1.0,
        }
