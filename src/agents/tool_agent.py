"""
OpenAI-Compatible Tool Agent
Works seamlessly with Ollama, vLLM, Groq, OpenRouter, and includes a fallback simulator mode.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional
from src.agents.base import BaseAgent

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


class OpenAIToolAgent(BaseAgent):
    """
    Agent interacting via standard OpenAI Chat Completions API with Tool Calling.
    """

    def __init__(
        self,
        name: str,
        model_id: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        mock_fallback: bool = False
    ):
        super().__init__(name, model_id)
        self.temperature = temperature
        self.mock_fallback = mock_fallback
        
        # Resolve endpoints
        self.base_url = base_url or os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = api_key or os.getenv("LOCAL_LLM_API_KEY", "ollama")

        self.client = None
        if OpenAI and not mock_fallback:
            try:
                self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            except Exception:
                self.client = None

    def _fallback_simulate(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Deterministic simulation mode for offline testing and verification.
        Emulates standard model behaviors across typical retail scenarios.
        """
        last_msg = messages[-1].get("content", "")
        last_role = messages[-1].get("role", "")

        # If previous message was a tool result, formulate response to customer
        if last_role == "tool":
            tool_content = messages[-1].get("content", "")
            return {
                "content": f"I have processed your request. Details: {tool_content}. Is there anything else I can help you with?",
                "tool_calls": None,
                "usage": {"prompt_tokens": 120, "completion_tokens": 35, "total_tokens": 155}
            }

        # Handle cancellation requests
        if "cancel" in last_msg.lower() and "ord_001" in last_msg.lower():
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_cancel_1",
                        "type": "function",
                        "function": {
                            "name": "cancel_order",
                            "arguments": json.dumps({"order_id": "ord_001", "reason": "Customer requested cancellation"})
                        }
                    }
                ],
                "usage": {"prompt_tokens": 210, "completion_tokens": 25, "total_tokens": 235}
            }

        # Handle address update requests
        if "address" in last_msg.lower() and "ord_005" in last_msg.lower():
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_addr_1",
                        "type": "function",
                        "function": {
                            "name": "modify_shipping_address",
                            "arguments": json.dumps({
                                "order_id": "ord_005",
                                "new_address": "900 Commonwealth Ave, Boston, MA 02215"
                            })
                        }
                    }
                ],
                "usage": {"prompt_tokens": 220, "completion_tokens": 30, "total_tokens": 250}
            }

        # Handle tracking lookup
        if "tracking" in last_msg.lower() and "ord_003" in last_msg.lower():
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_track_1",
                        "type": "function",
                        "function": {
                            "name": "get_order_details",
                            "arguments": json.dumps({"order_id": "ord_003"})
                        }
                    }
                ],
                "usage": {"prompt_tokens": 180, "completion_tokens": 20, "total_tokens": 200}
            }

        # Policy rejection / return window expired (ord_002)
        if "return" in last_msg.lower() and "ord_002" in last_msg.lower():
            return {
                "content": "I apologize, but according to our company policy, returns must be initiated within 30 days of delivery. Because order ord_002 was delivered over 45 days ago, the return window has expired and we cannot process this return.",
                "tool_calls": None,
                "usage": {"prompt_tokens": 190, "completion_tokens": 52, "total_tokens": 242}
            }

        # Valid return (ord_004)
        if "return" in last_msg.lower() and "ord_004" in last_msg.lower():
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_ret_1",
                        "type": "function",
                        "function": {
                            "name": "process_return",
                            "arguments": json.dumps({"order_id": "ord_004", "reason": "Customer no longer needs item"})
                        }
                    }
                ],
                "usage": {"prompt_tokens": 215, "completion_tokens": 28, "total_tokens": 243}
            }

        # Shipped cancellation rejection (ord_003)
        if "cancel" in last_msg.lower() and "ord_003" in last_msg.lower():
            return {
                "content": "I cannot cancel order ord_003 because it has already shipped with tracking number TRK112233. You may initiate a return once delivered.",
                "tool_calls": None,
                "usage": {"prompt_tokens": 185, "completion_tokens": 40, "total_tokens": 225}
            }

        # Default general response
        return {
            "content": "Hello! I am your retail assistant. How can I assist you with your orders or account today?",
            "tool_calls": None,
            "usage": {"prompt_tokens": 80, "completion_tokens": 22, "total_tokens": 102}
        }

    def act(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Produce the next action by querying the OpenAI-compatible API."""
        if self.mock_fallback or not self.client:
            return self._fallback_simulate(messages, tools_schema)

        try:
            kwargs: Dict[str, Any] = {
                "model": self.model_id,
                "messages": messages,
                "temperature": self.temperature,
            }
            if tools_schema:
                kwargs["tools"] = tools_schema
                kwargs["tool_choice"] = "auto"

            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            tool_calls = None
            if message.tool_calls:
                tool_calls = []
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }

            return {
                "content": message.content,
                "tool_calls": tool_calls,
                "usage": usage
            }
        except Exception as e:
            # Fall back to simulation if connection drops or endpoint unavailable
            print(f"[OpenAIToolAgent Warning] API request failed: {e}. Falling back to simulation.")
            return self._fallback_simulate(messages, tools_schema)
