from typing import Any, Dict, List, Optional, Tuple


class UserSimulator:
    """
    Simulates a retail customer for multi-turn evaluation.
    Supplies identity on demand, closes conversation when satisfied.
    """

    def __init__(
        self,
        task: Dict[str, Any],
    ):
        self.task = task
        self.turn_count = 0

    def respond(self, last_agent_message: str) -> Tuple[str, bool]:
        """
        Returns (response_text, is_done).
        is_done=True signals the episode should end.
        """
        self.turn_count += 1
        agent_lower = last_agent_message.lower()

        # Conversation ends when the agent confirms an outcome
        resolution_signals = [
            "successfully cancelled", "has been cancelled",
            "updated to", "address updated", "has been updated",
            "refund of", "return approved", "return processed",
            "tracking number", "cannot return", "cannot cancel",
            "return window", "already shipped", "policy",
        ]
        if any(signal in agent_lower for signal in resolution_signals):
            return "Thank you, that is all I needed.", True

        # Turn 1: state the problem
        if self.turn_count == 1:
            return self.task["user_goal"], False

        # Agent is asking for identity verification
        if any(v in agent_lower for v in ["name", "email", "verify", "phone", "confirm your"]):
            name = self.task.get("user_name", "")
            email = self.task.get("user_email", "")
            if name and email:
                return f"My name is {name} and my email is {email}.", False

        # Hard cap to avoid infinite loops
        if self.turn_count > 6:
            return "Okay, thank you.", True

        return "Could you please confirm if my request has been processed?", False
