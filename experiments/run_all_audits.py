"""
Unified Runner for all Day 3 Grader Audits
Executes Exploit 1 (No-Op), Exploit 2 (Policy Bypass), Exploit 3 (Side Effects), and Exploit 4 (Paraphrase Penalty).
"""

from experiments.no_op_agent import audit_no_op_exploit
from experiments.policy_bypass import audit_policy_bypass
from experiments.side_effect_test import audit_side_effect_blindness
from experiments.paraphrase_test import audit_paraphrase_sensitivity


def main():
    print("\n" + "#" * 80)
    print("      DAY 3: BREAK THE GRADER - COMPREHENSIVE BENCHMARK AUDIT SUITE")
    print("#" * 80 + "\n")

    audit_no_op_exploit()
    print("\n\n")

    audit_policy_bypass()
    print("\n\n")

    audit_side_effect_blindness()
    print("\n\n")

    audit_paraphrase_sensitivity()
    print("\n" + "#" * 80)
    print("      ALL AUDITS COMPLETE - REVIEW GRADER_AUDIT.MD FOR FULL ANALYSIS")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    main()
