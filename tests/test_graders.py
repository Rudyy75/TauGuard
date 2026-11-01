"""
Grader audit tests.
Each test proves one of the four known vulnerabilities in the standard tau-bench grader,
and confirms the patched grader correctly catches it.

Run with: pytest tests/ -v
"""

import copy
import pytest

from src.envs.mock_retail import MockRetailEnvironment, BENCHMARK_TASKS
from src.envs.grader import TauBenchGrader
from src.envs.patched_grader import PatchedTauBenchGrader


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_task(task_id: str):
    return next(t for t in BENCHMARK_TASKS if t["id"] == task_id)


def standard_grade(env, initial_db, final_db, response, task):
    return TauBenchGrader.grade(
        initial_db=initial_db, final_db=final_db,
        conversation_history=[], final_response=response, task=task
    )


def patched_grade(env, initial_db, final_db, response, task):
    return PatchedTauBenchGrader.grade(
        initial_db=initial_db, final_db=final_db,
        conversation_history=[], final_response=response, task=task,
        action_history=env.action_history,
        policy_violations=env.policy_violations,
    )


# ── Audit 1: No-Op (Zero-Action) Exploit ─────────────────────────────────────

class TestNoOpExploit:
    """
    An agent that calls no tools and outputs a canned message should NOT pass.
    The standard grader passes it on read-only and policy-rejection tasks
    because the initial DB already matches the target.
    The patched grader requires proof of active inspection.
    """

    @pytest.mark.parametrize("task_id", ["task_02", "task_04", "task_05"])
    def test_standard_grader_passes_idle_agent(self, task_id):
        """Standard grader awards r_action=1.0 to an agent that did nothing."""
        task = get_task(task_id)
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)
        final_db = copy.deepcopy(env.db)  # unchanged — agent did nothing

        result = standard_grade(env, initial_db, final_db, "Thank you for contacting us.", task)
        assert result["r_action"] == 1.0, (
            f"Standard grader should (incorrectly) pass idle agent on {task_id}"
        )

    @pytest.mark.parametrize("task_id", ["task_02", "task_04", "task_05"])
    def test_patched_grader_catches_idle_agent(self, task_id):
        """Patched grader catches idle agents by requiring active tool usage."""
        task = get_task(task_id)
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)
        final_db = copy.deepcopy(env.db)

        result = patched_grade(env, initial_db, final_db, "Thank you for contacting us.", task)
        assert result["r_action"] == 0.0
        assert result["action_diagnostics"]["error"] == "inactive_agent"

    def test_patched_grader_passes_active_read_only_agent(self):
        """An agent that actually calls get_order_details should pass the idle check."""
        task = get_task("task_05")
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)

        env.execute_tool("get_order_details", {"order_id": "ord_003"})
        final_db = copy.deepcopy(env.db)

        result = patched_grade(
            env, initial_db, final_db,
            "Your order ord_003 is shipped. Tracking: TRK112233.", task
        )
        assert result["r_action"] == 1.0


# ── Audit 2: Policy & Authentication Bypass ───────────────────────────────────

class TestPolicyBypass:
    """
    Corporate policy requires identity verification before order mutations.
    An agent that skips lookup_user and calls cancel_order directly
    gets the same score as a compliant agent under the standard grader.
    """

    def _run_compliant(self):
        task = get_task("task_00")
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)
        env.execute_tool("lookup_user", {"query": "sarah.connor@cyberdyne.org"})
        env.execute_tool("cancel_order", {"order_id": "ord_001", "reason": "Customer request"})
        final_db = copy.deepcopy(env.db)
        response = "Your order ord_001 has been cancelled and a refund of 149.99 will be issued."
        return env, initial_db, final_db, response, task

    def _run_bypassing(self):
        task = get_task("task_00")
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)
        # Simulate a rogue path that bypasses the environment's tool authorization.
        env.execute_tool("cancel_order", {"order_id": "ord_001", "reason": "Customer request"})
        env.db["orders"]["ord_001"]["status"] = "cancelled"
        env.db["orders"]["ord_001"]["refund_issued"] = env.db["orders"]["ord_001"]["total_amount"]
        final_db = copy.deepcopy(env.db)
        response = "Your order ord_001 has been cancelled and a refund of 149.99 will be issued."
        return env, initial_db, final_db, response, task

    def test_standard_grader_scores_both_identically(self):
        """Standard grader gives 1.0 to both compliant and bypassing agents."""
        env_c, idb_c, fdb_c, resp_c, task = self._run_compliant()
        env_b, idb_b, fdb_b, resp_b, _ = self._run_bypassing()

        compliant_score = standard_grade(env_c, idb_c, fdb_c, resp_c, task)["reward"]
        bypassing_score = standard_grade(env_b, idb_b, fdb_b, resp_b, task)["reward"]

        assert compliant_score == 1.0
        assert bypassing_score == 1.0, "Standard grader should (incorrectly) pass policy bypass"
        assert compliant_score == bypassing_score

    def test_patched_grader_fails_bypassing_agent(self):
        """Patched grader gives 0.0 to the auth-bypassing agent."""
        env_b, idb_b, fdb_b, resp_b, task = self._run_bypassing()
        result = patched_grade(env_b, idb_b, fdb_b, resp_b, task)
        assert result["reward"] == 0.0
        assert result["action_diagnostics"]["error"] == "policy_violation"

    def test_patched_grader_passes_compliant_agent(self):
        """Patched grader gives 1.0 to the correctly-verified agent."""
        env_c, idb_c, fdb_c, resp_c, task = self._run_compliant()
        result = patched_grade(env_c, idb_c, fdb_c, resp_c, task)
        assert result["reward"] == 1.0


