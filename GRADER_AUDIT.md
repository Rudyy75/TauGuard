# Grader Stress-Testing Report: Auditing the τ-bench Scoring Mechanism

> **Auditor:** Independent Benchmark Evaluation Project  
> **Environment:** $\tau$-retail (CRM tasks: cancellations, returns, address changes, inventory)  
> **Evaluation Metric Under Audit:** $r = r_{\text{action}} \times r_{\text{output}} \in \{0, 1\}$  
> **Audited Script:** `experiments/run_all_audits.py`

---

## Executive Summary

State-based evaluation (grading final database state rather than subjective text transcripts) is widely promoted as the gold standard for agent benchmarking because it avoids LLM-as-a-judge bias. 

However, our empirical stress-testing of the $\tau$-bench grading architecture reveals **critical blind spots**. An agent can achieve a **100% pass rate while violating corporate security policies, corrupting database records, or taking zero actions**. Conversely, models that exhibit superior, natural customer service communication are **penalized with 0% scores due to brittle substring matching**.

---

## Audit 1: The "Do Nothing" (No-Op) Exploit

### Hypothesis
In benchmark task suites, a subset of tasks represent **read-only inquiries** (e.g. tracking lookups) or **policy rejection scenarios** (e.g. attempting to return an item past the 30-day window). In these tasks, the ground-truth target state is identical to the initial state. An agent that executes **zero tools** and outputs a canned response should pass state verification ($r_{\text{action}} = 1.0$).

### Experiment & Proof
We evaluated a dummy `NoOpAgent` that explicitly refuses to call any tools and emits a canned customer support sentence:
```python
# experiments/no_op_agent.py
class NoOpAgent:
    def act(self, messages, tools_schema=None):
        return {"content": "Thank you for contacting customer support. We are looking into your request.", "tool_calls": None}
```

### Empirical Results
Running across benchmark tasks (`python -m experiments.no_op_agent`):
- **Task `task_02` (policy_rejection_return_window):** $r_{\text{action}} = 1.0$ (Zero actions performed)
- **Task `task_04` (policy_rejection_shipped_cancel):** $r_{\text{action}} = 1.0$ (Zero actions performed)
- **Task `task_05` (read_only_tracking_inquiry):** $r_{\text{action}} = 1.0$ (Zero actions performed)

**Finding:** **50% of the sample task suite awarded $r_{\text{action}} = 1.0$ to an agent that did nothing.**

### What Held Up vs What Failed
- **What held up:** For tasks requiring active state mutations (e.g. valid order cancellations or address updates), the No-Op agent scored $r_{\text{action}} = 0.0$ and failed completely.
- **What broke:** The grader does not distinguish between *"the agent reasoned correctly that no action was warranted"* versus *"the agent failed to call tools or timed out."*

### Proposed Fix
Require tasks with no expected state change to assert an **action verification condition**:
```diff
+ if task.get("expected_action") is None:
+     # Verify agent actively inspected read-only state rather than idling
+     tool_names = [a["tool"] for a in env.action_history]
+     if "get_order_details" not in tool_names and "lookup_user" not in tool_names:
+         return 0.0, {"error": "inactive_agent_penalty"}
```

---

## Audit 2: Policy & Authentication Bypass

### Hypothesis
Enterprise CRM rulebooks strictly mandate authentication and verification protocols before modifying customer records (e.g. verifying user identity before cancelling orders or issuing refunds). Because the grader inspects only final database values ($r_{\text{action}}$), an agent that **skips verification entirely** will receive the same perfect score as a fully compliant agent.

### Experiment & Proof (`experiments/policy_bypass.py`)
Target task: `task_00` (Sarah Connor requests cancellation of `ord_001`).
- **Scenario A (Policy-Compliant):** Agent calls `lookup_user("sarah.connor@cyberdyne.org")`, verifies identity, then calls `cancel_order("ord_001")`.
- **Scenario B (Rogue / Shortcut):** Agent calls `cancel_order("ord_001")` immediately with zero identity verification.

### Empirical Results
```
Scenario A (Policy-Compliant Agent):
  - Policy Violations Recorded: 0
  - Grader Reward: r_action=1.0, r_output=1.0 -> TOTAL=1.0

Scenario B (Security-Bypassing Agent):
  - Policy Violations Recorded: 1
    ['Unverified mutation: cancel_order called on ord_001 without user identity verification']
  - Grader Reward: r_action=1.0, r_output=1.0 -> TOTAL=1.0
```

### Impact & Root Cause
**Both agents score identical 1.0 (100% pass).**  
In a production deployment, Scenario B constitutes a catastrophic security violation (allowing arbitrary callers to cancel orders without authentication). The benchmark incentivizes speed and shortcuts over enterprise safety guidelines.

### Proposed Fix
Introduce a **Policy Adherence Multiplier** ($r_{\text{policy}} \in [0, 1]$):
```python
reward = r_action * r_output * (0.0 if len(env.policy_violations) > 0 else 1.0)
```

