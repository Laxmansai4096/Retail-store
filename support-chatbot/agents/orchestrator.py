"""
agents/orchestrator.py
-------------------------
Orchestrator: classifies each incoming user message into one of the four
domains (inventory / refund / orders / general) and dispatches it to the
right specialist Azure AI Foundry agent. Also keeps a router-only Foundry
agent (lightweight, no tools) purely for classification, so routing logic
itself is LLM-driven rather than brittle keyword matching, with a keyword
fallback for resilience/cost control.

This mirrors a common Azure AI Foundry multi-agent pattern: a top-level
"triage" agent hands off to domain specialist agents, each with their own
thread, instructions, and tools.

SDK COMPATIBILITY:
  All Azure SDK calls go through _SDKBridge from base_agent.py, which
  auto-detects classic vs new API at runtime.
"""

import json
import os
import re
from typing import Dict, Optional, Tuple

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from agents.base_agent import _SDKBridge
from agents.inventory_agent import InventoryAgent
from agents.refund_agent import RefundAgent
from agents.orders_agent import OrdersAgent
from agents.general_agent import GeneralAgent
from utils.logger import get_logger
from utils.session_manager import SessionManager

logger = get_logger(__name__)

ROUTER_INSTRUCTIONS = """You are a routing classifier for ShopSphere customer support.
Classify the user's message into exactly ONE of these categories:

- inventory: product availability, stock, product details/specs, recommendations, product comparisons
- refund: refund status/amount, returns, cancellations, refund/return/cancellation policy
- orders: order status, delivery tracking, courier/ETA, order history
- general: store timings, branch locations, shipping/payment methods, loyalty program, FAQs, greetings, anything else

Respond with ONLY a JSON object: {"category": "<one of: inventory, refund, orders, general>", "confidence": <0-1 float>}
No other text.
"""

# Lightweight keyword fallback if the router LLM call fails or is ambiguous
_KEYWORD_MAP = {
    "refund": ["refund", "return", "cancel", "cancellation", "money back", "exchange"],
    "orders": ["order status", "track", "tracking", "delivery", "shipped", "courier", "eta", "delayed", "out for delivery"],
    "inventory": ["stock", "available", "availability", "price of", "spec", "compare", "recommend", "details of", "in stock"],
    "general": ["timing", "hours", "branch", "store location", "open", "close", "payment method", "shipping cost", "loyalty", "faq", "contact"],
}


class Orchestrator:
    """Routes user messages to the right specialist agent and manages session."""

    def __init__(self):
        self.project_endpoint = os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
        self.model_deployment_name = os.getenv("AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o-mini")

        # Specialist agents (lazy Foundry agent creation happens on first use)
        self.inventory_agent = InventoryAgent(self.project_endpoint, self.model_deployment_name)
        self.refund_agent = RefundAgent(self.project_endpoint, self.model_deployment_name)
        self.orders_agent = OrdersAgent(self.project_endpoint, self.model_deployment_name)
        self.general_agent = GeneralAgent(self.project_endpoint, self.model_deployment_name)

        self.agents_by_key = {
            "inventory": self.inventory_agent,
            "refund": self.refund_agent,
            "orders": self.orders_agent,
            "general": self.general_agent,
        }

        # Separate lightweight client + SDK bridge for routing classification only
        self.router_client = AIProjectClient(
            endpoint=self.project_endpoint,
            credential=DefaultAzureCredential(),
        )
        self._router_sdk = _SDKBridge(self.router_client)  # ← ALL router calls go through this
        self._router_agent_id: Optional[str] = None
        self._router_thread_id: Optional[str] = None

    # ---------- Routing ----------

    def _ensure_router_agent(self) -> str:
        if self._router_agent_id:
            return self._router_agent_id
        agent = self._router_sdk.create_agent(
            model=self.model_deployment_name,
            name="ShopSphere-Router-Agent",
            instructions=ROUTER_INSTRUCTIONS,
        )
        self._router_agent_id = agent.id
        logger.info(f"Created router agent id={agent.id}")
        return self._router_agent_id

    def _ensure_router_thread(self) -> str:
        if self._router_thread_id:
            return self._router_thread_id
        thread = self._router_sdk.create_thread()           # ← was: self.router_client.agents.create_thread()
        self._router_thread_id = thread.id
        return self._router_thread_id

    def classify(self, user_message: str) -> Tuple[str, float]:
        """Returns (category, confidence). Falls back to keyword match on failure."""
        try:
            agent_id = self._ensure_router_agent()
            thread_id = self._ensure_router_thread()

            self._router_sdk.create_message(                 # ← was: self.router_client.agents.messages.create(...)
                thread_id=thread_id, role="user", content=user_message
            )

            run = self._router_sdk.create_and_process_run(   # ← was: self.router_client.agents.runs.create_and_process(...)
                thread_id=thread_id, agent_id=agent_id
            )

            if str(run.status) == "completed":
                messages = self._router_sdk.list_messages(   # ← was: self.router_client.agents.messages.list(...)
                    thread_id=thread_id, order="desc", limit=1
                )
                for msg in messages:
                    if msg.role == "assistant":
                        text = "".join(
                            c.text.value for c in msg.content if hasattr(c, "text")
                        ).strip()
                        parsed = self._parse_router_output(text)
                        if parsed:
                            return parsed
        except Exception as e:
            logger.warning(f"Router LLM classification failed, using keyword fallback: {e}")

        return self._keyword_fallback(user_message)

    def _parse_router_output(self, text: str) -> Optional[Tuple[str, float]]:
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            data = json.loads(match.group(0) if match else text)
            category = data.get("category", "").lower().strip()
            confidence = float(data.get("confidence", 0.5))
            if category in self.agents_by_key:
                return category, confidence
        except Exception:
            pass
        return None

    def _keyword_fallback(self, user_message: str) -> Tuple[str, float]:
        msg_l = user_message.lower()
        scores = {cat: 0 for cat in _KEYWORD_MAP}
        for cat, keywords in _KEYWORD_MAP.items():
            for kw in keywords:
                if kw in msg_l:
                    scores[cat] += 1
        best_cat = max(scores, key=scores.get)
        if scores[best_cat] == 0:
            return "general", 0.3
        return best_cat, min(1.0, 0.5 + 0.15 * scores[best_cat])

    # ---------- Dispatch ----------

    def handle_message(self, session: SessionManager, user_message: str) -> Dict:
        """
        Main entry point: classifies the message, ensures a thread exists for
        the chosen specialist agent on this session, runs it, and returns a
        dict with the response text and routing metadata.
        """
        category, confidence = self.classify(user_message)
        logger.info(f"Routed message to '{category}' (confidence={confidence:.2f})")

        agent = self.agents_by_key[category]

        thread_id = session.get_thread_id(category)
        if not thread_id:
            thread_id = agent.create_thread()
            session.set_thread_id(category, thread_id)

        extra_context = ""
        if session.customer_id:
            extra_context = f"customer_id={session.customer_id}"

        response_text = agent.run(thread_id, user_message, extra_context=extra_context)

        session.last_agent_used = category
        return {
            "response": response_text,
            "agent": category,
            "confidence": confidence,
        }
