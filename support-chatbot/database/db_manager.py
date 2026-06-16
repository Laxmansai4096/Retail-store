"""
database/db_manager.py
----------------------
Lightweight data access layer over dummy JSON files.
Designed so it can be swapped for a real DB (CosmosDB / SQL / etc.)
later without changing agent/tool code — only this file changes.
"""

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

_lock = threading.Lock()


class DBManager:
    """Singleton-style manager that loads JSON 'tables' into memory."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_all()
        return cls._instance

    # ---------- Loading ----------

    def _load_json(self, filename: str) -> Dict[str, Any]:
        path = os.path.join(DATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_all(self):
        with _lock:
            self.inventory_data = self._load_json("inventory.json")
            self.orders_data = self._load_json("orders.json")
            self.refunds_data = self._load_json("refunds.json")
            self.store_data = self._load_json("store_info.json")

    def reload(self):
        """Hot-reload all JSON files from disk (useful in dev)."""
        self._load_all()

    # ---------- Inventory ----------

    def get_all_products(self) -> List[Dict]:
        return self.inventory_data.get("products", [])

    def search_products(self, query: str = "", category: Optional[str] = None,
                         brand: Optional[str] = None, max_price: Optional[float] = None,
                         min_price: Optional[float] = None, in_stock_only: bool = False) -> List[Dict]:
        results = self.get_all_products()
        q = query.lower().strip() if query else ""

        def matches(p):
            if q and q not in p["name"].lower() and q not in p["category"].lower() \
               and q not in p["brand"].lower() and q not in p.get("description", "").lower():
                return False
            if category and category.lower() not in p["category"].lower():
                return False
            if brand and brand.lower() != p["brand"].lower():
                return False
            if max_price is not None and p["price"] > max_price:
                return False
            if min_price is not None and p["price"] < min_price:
                return False
            if in_stock_only and not p["in_stock"]:
                return False
            return True

        return [p for p in results if matches(p)]

    def get_product_by_id(self, product_id: str) -> Optional[Dict]:
        for p in self.get_all_products():
            if p["product_id"].lower() == product_id.lower():
                return p
        return None

    def get_product_by_name(self, name: str) -> Optional[Dict]:
        name_l = name.lower().strip()
        # exact match first
        for p in self.get_all_products():
            if p["name"].lower() == name_l:
                return p
        # partial match fallback
        candidates = [p for p in self.get_all_products() if name_l in p["name"].lower()]
        return candidates[0] if candidates else None

    def check_stock(self, product_id: str) -> Optional[Dict]:
        p = self.get_product_by_id(product_id)
        if not p:
            return None
        return {
            "product_id": p["product_id"],
            "name": p["name"],
            "in_stock": p["in_stock"],
            "stock_quantity": p["stock_quantity"],
            "restock_date": p.get("restock_date"),
            "discontinued": p.get("discontinued", False),
        }

    def compare_products(self, product_ids: List[str]) -> List[Dict]:
        return [p for pid in product_ids if (p := self.get_product_by_id(pid))]

    def recommend_products(self, category: Optional[str] = None, max_price: Optional[float] = None,
                            min_rating: float = 0, limit: int = 5) -> List[Dict]:
        results = self.search_products(category=category, max_price=max_price, in_stock_only=True)
        results = [p for p in results if p.get("rating", 0) >= min_rating]
        results.sort(key=lambda p: (p.get("rating", 0), p.get("reviews_count", 0)), reverse=True)
        return results[:limit]

    # ---------- Orders ----------

    def get_order_by_id(self, order_id: str) -> Optional[Dict]:
        for o in self.orders_data.get("orders", []):
            if o["order_id"].lower() == order_id.lower():
                return o
        return None

    def get_orders_by_customer(self, customer_id: str) -> List[Dict]:
        return [o for o in self.orders_data.get("orders", [])
                if o["customer_id"].lower() == customer_id.lower()]

    def get_orders_by_status(self, status: str) -> List[Dict]:
        return [o for o in self.orders_data.get("orders", [])
                if o["status"].lower() == status.lower()]

    # ---------- Refunds / Returns ----------

    def get_refund_by_return_id(self, return_id: str) -> Optional[Dict]:
        for r in self.refunds_data.get("refund_requests", []):
            if r["return_id"].lower() == return_id.lower():
                return r
        return None

    def get_refund_by_order_id(self, order_id: str) -> Optional[Dict]:
        for r in self.refunds_data.get("refund_requests", []):
            if r["order_id"].lower() == order_id.lower():
                return r
        return None

    def get_policies(self) -> Dict:
        return self.refunds_data.get("policies", {})

    def create_refund_request(self, order_id: str, product_id: str, reason: str) -> Dict:
        """Simulates creating a new refund/return request record."""
        order = self.get_order_by_id(order_id)
        if not order:
            return {"success": False, "message": f"Order {order_id} not found."}

        if order["status"] not in ("Delivered", "Returned"):
            return {
                "success": False,
                "message": f"Order {order_id} has status '{order['status']}'. "
                            f"Returns can only be initiated for delivered orders. "
                            f"If not yet shipped, request a cancellation instead."
            }

        product_name = next((it["name"] for it in order["items"] if it["product_id"] == product_id),
                             "Unknown product")
        new_return_id = f"RET{datetime.now().strftime('%y%m%d%H%M%S')}"
        new_request = {
            "return_id": new_return_id,
            "order_id": order_id,
            "customer_id": order["customer_id"],
            "product_id": product_id,
            "product_name": product_name,
            "request_date": datetime.now().strftime("%Y-%m-%d"),
            "reason": reason,
            "return_status": "Submitted - Pending Review",
            "refund_status": "Not Started",
            "refund_amount": next((it["price"] for it in order["items"] if it["product_id"] == product_id), 0),
            "refund_method": "Original payment method",
            "expected_refund_date": None,
            "actual_refund_date": None,
            "pickup_status": "Scheduled",
            "pickup_date": None,
        }
        self.refunds_data.setdefault("refund_requests", []).append(new_request)
        return {"success": True, "message": "Return request created successfully.", "data": new_request}

    # ---------- Store Info ----------

    def get_store_info(self) -> Dict:
        return self.store_data

    def get_branches(self, city: Optional[str] = None) -> List[Dict]:
        branches = self.store_data.get("branches", [])
        if city:
            return [b for b in branches if b["city"].lower() == city.lower()]
        return branches

    def get_faqs(self) -> List[Dict]:
        return self.store_data.get("faqs", [])

    def get_policies_general(self) -> Dict:
        return {
            "shipping_info": self.store_data.get("shipping_info", {}),
            "payment_methods": self.store_data.get("payment_methods", []),
            "loyalty_program": self.store_data.get("loyalty_program", {}),
        }


# Convenience global accessor
db = DBManager()