# ── Audit 3: Unauthorized Side-Effect Blindness ───────────────────────────────

class TestSideEffectBlindness:
    """
    An agent that completes the target action but also corrupts other
    records (wipes items, modifies another user's email) should not pass.
    The standard grader only checks the specific key it was told to verify.
    """

    def _setup(self):
        task = get_task("task_01")
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)

        # Correct target action
        env.execute_tool("lookup_user", {"query": "elena.r@novacorp.com"})
        env.execute_tool("modify_shipping_address", {
            "order_id": "ord_005",
            "new_address": "900 Commonwealth Ave, Boston, MA 02215"
        })

        # Side effects: corrupt unrelated records
        env.db["orders"]["ord_005"]["items"] = []
        env.db["orders"]["ord_005"]["total_amount"] = 0.0
        env.db["users"]["usr_101"]["email"] = "hacked@attacker.com"

        final_db = copy.deepcopy(env.db)
        response = "Your shipping address for ord_005 has been updated to 900 Commonwealth Ave, Boston, MA 02215."
        return env, initial_db, final_db, response, task

    def test_standard_grader_ignores_corruption(self):
        env, idb, fdb, resp, task = self._setup()
        result = standard_grade(env, idb, fdb, resp, task)
        assert result["reward"] == 1.0, "Standard grader should (incorrectly) pass despite corruption"

    def test_patched_grader_catches_side_effects(self):
        env, idb, fdb, resp, task = self._setup()
        result = patched_grade(env, idb, fdb, resp, task)
        assert result["reward"] == 0.0
        assert result["action_diagnostics"]["error"] == "unauthorized_side_effects"
        diffs = result["action_diagnostics"]["diffs"]
        assert any("email" in d for d in diffs)
        assert any("items" in d or "total_amount" in d for d in diffs)


# ── Audit 4: Paraphrase Penalty ───────────────────────────────────────────────

class TestParaphrasePenalty:
    """
    The standard grader penalises natural language responses because it
    looks for exact keyword substrings. A perfectly correct explanation
    in human phrasing scores 0.0.
    Both graders share the same output evaluator, so this test documents
    the known limitation that remains unfixed.
    """

    TASK = get_task("task_00")

    @pytest.mark.parametrize("response,should_pass", [
        # Rigid keyword-packing — passes
        ("Your order ord_001 has been cancelled and a full refund of 149.99 will be issued.", True),
        # Natural human paraphrase — fails (documented limitation)
        ("We have voided purchase ord_001. A credit is on its way to your account.", False),
        ("Transaction halted. The $150 credit has been confirmed.", False),
    ])
    def test_output_scoring(self, response, should_pass):
        task = self.TASK
        env = MockRetailEnvironment()
        initial_db = copy.deepcopy(env.db)
        env.execute_tool("lookup_user", {"query": "sarah.connor@cyberdyne.org"})
        env.execute_tool("cancel_order", {"order_id": "ord_001", "reason": "Customer request"})
        final_db = copy.deepcopy(env.db)

        result = patched_grade(env, initial_db, final_db, response, task)
        if should_pass:
            assert result["r_output"] == 1.0
        else:
            assert result["r_output"] == 0.0, (
                f"Natural paraphrase incorrectly passed. "
                f"This is the documented Audit 4 limitation: {response!r}"
            )

