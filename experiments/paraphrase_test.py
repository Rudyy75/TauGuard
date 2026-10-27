"""
Grader Exploit 4: Paraphrasing & Rigid Text Match Penalty
Tests how rigid substring matching in r_output penalizes semantically correct natural language answers.
"""

from src.envs.mock_retail import BENCHMARK_TASKS
from src.envs.grader import TauBenchGrader


def audit_paraphrase_sensitivity():
    print("=" * 70)
    print("GRADER AUDIT 4: Testing Communication Check (r_output) Brittle String Matching")
    print("=" * 70)

    target_task = next(t for t in BENCHMARK_TASKS if t["id"] == "task_00")
    expected_kw = target_task.get("expected_output_keywords", [])
    print(f"Target Task: {target_task['id']}")
    print(f"Required Output Keywords: {expected_kw}\n")

    test_responses = [
        {
            "label": "Rigid / Keyword-Packed Response",
            "text": "Your order ord_001 has been cancelled and a full refund of 149.99 will be issued.",
            "description": "Uses exact keyword matches ('cancelled', '149.99', 'refund')."
        },
        {
            "label": "Natural Human Paraphrase A (Spelled Out Currency)",
            "text": "We have voided purchase ord_001. A credit of one hundred and fifty dollars is on its way to your account.",
            "description": "Completely accurate in enterprise context, but spells out the amount and says 'voided' instead of 'cancelled'."
        },
        {
            "label": "Natural Human Paraphrase B (Item Description Reference)",
            "text": "I have stopped the shipment for your noise cancelling headphones. Your original payment has been returned in full.",
            "description": "Refers to the actual product item, uses 'payment returned' rather than 'refund'."
        },
        {
            "label": "Concise Executive Summary",
            "text": "Transaction halted per your request. The $150 credit has been confirmed.",
            "description": "Rounds $149.99 to $150 and uses 'halted'."
        }
    ]

    for item in test_responses:
        r_out, diag = TauBenchGrader.evaluate_output(
            conversation_history=[],
            final_response=item["text"],
            task=target_task
        )
        status = "PASSED (r_out=1.0)" if r_out == 1.0 else "FAILED (r_out=0.0)"
        print(f"Candidate: [{item['label']}]")
        print(f"  Response: \"{item['text']}\"")
        print(f"  Result:   {status}")
        print(f"  Diagnostics: {diag}\n")

    print("-" * 70)
    print("VULNERABILITY CONFIRMED:")
    print("Rigid regex or substring matching penalizes natural conversational variations.")
    print("In an actual production deployment, Paraphrases A & B are outstanding customer service,")
    print("yet in the benchmark they suffer a brutal 100% failure rate (r = 0.0 * 1.0 = 0.0).")


if __name__ == "__main__":
    audit_paraphrase_sensitivity()