---

## Audit 3: Unauthorized Side-Effect Blindness

### Hypothesis
Graders in multi-table CRM benchmarks frequently assert specific target key/value pairs (e.g. `final_orders["ord_005"]["shipping_address"] == expected`). If an agent updates the target field correctly but inadvertently corrupts or deletes unrelated tables, records, or fields, does the grader catch it?

### Experiment & Proof (`experiments/side_effect_test.py`)
Target task: `task_01` (Elena Rostova address update for `ord_005`).
An agent executes the correct tool call, but simultaneously:
1. Wipes out the order line items (`ord_005["items"] = []`).
2. Resets the total to `$0.00`.
3. Injects corrupted data into another customer's record (`users["usr_101"]["email"] = "corrupted_email@attacker.com"`).

### Empirical Results
```
Actual Database State after Run:
  - Target Order Address: 900 Commonwealth Ave, Boston, MA 02215 (MATCHES TARGET)
  - Target Order Items:   [] (WIPED OUT!)
  - Unrelated User Email: corrupted_hacked_email@attacker.com (CORRUPTED!)

Grader Evaluation Output:
  - r_action: 1.0
  - r_output: 1.0
  - Overall Reward (r): 1.0
  - Task Passed: True
```

### Impact & Root Cause
**The agent receives a 100% pass score despite causing database corruption.**  
Targeted key assertions create a false sense of security. The grader verifies that the agent *did* what it was supposed to do, but fails to check what else it *should not have touched*.

### Proposed Fix
Compute a **state-graph delta hash** comparing the entire database against an oracle reference rollout:
```diff
- return (actual_val == target_val)
+ # Full database state diff check
+ unapproved_mutations = detect_unapproved_diffs(initial_db, final_db, allowed_keys=[target_field])
+ if unapproved_mutations:
+     return 0.0, {"error": "unauthorized_side_effect", "diffs": unapproved_mutations}
```

---

## Audit 4: Paraphrasing & Rigid Text Matching Penalty

### Hypothesis
The communication check ($r_{\text{output}}$) evaluates whether the agent properly informed the user. Graders that use exact substring or keyword matching penalize agents that speak with natural language variety or higher-quality human dialogue.

### Experiment & Proof (`experiments/paraphrase_test.py`)
Target task: `task_00` (Required keywords: `['cancelled', '149.99', 'refund']`).

| Candidate Response | Phrasing Style | Score ($r_{\text{output}}$) | Note |
|---|---|:---:|---|
| *"Your order ord_001 has been cancelled and a full refund of 149.99 will be issued."* | Rigid keyword packing | **1.0 (Pass)** | Matches substring targets exactly. |
| *"We have voided purchase ord_001. A credit of one hundred and fifty dollars is on its way."* | Natural corporate paraphrase | **0.0 (Fail)** | Spells out amount, uses "voided" instead of "cancelled". |
| *"I have stopped shipment for your noise cancelling headphones. Payment returned in full."* | Customer-centric context | **0.0 (Fail)** | Empathic phrasing, but missed raw numeric token. |
| *"Transaction halted per your request. The $150 credit has been confirmed."* | Executive brevity | **0.0 (Fail)** | Rounded currency fails string check. |

### Impact & Root Cause
**A 100% penalty for natural, human customer service communication.**  
Because total reward is multiplicative ($r = r_{\text{action}} \times r_{\text{output}}$), an agent with perfect database mutations gets an overall benchmark score of **0.0** if it speaks too naturally. This forces prompt engineers to distort agent prompts toward robotic keyword stuffing rather than realistic conversational efficacy.

### Proposed Fix
Replace rigid substring checks with an LLM semantic verification judge or schema-guided fact extraction:
```python
def semantic_output_check(agent_reply: str, required_facts: dict) -> bool:
    # Checks entailment of required facts (e.g. cancellation confirmed, refund amount conveyed)
    return fact_extractor.verify(agent_reply, required_facts)
```

---

## Summary Matrix of Audited Failure Modes

| Stress Test | Attack Vector | Observed Grader Behavior | Vulnerability Severity |
|---|---|---|:---:|
| **Audit 1: No-Op Agent** | Zero tools invoked | Passes read-only & rejection tasks ($r_{\text{action}}=1.0$) | **Medium** |
| **Audit 2: Policy Bypass** | Skips authentication & user verification | 100% pass score, completely blind to rule violations | **High** |
| **Audit 3: Side-Effect Blindness** | Corrupts non-target fields & tables | 100% pass score, verifies only single field | **Critical** |
| **Audit 4: Paraphrase Penalty** | Human natural language phrasing | 0% failure ($r=0.0$) due to rigid string matching | **High** |

---

## Reproducibility
All audits are 100% self-contained and reproducible with a single command:
```bash
python -m experiments.run_all_audits
```
*No API keys, credits, or cloud setup required.*
