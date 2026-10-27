"""
User Simulator
Emulates real customer behavior following task instructions.
"""

from typing import Any, Dict, List, Optional
import os

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


class UserSimulator:
    """
    Simulates a retail customer driven by task goal and conversation context.
    """

    def __init__(
        self,
        task: Dict[str, Any],
        model_id: str = "llama-3.3-70b-versatile",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        mock_mode: bool = False
    ):
        self.task = task
        self.model_id = model_id
        self.mock_mode = mock_mode
        self.turn_count = 0

        self.base_url = base_url or os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")

        self.client = None
        if OpenAI and self.api_key and not mock_mode:
            try:
                self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            except Exception:
                self.client = None

    def respond(self, last_agent_message: str) -> Tuple_Response:
        """
        Generate user response based on task goal and agent's question.
        Returns: (response_text, is_satisfied_or_done)
        """
        self.turn_count += 1
        agent_lower = last_agent_message.lower()

        # If agent fulfilled or answered, end conversation
        if any(term in agent_lower for term in [
            "successfully cancelled", "updated to", "refund of", "tracking number",
            "cannot return", "cannot cancel", "policy violation", "return approved"
        ]):
            return "Thank you so much for your assistance! That is all I needed.", True

        # Initial turn returns user goal
        if self.turn_count == 1:
            return self.task["user_goal"], False

        # If agent asks for verification or user details
        if any(v in agent_lower for v in ["name", "email", "verify", "phone", "order id"]):
            uid = self.task.get("user_id", "usr_101")
            if uid == "usr_101":
                return "My name is Sarah Connor and my email is sarah.connor@cyberdyne.org.", False
            elif uid == "usr_102":
                return "My name is David Miller and my email is d.miller@techflow.io.", False
            else:
                return "My name is Elena Rostova and my email is elena.r@novacorp.com.", False

        # If turn count exceeds limit, close
        if self.turn_count > 6:
            return "Okay, thank you for your help.", True

        return "Could you please confirm if my request has been processed?", False


Tuple_Response = Any
