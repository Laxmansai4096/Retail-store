# ShopSphere Multi-Agent Customer Support Chatbot

Production-style agentic customer support chatbot built on **Azure AI Foundry Agent Service**, with a **Streamlit** chat UI. An orchestrator classifies each user message and routes it to one of four specialist agents, each backed by its own tools and dummy JSON "database."

## Architecture

```
User (Streamlit)
      │
      ▼
 Orchestrator (Azure AI Foundry router agent)
      │  classifies message → inventory | refund | orders | general
      ▼
 ┌───────────┬───────────┬───────────┬───────────┐
 │ Inventory │  Refund/  │  Orders   │  General  │
 │   Agent   │  Returns  │   Agent   │   Agent   │
 │           │   Agent   │           │           │
 └─────┬─────┴─────┬─────┴─────┬─────┴─────┬─────┘
       │           │           │           │
       ▼           ▼           ▼           ▼
   tools/tool_definitions.py  →  database/db_manager.py  →  data/*.json
```

Each specialist is a real Azure AI Foundry **Agent** (persistent definition: model + instructions + function tools) with its own **conversation thread** per chat session. When the agent decides to call a tool, the SDK run pauses with status `requires_action`; the app executes the matching Python function against the JSON "database" and submits the result back via `submit_tool_outputs`, then the agent produces its final answer grounded in real data.

## Project Structure

```
support-chatbot/
├── app.py                      # Streamlit entry point
├── requirements.txt
├── .env.example                 # copy to .env and fill in
├── agents/
│   ├── base_agent.py            # Foundry agent/thread/run/tool-loop wrapper
│   ├── orchestrator.py          # routes messages to specialist agents
│   ├── inventory_agent.py
│   ├── refund_agent.py
│   ├── orders_agent.py
│   └── general_agent.py
├── tools/
│   └── tool_definitions.py      # tool JSON schemas + Python implementations
├── database/
│   └── db_manager.py            # data access layer over JSON files
├── data/
│   ├── inventory.json           # 25 products (in-stock, out-of-stock, low-stock, discontinued, restock dates...)
│   ├── orders.json              # 10 orders covering every status
│   ├── refunds.json             # 5 refund/return cases + full policy doc
│   └── store_info.json          # branches, timings, shipping, payments, loyalty, FAQs
└── utils/
    ├── logger.py
    └── session_manager.py
```

## Database coverage ("x5" cases)

- **Inventory (25 products):** in-stock, out-of-stock with restock date, out-of-stock discontinued, low-stock, high-rating/low-rating, multiple categories (electronics, kitchen, furniture, fitness, travel, bedding), product variants of the same line (e.g. AeroFit Series 3 vs 4) for comparison testing.
- **Orders (10 orders):** Order Placed, Processing, Shipped, Out for Delivery, Delivered, Delayed (with reason), Cancelled (with reason), Payment Failed (with reason), Returned.
- **Refunds (5 requests + policy doc):** Processing, Completed, Rejected (with reason), Pending Cancellation, Cancelled-order refund — plus full return window / non-returnable / cancellation / exchange / damaged-item / partial-refund / delay policies.
- **Store info:** 5 branches across cities with distinct hours/services, shipping & COD rules, payment methods, loyalty tiers, FAQs, social handles.

## Setup

### 1. Azure AI Foundry prerequisites
1. Create an **Azure AI Foundry** resource + project in the [Azure AI Foundry portal](https://ai.azure.com).
2. Deploy a chat model (e.g. `gpt-4o-mini` or `gpt-4o`) inside that project — note the **deployment name**.
3. Copy the **project endpoint** (Project → Overview).
4. Ensure your identity has the **Azure AI User** (or equivalent) role on the project for `DefaultAzureCredential` to work.

### 2. Local environment
```bash
git clone <this-repo>
cd support-chatbot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# edit .env with your AZURE_AI_FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT
az login        # authenticates DefaultAzureCredential for local dev
```

### 4. Run
```bash
streamlit run app.py
```
Open the URL Streamlit prints (default `http://localhost:8501`).

## Try it
- "Is the UltraSound Pro Wireless Earbuds in stock?" → Inventory
- "Compare P1006 and P1025 laptops" → Inventory
- "What's the status of order ORD20260504?" → Orders
- "What's the refund status for RET550010?" → Refund
- "I want to return order ORD20260501, item P1001 — it's defective" → Refund
- "What are your store timings in Chennai?" → General

## Notes on swapping in a real database
Only `database/db_manager.py` reads/writes the JSON files. To move to a real database (Cosmos DB, Azure SQL, etc.), reimplement the methods on `DBManager` against your DB client — `tools/tool_definitions.py` and all agents stay unchanged.

## Production considerations included
- Centralized logging with rotation (`utils/logger.py`)
- Per-session thread isolation so concurrent users don't share agent state
- Router LLM classification with a keyword-based fallback for resilience
- Clean separation of concerns: agents / tools / data access / UI
- `.env`-based config, no secrets in code; `DefaultAzureCredential` supports both `az login` (local) and managed identity / service principal (deployed)

## Next steps for a real production deployment
- Persist `agent_threads` / chat history in a real session store (Redis) instead of Streamlit session state if scaling beyond a single instance.
- Add authentication (Azure AD / Entra ID) in front of the Streamlit app.
- Add automated tests for `tools/tool_definitions.py` and `db_manager.py`.
- Add Application Insights for tracing Foundry agent runs.
- Consider Foundry's **Connected Agents** / handoff feature to let the orchestrator be a Foundry agent itself that calls specialist agents as tools, instead of app-level routing.
