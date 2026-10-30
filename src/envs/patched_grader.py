from typing import Any, Dict, List, Optional, Tuple


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
        diffs = []

        for uid, user in initial_db.get("users", {}).items():
            final_user = final_db.get("users", {}).get(uid, {})
            for k, v in user.items():
                if k == "verified":
                    continue  # lookup_user legitimately sets this
                if final_user.get(k) != v:
                    diffs.append(f"users[{uid}][{k}] was changed without authorisation")

        for pid, prod in initial_db.get("products", {}).items():
            final_prod = final_db.get("products", {}).get(pid, {})
            for k, v in prod.items():
                if final_prod.get(k) != v:
                    diffs.append(f"products[{pid}][{k}] was changed without authorisation")

        for oid, order in initial_db.get("orders", {}).items():
            final_order = final_db.get("orders", {}).get(oid, {})
            for k, v in order.items():
                if oid == allowed_order_id and k in (allowed_field, "refund_issued"):
                    continue  # the intended change
                if final_order.get(k) != v:
                    diffs.append(f"orders[{oid}][{k}] was changed without authorisation")

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
            if not tool_names.intersection({"get_order_details", "lookup_user"}):
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
        expected_keywords = task.get("expected_output_keywords", [])
        if not expected_keywords:
            return 1.0, {"status": "no_output_constraints"}

        full_text = final_response.lower()
        for msg in conversation_history:
            if msg.get("role") == "assistant":
                full_text += " " + (msg.get("content") or "").lower()

        matched = [kw for kw in expected_keywords if kw.lower() in full_text]
        if matched:
            return 1.0, {"status": "output_matched", "matched": matched}
        return 0.0, {"status": "missing_keywords", "expected": expected_keywords}

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
