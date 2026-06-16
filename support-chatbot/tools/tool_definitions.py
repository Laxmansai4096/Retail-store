"""
tools/tool_definitions.py
--------------------------
Defines the function tools exposed to Azure AI Foundry Agents.
Each tool has:
  - a JSON schema (for the Foundry Agent 'function' tool definition)
  - a Python callable (executed locally when the agent requests a tool call)

This mirrors the Azure AI Foundry Agent Service "function calling" pattern:
the agent decides which tool to call -> we execute it locally -> we return
the result back to the agent run via submit_tool_outputs.
"""

import json
from typing import Any, Dict

from database.db_manager import db


# ===================== INVENTORY TOOLS =====================

def tool_search_products(query: str = "", category: str = None, brand: str = None,
                          max_price: float = None, min_price: float = None,
                          in_stock_only: bool = False) -> str:
    results = db.search_products(query=query, category=category, brand=brand,
                                  max_price=max_price, min_price=min_price,
                                  in_stock_only=in_stock_only)
    return json.dumps({"count": len(results), "products": results[:10]}, default=str)


def tool_get_product_details(product_id: str = None, product_name: str = None) -> str:
    product = None
    if product_id:
        product = db.get_product_by_id(product_id)
    if not product and product_name:
        product = db.get_product_by_name(product_name)
    if not product:
        return json.dumps({"found": False, "message": "Product not found."})
    return json.dumps({"found": True, "product": product}, default=str)


def tool_check_stock(product_id: str = None, product_name: str = None) -> str:
    if not product_id and product_name:
        p = db.get_product_by_name(product_name)
        product_id = p["product_id"] if p else None
    if not product_id:
        return json.dumps({"found": False, "message": "Product not found."})
    stock = db.check_stock(product_id)
    if not stock:
        return json.dumps({"found": False, "message": "Product not found."})
    return json.dumps({"found": True, "stock": stock}, default=str)


def tool_compare_products(product_ids: list) -> str:
    products = db.compare_products(product_ids)
    if not products:
        return json.dumps({"found": False, "message": "No matching products found."})
    return json.dumps({"found": True, "products": products}, default=str)


def tool_recommend_products(category: str = None, max_price: float = None,
                             min_rating: float = 0, limit: int = 5) -> str:
    results = db.recommend_products(category=category, max_price=max_price,
                                     min_rating=min_rating, limit=limit)
    return json.dumps({"count": len(results), "recommendations": results}, default=str)


# ===================== ORDERS TOOLS =====================

def tool_get_order_status(order_id: str) -> str:
    order = db.get_order_by_id(order_id)
    if not order:
        return json.dumps({"found": False, "message": f"Order {order_id} not found. Please check the order ID."})
    return json.dumps({"found": True, "order": order}, default=str)


def tool_get_orders_by_customer(customer_id: str) -> str:
    orders = db.get_orders_by_customer(customer_id)
    if not orders:
        return json.dumps({"found": False, "message": f"No orders found for customer {customer_id}."})
    return json.dumps({"found": True, "count": len(orders), "orders": orders}, default=str)


def tool_get_delivery_details(order_id: str) -> str:
    order = db.get_order_by_id(order_id)
    if not order:
        return json.dumps({"found": False, "message": f"Order {order_id} not found."})
    delivery_info = {
        "order_id": order["order_id"],
        "status": order["status"],
        "tracking_id": order.get("tracking_id"),
        "courier_partner": order.get("courier_partner"),
        "delivery_address": order.get("delivery_address"),
        "expected_delivery_date": order.get("expected_delivery_date"),
        "delivered_date": order.get("delivered_date"),
        "delay_reason": order.get("delay_reason"),
    }
    return json.dumps({"found": True, "delivery": delivery_info}, default=str)


# ===================== REFUND / RETURN TOOLS =====================

def tool_get_refund_status(return_id: str = None, order_id: str = None) -> str:
    refund = None
    if return_id:
        refund = db.get_refund_by_return_id(return_id)
    if not refund and order_id:
        refund = db.get_refund_by_order_id(order_id)
    if not refund:
        return json.dumps({"found": False, "message": "No refund/return request found for given ID."})
    return json.dumps({"found": True, "refund": refund}, default=str)


def tool_get_return_policy() -> str:
    return json.dumps({"policies": db.get_policies()}, default=str)


def tool_create_return_request(order_id: str, product_id: str, reason: str) -> str:
    result = db.create_refund_request(order_id, product_id, reason)
    return json.dumps(result, default=str)


