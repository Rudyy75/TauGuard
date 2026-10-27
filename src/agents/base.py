"""
Base Agent Interface
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseAgent(ABC):
    """Abstract base class for conversational tool-calling agents."""

    def __init__(self, name: str, model_id: str):
        self.name = name
        self.model_id = model_id

    @abstractmethod
    def act(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Produce next action: either a message response or a list of tool calls.
        Returns dict matching OpenAI response format:
        {
            "content": str or None,
            "tool_calls": List[{"name": str, "arguments": dict}] or None,
            "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        }
        """
        pass
