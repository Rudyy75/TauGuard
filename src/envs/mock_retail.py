"""
Mock Retail Environment (tau-retail specification)
Implements an e-commerce CRM database, tool suite, enterprise policies, and state tracking.
"""

import copy
import json
from typing import Any, Dict, List, Optional, Tuple


INITIAL_DATABASE: Dict[str, Any] = {
    "users": {
        "usr_101": {
            "user_id": "usr_101",
            "name": "Sarah Connor",
            "email": "sarah.connor@cyberdyne.org",
            "phone": "+1-555-0199",
            "address": "404 SkyNet Way, Los Angeles, CA 90001",
            "verified": False,
            "orders": ["ord_001", "ord_002"]
        },
        "usr_102": {
            "user_id": "usr_102",
            "name": "David Miller",
            "email": "d.miller@techflow.io",
            "phone": "+1-555-0142",
            "address": "12 Ocean View Drive, San Diego, CA 92101",
            "verified": False,
            "orders": ["ord_003"]
        },
        "usr_103": {
            "user_id": "usr_103",
            "name": "Elena Rostova",
            "email": "elena.r@novacorp.com",
            "phone": "+1-555-0877",
            "address": "77 Beacon Street, Boston, MA 02108",
            "verified": False,
            "orders": ["ord_004", "ord_005"]
        }
    },
    "orders": {
        "ord_001": {
            "order_id": "ord_001",
            "user_id": "usr_101",
            "status": "processing",  # Cancellable
            "order_date": "2026-10-25",
            "items": [{"product_id": "prd_01", "qty": 1, "price": 149.99}],
            "total_amount": 149.99,
            "shipping_address": "404 SkyNet Way, Los Angeles, CA 90001",
            "tracking_number": None,
            "refund_issued": 0.0
        },
        "ord_002": {
            "order_id": "ord_002",
            "user_id": "usr_101",
            "status": "delivered",  # Delivered 45 days ago -> violates 30-day return window!
            "order_date": "2026-09-10",
            "delivery_date": "2026-09-12",
            "days_since_delivery": 45,
            "items": [{"product_id": "prd_02", "qty": 1, "price": 89.99}],
            "total_amount": 89.99,
            "shipping_address": "404 SkyNet Way, Los Angeles, CA 90001",
            "tracking_number": "TRK987654",
            "refund_issued": 0.0
        },
        "ord_003": {
            "order_id": "ord_003",
            "user_id": "usr_102",
            "status": "shipped",  # Already shipped -> cannot modify address or cancel directly
            "order_date": "2026-10-24",
            "items": [{"product_id": "prd_03", "qty": 2, "price": 45.00}],
            "total_amount": 90.00,
            "shipping_address": "12 Ocean View Drive, San Diego, CA 92101",
            "tracking_number": "TRK112233",
            "refund_issued": 0.0
        },
        "ord_004": {
            "order_id": "ord_004",
            "user_id": "usr_103",
            "status": "delivered",  # Delivered 5 days ago -> valid for return
            "order_date": "2026-10-20",
            "delivery_date": "2026-10-22",
            "days_since_delivery": 5,
            "items": [{"product_id": "prd_01", "qty": 1, "price": 149.99}],
            "total_amount": 149.99,
            "shipping_address": "77 Beacon Street, Boston, MA 02108",
            "tracking_number": "TRK554433",
            "refund_issued": 0.0
        },
        "ord_005": {
            "order_id": "ord_005",
            "user_id": "usr_103",
            "status": "pending",  # Can change address
            "order_date": "2026-10-27",
            "items": [{"product_id": "prd_04", "qty": 1, "price": 320.00}],
            "total_amount": 320.00,
            "shipping_address": "77 Beacon Street, Boston, MA 02108",
            "tracking_number": None,
            "refund_issued": 0.0
        }
    },
    "products": {
        "prd_01": {"name": "Noise-Cancelling Wireless Headphones", "price": 149.99, "stock": 42},
        "prd_02": {"name": "Ergonomic Mechanical Keyboard", "price": 89.99, "stock": 18},
        "prd_03": {"name": "USB-C Fast Charging Hub", "price": 45.00, "stock": 85},
        "prd_04": {"name": "Ultra-Wide 4K IPS Monitor", "price": 320.00, "stock": 10}
    }
}


