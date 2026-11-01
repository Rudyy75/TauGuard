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
    Connects to any OpenAI-compatible endpoint (Ollama, vLLM, Groq, OpenRouter).
    Falls back to deterministic simulation when no endpoint is available.
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

        self.base_url = base_url or os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        self.api_key = api_key or os.getenv("LOCAL_LLM_API_KEY", "ollama")

        self.client = None
        if OpenAI and not mock_fallback:
            try:
                self.client = OpenAI(base_url=self.base_url, api_key=self.api_key)
            except Exception:
                self.client = None

    def _tool_call(self, name: str, args: dict, call_id: str = "call_0") -> dict:
        return {
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}
        }

    def _usage(self, prompt: int, completion: int) -> dict:
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}

    def _fallback_simulate(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Deterministic offline simulation. Routes by message content.
        Looks at task context (injected via system prompt or user message)
        to pick the correct tool action.
        """
        last = messages[-1]
        last_role = last.get("role", "")
        last_msg = last.get("content", "") or ""

        # After a tool result, summarise and close
        if last_role == "tool":
            tool_result = json.loads(last.get("content", "{}"))
            if tool_result.get("status") == "error":
                err_msg = tool_result.get("message", "")
                if "30 days" in err_msg or "expired" in err_msg:
                    return {
                        "content": "I apologize, but we cannot return this order. Our 30 days policy has expired for this delivery.",
                        "tool_calls": None,
                        "usage": self._usage(160, 35)
                    }
                if "shipped" in err_msg or "cancel" in err_msg.lower():
                    return {
                        "content": "I apologize, but this order has already shipped and cannot cancel directly.",
                        "tool_calls": None,
                        "usage": self._usage(150, 30)
                    }
                return {
                    "content": f"I was unable to complete your request: {err_msg}",
                    "tool_calls": None,
                    "usage": self._usage(130, 20)
                }

            # Success — summarise the tool result
            order = tool_result.get("order", {})
            if order:
                trk = order.get("tracking_number", "TRK112233")
                status = order.get("status", "processing")
                oid = order.get("order_id", "order")
                days = order.get("days_since_delivery", 0)

                # Check if this inquiry was about returning an expired order
                if days > 30:
                    return {
                        "content": f"I verified order {oid}. It was delivered {days} days ago. Under our 30 days policy, the return window has expired and we cannot return it.",
                        "tool_calls": None,
                        "usage": self._usage(170, 40)
                    }
                # Check if this inquiry was about cancelling a shipped order
                if status in ("shipped", "delivered"):
                    return {
                        "content": f"I checked order {oid}. It has already shipped with tracking number {trk}, so I cannot cancel it directly.",
                        "tool_calls": None,
                        "usage": self._usage(160, 35)
                    }
                # General tracking inquiry
                return {
                    "content": f"Your order {oid} is {status} with tracking number {trk}.",
                    "tool_calls": None,
                    "usage": self._usage(140, 25)
                }

            msg = tool_result.get("message", "Your request has been processed successfully.")
            return {
                "content": f"{msg} Is there anything else I can assist you with?",
                "tool_calls": None,
                "usage": self._usage(120, 25)
            }

        # Extract order ID and user identity
        user_text = " ".join(
            (m.get("content") or "") for m in messages if m.get("role") == "user"
        )
        oid_match = re.search(r"ord_\d+", user_text, re.IGNORECASE)
        oid = oid_match.group(0).lower() if oid_match else "ord_001"
        msg_lower = user_text.lower()

        # Identity must come from the customer's conversation, never hidden task metadata.
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", user_text)
        user_query = email_match.group(0) if email_match else None
        system_content = " ".join(
            (m.get("content") or "") for m in messages if m.get("role") == "system"
        ).lower()

        if any(word in msg_lower for word in ("cancel", "address", "return")) and not user_query:
            return {
                "content": "I can help with that. What email address is associated with your account so I can verify your identity?",
                "tool_calls": None,
                "usage": self._usage(100, 25)
            }

        # 1. Shipped cancellation rejection (inspect first)
        if "cancel" in msg_lower and ("category: policy_rejection_shipped" in system_content or oid == "ord_003"):
            return {
                "content": None,
                "tool_calls": [self._tool_call("get_order_details", {"order_id": oid}, call_id="call_inspect")],
                "usage": self._usage(160, 20)
            }

        # 2. Valid cancellation (verify identity + cancel)
        if "cancel" in msg_lower:
            return {
                "content": None,
                "tool_calls": [
                    self._tool_call("lookup_user", {"query": user_query}, call_id="call_lookup"),
                    self._tool_call("cancel_order", {"order_id": oid, "reason": "Customer requested cancellation"}, call_id="call_cancel")
                ],
                "usage": self._usage(210, 30)
            }

        # 3. Address update (verify identity + update address)
        if "address" in msg_lower:
            initial_user_goal = next(
                ((m.get("content") or "") for m in messages if m.get("role") == "user"), ""
            )
            addr_match = re.search(r"to\s+(.+)", initial_user_goal, re.IGNORECASE)
            target_addr = addr_match.group(1).strip().rstrip(".") if addr_match else "900 Commonwealth Ave, Boston, MA 02215"
            return {
                "content": None,
                "tool_calls": [
                    self._tool_call("lookup_user", {"query": user_query}, call_id="call_lookup"),
                    self._tool_call("modify_shipping_address", {"order_id": oid, "new_address": target_addr}, call_id="call_addr")
                ],
                "usage": self._usage(220, 32)
            }

        # 4. Tracking inquiry (inspect order)
        if any(w in msg_lower for w in ["tracking", "where is", "package", "tracking number"]):
            return {
                "content": None,
                "tool_calls": [self._tool_call("get_order_details", {"order_id": oid}, call_id="call_track")],
                "usage": self._usage(160, 20)
            }

        # 5. Expired return window rejection (inspect order first)
        if "return" in msg_lower and ("category: policy_rejection_return" in system_content or oid == "ord_002"):
            return {
                "content": None,
                "tool_calls": [self._tool_call("get_order_details", {"order_id": oid}, call_id="call_inspect")],
                "usage": self._usage(160, 20)
            }

        # 6. Valid return (verify identity + process return)
        if "return" in msg_lower:
            return {
                "content": None,
                "tool_calls": [
                    self._tool_call("lookup_user", {"query": user_query}, call_id="call_lookup"),
                    self._tool_call("process_return", {"order_id": oid, "reason": "Customer return request"}, call_id="call_ret")
                ],
                "usage": self._usage(215, 30)
            }

        return {
            "content": "Hello! I am your retail assistant. How can I help you today?",
            "tool_calls": None,
            "usage": self._usage(80, 15)
        }

    def act(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        if self.mock_fallback or not self.client:
            if self.mock_fallback:
                return self._fallback_simulate(messages, tools_schema)
            raise RuntimeError(
                "Live Ollama client is unavailable. Check the OpenAI package and Ollama server; "
                "live runs never fall back to the mock agent."
            )

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
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in message.tool_calls
                ]

            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }

            return {"content": message.content, "tool_calls": tool_calls, "usage": usage}

        except Exception as e:
            raise RuntimeError(f"Live model request failed for {self.model_id}: {e}") from e
