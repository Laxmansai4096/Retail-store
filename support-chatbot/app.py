"""
app.py
-------
Streamlit front-end for the ShopSphere multi-agent customer support chatbot,
powered by Azure AI Foundry Agent Service.

Run with:
    streamlit run app.py
"""

import os
import sys
import traceback

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from utils.session_manager import SessionManager
from utils.logger import get_logger

logger = get_logger("app")

st.set_page_config(
    page_title="ShopSphere Support",
    page_icon="🛍️",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ===================== STYLING =====================

CUSTOM_CSS = """
<style>
:root {
    --ss-ink: #1d2230;
    --ss-paper: #faf8f5;
    --ss-coral: #e8603c;
    --ss-teal: #1f6f6b;
    --ss-muted: #8b8579;
    --ss-line: #e4ddd2;
}

.stApp {
    background: var(--ss-paper);
}

[data-testid="stSidebar"] {
    background: #21262f;
}
[data-testid="stSidebar"] * {
    color: #eee9e0 !important;
}
[data-testid="stSidebar"] .stButton button {
    background: var(--ss-coral) !important;
    color: white !important;
    border: none;
}

h1, h2, h3 {
    color: var(--ss-ink) !important;
    font-family: 'Georgia', 'Times New Roman', serif;
}

.ss-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 6px;
}
.ss-badge-inventory { background: #fde8e0; color: var(--ss-coral); }
.ss-badge-refund    { background: #e3f0ef; color: var(--ss-teal); }
.ss-badge-orders    { background: #eef0fb; color: #4b4fb0; }
.ss-badge-general   { background: #f1efe9; color: var(--ss-muted); }

.ss-header {
    border-bottom: 1px solid var(--ss-line);
    padding-bottom: 14px;
    margin-bottom: 18px;
}
.ss-header h1 { margin-bottom: 2px; font-size: 28px; }
.ss-header p { color: var(--ss-muted); margin: 0; font-size: 14px; }

[data-testid="stChatMessage"] {
    background: white;
    border: 1px solid var(--ss-line);
    border-radius: 10px;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

AGENT_LABELS = {
    "inventory": ("📦 Inventory", "ss-badge-inventory"),
    "refund": ("💳 Refunds & Returns", "ss-badge-refund"),
    "orders": ("🚚 Orders", "ss-badge-orders"),
    "general": ("🏬 General", "ss-badge-general"),
    None: ("🤖 Assistant", "ss-badge-general"),
}

SAMPLE_QUERIES = [
    "Is the UltraSound Pro Wireless Earbuds in stock?",
    "Compare P1006 and P1025 laptops",
    "Recommend a good office chair under ₹15000",
    "What's the status of order ORD20260504?",
    "Track my delivery for ORD20260506",
    "What's the refund status for RET550010?",
    "I want to return order ORD20260501, item P1001 — it's defective",
    "Can I cancel order ORD20260507?",
    "What are your store timings in Chennai?",
    "What payment methods do you accept?",
]


# ===================== SESSION STATE =====================

def init_session():
    if "session" not in st.session_state:
        st.session_state.session = SessionManager()
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = None
    if "init_error" not in st.session_state:
        st.session_state.init_error = None


def get_orchestrator():
    if st.session_state.orchestrator is not None:
        return st.session_state.orchestrator
    try:
        from agents.orchestrator import Orchestrator
        st.session_state.orchestrator = Orchestrator()
        st.session_state.init_error = None
    except Exception as e:
        st.session_state.init_error = str(e)
        logger.error(f"Failed to initialize orchestrator: {e}\n{traceback.format_exc()}")
    return st.session_state.orchestrator


init_session()
session: SessionManager = st.session_state.session


# ===================== SIDEBAR =====================

with st.sidebar:
    st.markdown("## 🛍️ ShopSphere")
    st.caption("Multi-agent support, powered by Azure AI Foundry")

    st.markdown("---")
    st.markdown("**Optional: link your customer ID**")
    customer_id_input = st.text_input(
        "Customer ID", value=session.customer_id or "", placeholder="e.g. CUST001",
        label_visibility="collapsed"
    )
    if customer_id_input and customer_id_input != session.customer_id:
        session.set_customer_id(customer_id_input.strip())

    st.markdown("---")
    st.markdown("**Agents in this system**")
    for key, (label, cls) in AGENT_LABELS.items():
        if key:
            st.markdown(f"<span class='ss-badge {cls}'>{label}</span>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("**Try asking:**")
    for q in SAMPLE_QUERIES:
        if st.button(q, key=f"sample_{q}", use_container_width=True):
            st.session_state["pending_query"] = q

    st.markdown("---")
    if st.button("🔄 Reset conversation", use_container_width=True):
        session.reset()
        st.rerun()

    st.markdown("---")
    st.caption("Sample data only. Order IDs like ORD20260501, return IDs like RET550010, product IDs like P1001 are available for testing.")


# ===================== HEADER =====================

st.markdown(
    """
    <div class="ss-header">
        <h1>ShopSphere Support</h1>
        <p>Ask about products, orders, refunds & returns, or store info — routed automatically to the right specialist agent.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.init_error:
    st.error(
        "⚠️ Could not connect to Azure AI Foundry. Check your `.env` configuration "
        "(AZURE_AI_FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT) and Azure CLI login "
        "(`az login`).\n\n"
        f"Details: {st.session_state.init_error}"
    )
    st.stop()


# ===================== CHAT HISTORY RENDER =====================

for msg in session.chat_history:
    role = msg["role"]
    avatar = "🧑" if role == "user" else "🤖"
    with st.chat_message(role, avatar=avatar):
        if role == "assistant" and msg.get("agent"):
            label, cls = AGENT_LABELS.get(msg["agent"], AGENT_LABELS[None])
            st.markdown(f"<span class='ss-badge {cls}'>{label}</span>", unsafe_allow_html=True)
        st.markdown(msg["content"])


# ===================== INPUT HANDLING =====================

pending_query = st.session_state.pop("pending_query", None)
user_input = st.chat_input("Type your question here...")

final_input = pending_query or user_input

if final_input:
    session.add_message("user", final_input)
    with st.chat_message("user", avatar="🧑"):
        st.markdown(final_input)

    orchestrator = get_orchestrator()
    if orchestrator is None:
        st.error("Orchestrator unavailable. Please check Azure AI Foundry configuration.")
    else:
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("Routing to the right specialist agent..."):
                try:
                    result = orchestrator.handle_message(session, final_input)
                    response_text = result["response"]
                    agent_used = result["agent"]
                except Exception as e:
                    logger.error(f"Error handling message: {e}\n{traceback.format_exc()}")
                    response_text = (
                        "Something went wrong while processing your request. "
                        "Please try again, or contact support at 1800-123-4567."
                    )
                    agent_used = None
                    

            if agent_used:
                label, cls = AGENT_LABELS.get(agent_used, AGENT_LABELS[None])
                st.markdown(f"<span class='ss-badge {cls}'>{label}</span>", unsafe_allow_html=True)
            st.markdown(response_text)

        session.add_message("assistant", response_text, agent=agent_used)