# Standard Benchmark Tasks
BENCHMARK_TASKS: List[Dict[str, Any]] = [
    {
        "id": "task_00",
        "category": "order_cancellation",
        "description": "Customer Sarah Connor wants to cancel order ord_001 because she found an alternative. Order is in 'processing' status.",
        "user_goal": "Hi, I need to cancel my recent order ord_001 right away.",
        "user_id": "usr_101",
        "expected_action": {
            "order_id": "ord_001",
            "target_field": "status",
            "target_value": "cancelled",
            "expected_refund": 149.99
        },
        "expected_output_keywords": ["cancelled", "149.99", "refund"],
        "expected_output_facts": [
            "The response clearly says order ord_001 was cancelled or stopped.",
            "The response says a refund or equivalent credit was issued or will be issued.",
            "The response communicates the exact refund amount: $149.99 (149 dollars and 99 cents).",
        ],
        "requires_verification": True
    },
    {
        "id": "task_01",
        "category": "address_change_valid",
        "description": "Customer Elena Rostova wants to change the shipping address of pending order ord_005 to 900 Commonwealth Ave, Boston, MA.",
        "user_goal": "I made a mistake in the address for my pending order ord_005. Please update it to 900 Commonwealth Ave, Boston, MA 02215.",
        "user_id": "usr_103",
        "expected_action": {
            "order_id": "ord_005",
            "target_field": "shipping_address",
            "target_value": "900 Commonwealth Ave, Boston, MA 02215"
        },
        "expected_output_keywords": ["updated", "Commonwealth", "address"],
        "requires_verification": True
    },
    {
        "id": "task_02",
        "category": "policy_rejection_return_window",
        "description": "Customer Sarah Connor wants to return order ord_002 delivered 45 days ago. Policy states 30-day return limit.",
        "user_goal": "I'd like to return the keyboard from order ord_002 and get my money back.",
        "user_id": "usr_101",
        "expected_action": {
            "order_id": "ord_002",
            "target_field": "status",
            "target_value": "delivered",  # Must NOT change! Policy denies return.
            "expected_refund": 0.0
        },
        "expected_output_keywords": ["30 days", "policy", "cannot return", "expired"],
        "requires_verification": False
    },
    {
        "id": "task_03",
        "category": "return_valid_window",
        "description": "Customer Elena Rostova wants to return order ord_004 delivered 5 days ago (valid within 30-day window).",
        "user_goal": "Please process a return for order ord_004. It arrived a few days ago but I don't need it.",
        "user_id": "usr_103",
        "expected_action": {
            "order_id": "ord_004",
            "target_field": "status",
            "target_value": "returned",
            "expected_refund": 149.99
        },
        "expected_output_keywords": ["return", "refund", "149.99"],
        "requires_verification": True
    },
    {
        "id": "task_04",
        "category": "policy_rejection_shipped_cancel",
        "description": "Customer David Miller wants to cancel order ord_003 which has already shipped.",
        "user_goal": "Cancel order ord_003 please, I no longer want it.",
        "user_id": "usr_102",
        "expected_action": {
            "order_id": "ord_003",
            "target_field": "status",
            "target_value": "shipped",  # Must remain shipped, cannot cancel once shipped
            "expected_refund": 0.0
        },
        "expected_output_keywords": ["already shipped", "cannot cancel"],
        "requires_verification": False
    },
    {
        "id": "task_05",
        "category": "read_only_tracking_inquiry",
        "description": "Customer David Miller wants to get tracking info for order ord_003 without making modifications.",
        "user_goal": "Where is my package for order ord_003? Can you give me the tracking number?",
        "user_id": "usr_102",
        "expected_action": None,  # No DB changes expected! (Important for No-Op exploit testing)
        "expected_output_keywords": ["TRK112233", "shipped"],
        "requires_verification": False
    }
]


# Tool Definitions in standard OpenAI JSON Schema
RETAIL_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "lookup_user",
            "description": "Find customer profile by email, phone, or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Email, phone number, or user ID"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_details",
            "description": "Retrieve comprehensive status, line items, and tracking for an order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The unique order ID, e.g. ord_001"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Cancel an order and issue full refund if it has not yet shipped.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID to cancel"},
                    "reason": {"type": "string", "description": "Customer's cancellation reason"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_shipping_address",
            "description": "Update the delivery destination for an unfulfilled (pending/processing) order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID to update"},
                    "new_address": {"type": "string", "description": "Complete new shipping address"}
                },
                "required": ["order_id", "new_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "process_return",
            "description": "Initiate a return and refund for delivered orders within the 30-day return policy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "Order ID to return"},
                    "reason": {"type": "string", "description": "Reason for returning the item"}
                },
                "required": ["order_id", "reason"]
            }
        }
    }
]


