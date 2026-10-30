import random
from typing import Any, Dict, List, Tuple


def generate_crm_benchmark(num_tasks: int = 30, seed: int = 42) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generates parameterized CRM benchmark tasks and a matching mock database.
    Provides realistic diversity across customers, catalog items, pricing,
    delivery dates, and task goals.
    """
    rng = random.Random(seed)

    first_names = [
        "Sarah", "David", "Elena", "Marcus", "Aisha", "Liam", "Sophia", "Chen",
        "Amara", "Carlos", "Priya", "Nikolai", "Fatima", "Jordan", "Mei", "Hannah"
    ]
    last_names = [
        "Connor", "Miller", "Rostova", "Vance", "Patel", "Dubois", "Kim", "Larsson",
        "Okafor", "Santana", "Sharma", "Volkov", "Al-Mansoor", "Taylor", "Zhang", "Schmidt"
    ]
    domains = [
        "cyberdyne.org", "techflow.io", "novacorp.com", "apex.ai", "hyperion.net",
        "quantumscale.dev", "cloudcore.org", "vanguardlogic.io"
    ]
    
    cities = [
        ("Los Angeles", "CA", "90001"),
        ("San Diego", "CA", "92101"),
        ("Boston", "MA", "02108"),
        ("Austin", "TX", "78701"),
        ("Seattle", "WA", "98101"),
        ("Chicago", "IL", "60601"),
        ("New York", "NY", "10001"),
        ("Denver", "CO", "80202")
    ]
    streets = [
        "SkyNet Way", "Ocean View Drive", "Beacon Street", "Market Street",
        "Silicon Ave", "Pike Street", "Michigan Ave", "Broadway", "Colfax Ave"
    ]

    products = {
        "prd_01": {"name": "Noise-Cancelling Wireless Headphones", "price": 149.99, "stock": 40},
        "prd_02": {"name": "Ergonomic Mechanical Keyboard", "price": 89.99, "stock": 25},
        "prd_03": {"name": "USB-C Fast Charging Hub", "price": 45.00, "stock": 80},
        "prd_04": {"name": "Ultra-Wide 4K IPS Monitor", "price": 320.00, "stock": 15},
        "prd_05": {"name": "Thunderbolt 4 Docking Station", "price": 199.50, "stock": 30},
        "prd_06": {"name": "Wireless Vertical Mouse", "price": 59.95, "stock": 65},
        "prd_07": {"name": "Studio Condenser Microphone", "price": 129.00, "stock": 20},
        "prd_08": {"name": "Active Stylus Pen", "price": 39.99, "stock": 90},
    }
    prod_ids = list(products.keys())

    users: Dict[str, Any] = {}
    orders: Dict[str, Any] = {}
    tasks: List[Dict[str, Any]] = []

    categories = [
        "order_cancellation",
        "address_change_valid",
        "policy_rejection_return_window",
        "return_valid_window",
        "policy_rejection_shipped_cancel",
        "read_only_tracking_inquiry",
    ]

    for idx in range(num_tasks):
        cat = categories[idx % len(categories)]
        uid = f"usr_{100 + idx}"
        oid = f"ord_{idx + 1:03d}"
        
        prd_id = prod_ids[idx % len(prod_ids)]
        prd = products[prd_id]
        qty = (idx % 2) + 1
        total_price = round(prd["price"] * qty, 2)

        first = first_names[idx % len(first_names)]
        last = last_names[(idx + 3) % len(last_names)]
        name = f"{first} {last}"
        email = f"{first.lower()}.{last.lower()}@{rng.choice(domains)}"
        city, state, zip_code = rng.choice(cities)
        street_num = 100 + (idx * 17) % 800
        addr = f"{street_num} {rng.choice(streets)}, {city}, {state} {zip_code}"

        users[uid] = {
            "user_id": uid,
            "name": name,
            "email": email,
            "phone": f"+1-555-01{idx:02d}",
            "address": addr,
            "verified": False,
            "orders": [oid],
        }

        if cat == "order_cancellation":
            orders[oid] = {
                "order_id": oid,
                "user_id": uid,
                "status": "processing",
                "order_date": "2026-10-25",
                "items": [{"product_id": prd_id, "qty": qty, "price": prd["price"]}],
                "total_amount": total_price,
                "shipping_address": addr,
                "tracking_number": None,
                "refund_issued": 0.0,
            }
            tasks.append({
                "id": f"task_{idx:02d}",
                "category": cat,
                "description": f"Customer {name} cancels processing order {oid}.",
                "user_goal": f"Hi, I need to cancel my recent order {oid} right away.",
                "user_id": uid,
                "user_name": name,
                "user_email": email,
                "expected_action": {
                    "order_id": oid,
                    "target_field": "status",
                    "target_value": "cancelled",
                    "expected_refund": total_price
                },
                "expected_output_keywords": ["cancelled", "refund"],
                "requires_verification": True,
            })

        elif cat == "address_change_valid":
            dest_city, dest_state, dest_zip = rng.choice(cities)
            dest_street = rng.choice(streets)
            new_addr = f"{200 + idx * 13} {dest_street}, {dest_city}, {dest_state} {dest_zip}"
            orders[oid] = {
                "order_id": oid,
                "user_id": uid,
                "status": "pending",
                "order_date": "2026-10-27",
                "items": [{"product_id": prd_id, "qty": qty, "price": prd["price"]}],
                "total_amount": total_price,
                "shipping_address": addr,
                "tracking_number": None,
                "refund_issued": 0.0,
            }
            tasks.append({
                "id": f"task_{idx:02d}",
                "category": cat,
                "description": f"Customer {name} updates shipping destination for pending order {oid}.",
                "user_goal": f"Please update the shipping address for order {oid} to {new_addr}.",
                "user_id": uid,
                "user_name": name,
                "user_email": email,
                "expected_action": {
                    "order_id": oid,
                    "target_field": "shipping_address",
                    "target_value": new_addr
                },
                "expected_output_keywords": ["updated", "address"],
                "requires_verification": True,
            })

        elif cat == "policy_rejection_return_window":
            days_expired = rng.choice([35, 42, 50, 65, 90])
            orders[oid] = {
                "order_id": oid,
                "user_id": uid,
                "status": "delivered",
                "order_date": "2026-08-15",
                "delivery_date": "2026-08-20",
                "days_since_delivery": days_expired,
                "items": [{"product_id": prd_id, "qty": qty, "price": prd["price"]}],
                "total_amount": total_price,
                "shipping_address": addr,
                "tracking_number": f"TRK{1000 + idx}",
                "refund_issued": 0.0,
            }
            tasks.append({
                "id": f"task_{idx:02d}",
                "category": cat,
                "description": f"Customer {name} attempts return on order {oid} delivered {days_expired} days ago (window expired).",
                "user_goal": f"I would like to return order {oid} and get my money refunded.",
                "user_id": uid,
                "user_name": name,
                "user_email": email,
                "expected_action": {
                    "order_id": oid,
                    "target_field": "status",
                    "target_value": "delivered",
                    "expected_refund": 0.0
                },
                "expected_output_keywords": ["policy", "30 days", "cannot return"],
                "requires_verification": False,
            })

        elif cat == "return_valid_window":
            days_valid = rng.choice([3, 5, 8, 14, 21])
            orders[oid] = {
                "order_id": oid,
                "user_id": uid,
                "status": "delivered",
                "order_date": "2026-10-18",
                "delivery_date": "2026-10-22",
                "days_since_delivery": days_valid,
                "items": [{"product_id": prd_id, "qty": qty, "price": prd["price"]}],
                "total_amount": total_price,
                "shipping_address": addr,
                "tracking_number": f"TRK{2000 + idx}",
                "refund_issued": 0.0,
            }
            tasks.append({
                "id": f"task_{idx:02d}",
                "category": cat,
                "description": f"Customer {name} returns order {oid} delivered {days_valid} days ago (valid window).",
                "user_goal": f"Please process a return for order {oid}. It arrived a few days ago but I do not need it.",
                "user_id": uid,
                "user_name": name,
                "user_email": email,
                "expected_action": {
                    "order_id": oid,
                    "target_field": "status",
                    "target_value": "returned",
                    "expected_refund": total_price
                },
                "expected_output_keywords": ["return", "refund"],
                "requires_verification": True,
            })

        elif cat == "policy_rejection_shipped_cancel":
            orders[oid] = {
                "order_id": oid,
                "user_id": uid,
                "status": "shipped",
                "order_date": "2026-10-24",
                "items": [{"product_id": prd_id, "qty": qty, "price": prd["price"]}],
                "total_amount": total_price,
                "shipping_address": addr,
                "tracking_number": f"TRK{3000 + idx}",
                "refund_issued": 0.0,
            }
            tasks.append({
                "id": f"task_{idx:02d}",
                "category": cat,
                "description": f"Customer {name} attempts cancellation on already shipped order {oid}.",
                "user_goal": f"Please cancel order {oid} right now, I no longer want it.",
                "user_id": uid,
                "user_name": name,
                "user_email": email,
                "expected_action": {
                    "order_id": oid,
                    "target_field": "status",
                    "target_value": "shipped",
                    "expected_refund": 0.0
                },
                "expected_output_keywords": ["already shipped", "cannot cancel"],
                "requires_verification": False,
            })

        elif cat == "read_only_tracking_inquiry":
            trk = f"TRK{4000 + idx}"
            orders[oid] = {
                "order_id": oid,
                "user_id": uid,
                "status": "shipped",
                "order_date": "2026-10-25",
                "items": [{"product_id": prd_id, "qty": qty, "price": prd["price"]}],
                "total_amount": total_price,
                "shipping_address": addr,
                "tracking_number": trk,
                "refund_issued": 0.0,
            }
            tasks.append({
                "id": f"task_{idx:02d}",
                "category": cat,
                "description": f"Customer {name} requests tracking information for order {oid}.",
                "user_goal": f"Where is my package for order {oid}? Could you share the tracking number?",
                "user_id": uid,
                "user_name": name,
                "user_email": email,
                "expected_action": None,
                "expected_output_keywords": [trk, "shipped"],
                "requires_verification": False,
            })

    db = {"users": users, "orders": orders, "products": products}
    return tasks, db
