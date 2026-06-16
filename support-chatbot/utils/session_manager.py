"""
utils/session_manager.py
-------------------------
Manages per-user-session conversation state, including Azure AI Foundry
thread IDs for each agent, chat history, and routing context.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional


class SessionManager:
    """Holds state for a single chat session (maps 1:1 to a Streamlit session)."""

    def __init__(self):
        self.session_id: str = str(uuid.uuid4())
        self.created_at: str = datetime.now().isoformat()
        self.chat_history: List[Dict] = []
        # Azure AI Foundry conversation thread IDs per agent (created lazily)
        self.agent_threads: Dict[str, str] = {
            "orchestrator": None,
            "inventory": None,
            "refund": None,
            "orders": None,
            "general": None,
        }
        self.customer_id: Optional[str] = None
        self.last_agent_used: Optional[str] = None

    def add_message(self, role: str, content: str, agent: Optional[str] = None):
        self.chat_history.append({
            "role": role,
            "content": content,
            "agent": agent,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        })

    def get_thread_id(self, agent_key: str) -> Optional[str]:
        return self.agent_threads.get(agent_key)

    def set_thread_id(self, agent_key: str, thread_id: str):
        self.agent_threads[agent_key] = thread_id

    def set_customer_id(self, customer_id: str):
        self.customer_id = customer_id

    def get_history_text(self, max_turns: int = 6) -> str:
        """Returns last N turns formatted as plain text, for lightweight context."""
        recent = self.chat_history[-max_turns:]
        lines = []
        for m in recent:
            speaker = "User" if m["role"] == "user" else f"Assistant ({m.get('agent', 'bot')})"
            lines.append(f"{speaker}: {m['content']}")
        return "\n".join(lines)

    def reset(self):
        self.chat_history.clear()
        for k in self.agent_threads:
            self.agent_threads[k] = None
        self.last_agent_used = None