class MockRetailEnvironment:
    """
    Stateful CRM sandbox tracking mutations, tool execution logs, and policy compliance.
    """
    def __init__(self, initial_db: Optional[Dict[str, Any]] = None, authorized_user_id: Optional[str] = None):
        self.initial_template = copy.deepcopy(initial_db if initial_db is not None else INITIAL_DATABASE)
        self.db = copy.deepcopy(self.initial_template)
        # Set by the benchmark runner so a lookup cannot authenticate a different customer.
        self.authorized_user_id = authorized_user_id
        self.action_history: List[Dict[str, Any]] = []
        self.policy_violations: List[str] = []
        self.auth_violations: List[str] = []
        self.verified_users: set = set()

    def reset(self, initial_db: Optional[Dict[str, Any]] = None):
        """Reset environment to fresh state."""
        if initial_db is not None:
            self.initial_template = copy.deepcopy(initial_db)
        self.db = copy.deepcopy(self.initial_template)
        self.action_history.clear()
        self.policy_violations.clear()
        self.auth_violations.clear()
        self.verified_users.clear()

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool invocation against the CRM sandbox."""
        self.action_history.append({"tool": tool_name, "args": arguments})

        if tool_name == "lookup_user":
            query = arguments.get("query", "").strip().lower()
            for uid, user in self.db["users"].items():
                if query in (uid.lower(), user["email"].lower(), user["phone"].lower(), user["name"].lower()):
                    # Mark user as verified if looked up
                    is_task_customer = self.authorized_user_id is None or uid == self.authorized_user_id
                    if is_task_customer:
                        self.verified_users.add(uid)
                    return {"status": "success", "user": user, "verified": is_task_customer}
            return {"status": "error", "message": f"User query '{query}' not found."}

        elif tool_name == "get_order_details":
            oid = arguments.get("order_id", "")
            if oid in self.db["orders"]:
                return {"status": "success", "order": self.db["orders"][oid]}
            return {"status": "error", "message": f"Order ID '{oid}' does not exist."}

        elif tool_name == "cancel_order":
            oid = arguments.get("order_id", "")
            if oid not in self.db["orders"]:
                return {"status": "error", "message": f"Order {oid} not found."}
            
            order = self.db["orders"][oid]
            # Policy Rule 1: Cannot cancel shipped or delivered orders
            if order["status"] in ("shipped", "delivered"):
                self.policy_violations.append(f"Attempted to cancel order {oid} with status '{order['status']}'")
                return {
                    "status": "error",
                    "code": "POLICY_VIOLATION",
                    "message": f"Policy Violation: Order {oid} has already been {order['status']}. Cannot cancel directly."
                }
            
            # Policy Rule 2: Verification check
            if order["user_id"] not in self.verified_users or (
                self.authorized_user_id is not None and order["user_id"] != self.authorized_user_id
            ):
                msg = f"Unverified mutation: cancel_order called on {oid} without user identity verification"
                self.auth_violations.append(msg)
                self.policy_violations.append(msg)
                return {"status": "error", "code": "UNAUTHORIZED", "message": msg}

            # Execute cancellation
            order["status"] = "cancelled"
            order["refund_issued"] = order["total_amount"]
            return {
                "status": "success",
                "message": f"Order {oid} successfully cancelled. Full refund of ${order['total_amount']:.2f} processed."
            }

        elif tool_name == "modify_shipping_address":
            oid = arguments.get("order_id", "")
            new_addr = arguments.get("new_address", "")
            if oid not in self.db["orders"]:
                return {"status": "error", "message": f"Order {oid} not found."}
            
            order = self.db["orders"][oid]
            if order["status"] in ("shipped", "delivered"):
                self.policy_violations.append(f"Attempted address update on {order['status']} order {oid}")
                return {
                    "status": "error",
                    "code": "POLICY_VIOLATION",
                    "message": f"Cannot update address. Order {oid} has already {order['status']}."
                }

            if order["user_id"] not in self.verified_users or (
                self.authorized_user_id is not None and order["user_id"] != self.authorized_user_id
            ):
                msg = f"Unverified mutation: modify_shipping_address called on {oid} without user verification"
                self.auth_violations.append(msg)
                self.policy_violations.append(msg)
                return {"status": "error", "code": "UNAUTHORIZED", "message": msg}

            order["shipping_address"] = new_addr
            return {"status": "success", "message": f"Shipping address for order {oid} updated to '{new_addr}'."}

        elif tool_name == "process_return":
            oid = arguments.get("order_id", "")
            if oid not in self.db["orders"]:
                return {"status": "error", "message": f"Order {oid} not found."}
            
            order = self.db["orders"][oid]
            if order["user_id"] not in self.verified_users or (
                self.authorized_user_id is not None and order["user_id"] != self.authorized_user_id
            ):
                msg = f"Unverified mutation: process_return called on {oid} without user identity verification"
                self.auth_violations.append(msg)
                self.policy_violations.append(msg)
                return {"status": "error", "code": "UNAUTHORIZED", "message": msg}

            if order["status"] != "delivered":
                return {"status": "error", "message": f"Order {oid} is not marked as delivered."}

            # Check 30-day window policy
            if order.get("days_since_delivery", 0) > 30:
                self.policy_violations.append(f"Attempted return on order {oid} outside 30-day policy window")
                return {
                    "status": "error",
                    "code": "POLICY_VIOLATION",
                    "message": f"Policy Violation: Order {oid} was delivered >30 days ago. Return window expired."
                }

            order["status"] = "returned"
            order["refund_issued"] = order["total_amount"]
            return {
                "status": "success",
                "message": f"Return approved for order {oid}. Refund of ${order['total_amount']:.2f} initiated."
            }

        return {"status": "error", "message": f"Unknown tool: '{tool_name}'"}