def tool_check_cancellation_eligibility(order_id: str) -> str:
    order = db.get_order_by_id(order_id)
    if not order:
        return json.dumps({"found": False, "message": f"Order {order_id} not found."})
    status = order["status"]
    eligible_statuses = ("Order Placed", "Processing")
    eligible = status in eligible_statuses
    if status == "Out for Delivery":
        msg = "Cannot cancel — order is out for delivery. Please refuse delivery or request a return afterward."
    elif status == "Shipped":
        msg = "Cannot cancel — order has already shipped. Please request a return after delivery."
    elif status == "Delivered":
        msg = "Cannot cancel — order is already delivered. Please request a return instead."
    elif status == "Cancelled":
        msg = "Order is already cancelled."
    elif eligible:
        msg = "Order is eligible for free cancellation."
    else:
        msg = f"Order status is '{status}'; cancellation not applicable."
    return json.dumps({"found": True, "order_id": order_id, "status": status,
                        "eligible_for_cancellation": eligible, "message": msg})


# ===================== GENERAL TOOLS =====================

def tool_get_store_branches(city: str = None) -> str:
    branches = db.get_branches(city=city)
    if not branches:
        return json.dumps({"found": False, "message": f"No branches found for city '{city}'."})
    return json.dumps({"found": True, "branches": branches}, default=str)


def tool_get_store_info() -> str:
    info = db.get_store_info()
    summary = {
        "store_name": info.get("store_name"),
        "tagline": info.get("tagline"),
        "customer_care": info.get("customer_care"),
        "online_store_hours": info.get("online_store_hours"),
        "shipping_info": info.get("shipping_info"),
        "payment_methods": info.get("payment_methods"),
        "loyalty_program": info.get("loyalty_program"),
        "social_media": info.get("social_media"),
    }
    return json.dumps(summary, default=str)


def tool_get_faqs() -> str:
    return json.dumps({"faqs": db.get_faqs()}, default=str)


# ===================== TOOL SCHEMAS (Azure AI Foundry function format) =====================

INVENTORY_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search products by keyword, category, brand, or price range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free text search keyword"},
                    "category": {"type": "string", "description": "Product category filter"},
                    "brand": {"type": "string", "description": "Brand filter"},
                    "max_price": {"type": "number", "description": "Maximum price filter"},
                    "min_price": {"type": "number", "description": "Minimum price filter"},
                    "in_stock_only": {"type": "boolean", "description": "Only return in-stock items"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Get full details of a specific product by ID or name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_stock",
            "description": "Check stock availability and quantity for a product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"},
                    "product_name": {"type": "string"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_products",
            "description": "Compare two or more products side by side using their product IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_ids": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["product_ids"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_products",
            "description": "Recommend top-rated in-stock products, optionally filtered by category/price/rating.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "max_price": {"type": "number"},
                    "min_rating": {"type": "number"},
                    "limit": {"type": "integer"}
                },
                "required": []
            }
        }
    },
]

ORDERS_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Get the current status and full details of an order by order ID.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_orders_by_customer",
            "description": "List all orders placed by a given customer ID.",
            "parameters": {
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_delivery_details",
            "description": "Get delivery/tracking details (courier, tracking ID, ETA, delay reason) for an order.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"]
            }
        }
    },
]

REFUND_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_refund_status",
            "description": "Get refund/return status using a return ID or order ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "return_id": {"type": "string"},
                    "order_id": {"type": "string"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_return_policy",
            "description": "Get store return, refund, cancellation, and exchange policies.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_return_request",
            "description": "Create a new return/refund request for a delivered order item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "product_id": {"type": "string"},
                    "reason": {"type": "string"}
                },
                "required": ["order_id", "product_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_cancellation_eligibility",
            "description": "Check whether an order is still eligible for free cancellation.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"]
            }
        }
    },
]

GENERAL_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_store_branches",
            "description": "Get store branch addresses, timings, and services, optionally filtered by city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_store_info",
            "description": "Get general store info: hours, customer care contact, shipping, payments, loyalty program.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_faqs",
            "description": "Get frequently asked questions and answers about the store.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
]

# Maps tool name (as called by the LLM) -> python callable
TOOL_FUNCTION_MAP = {
    "search_products": tool_search_products,
    "get_product_details": tool_get_product_details,
    "check_stock": tool_check_stock,
    "compare_products": tool_compare_products,
    "recommend_products": tool_recommend_products,
    "get_order_status": tool_get_order_status,
    "get_orders_by_customer": tool_get_orders_by_customer,
    "get_delivery_details": tool_get_delivery_details,
    "get_refund_status": tool_get_refund_status,
    "get_return_policy": tool_get_return_policy,
    "create_return_request": tool_create_return_request,
    "check_cancellation_eligibility": tool_check_cancellation_eligibility,
    "get_store_branches": tool_get_store_branches,
    "get_store_info": tool_get_store_info,
    "get_faqs": tool_get_faqs,
}


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Executes a tool by name with given arguments dict, returns JSON string result."""
    func = TOOL_FUNCTION_MAP.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        return func(**arguments)
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}"})
