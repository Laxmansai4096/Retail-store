"""
agents/base_agent.py
----------------------
Base wrapper around Azure AI Foundry Agent Service (azure-ai-projects /
azure-ai-agents SDK). Each specialized agent (Inventory, Refund, Orders,
General) subclasses this and supplies its own name, instructions, and tools.

Azure AI Foundry concepts used:
  - AIProjectClient: entry point to the Foundry project
  - agents.create_agent(): registers a persistent agent definition (model +
    instructions + tools) in the Foundry project
  - agents.threads.create(): a conversation thread for a given user session
  - agents.messages.create(): adds a user message to the thread
  - agents.runs.create_and_process() / polling loop: runs the agent on the
    thread, pausing on 'requires_action' for our local tool execution,
    then resuming with submit_tool_outputs
"""

import json
import os
import time
from typing import Dict, List, Optional

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import HttpResponseError

from tools.tool_definitions import execute_tool
from utils.logger import get_logger

logger = get_logger(__name__)


class BaseAgent:
    """
    Wraps an Azure AI Foundry Agent: creation, thread management, and the
    run/tool-call loop. Subclasses provide name, instructions, and tool schemas.
    """

    agent_key: str = "base"
    agent_name: str = "BaseAgent"
    instructions: str = "You are a helpful assistant."
    tool_schemas: List[Dict] = []

    def __init__(self, project_endpoint: Optional[str] = None,
                 model_deployment_name: Optional[str] = None):
        self.project_endpoint = project_endpoint or os.getenv("AZURE_AI_FOUNDRY_PROJECT_ENDPOINT")
        self.model_deployment_name = model_deployment_name or os.getenv("AZURE_AI_FOUNDRY_MODEL_DEPLOYMENT", "gpt-4o-mini")

        if not self.project_endpoint:
            raise EnvironmentError(
                "AZURE_AI_FOUNDRY_PROJECT_ENDPOINT is not set. "
                "Set it in your .env file (see .env.example)."
            )

        self.client = AIProjectClient(
            endpoint=self.project_endpoint,
            credential=DefaultAzureCredential(),
        )
        self._agent_id: Optional[str] = None

    # ---------- Agent lifecycle ----------

    def ensure_agent(self) -> str:
        """Creates the Foundry agent definition once and caches its ID."""
        if self._agent_id:
            return self._agent_id

        agent = self.client.agents.create_agent(
            model=self.model_deployment_name,
            name=self.agent_name,
            instructions=self.instructions,
            tools=self.tool_schemas,
        )
        self._agent_id = agent.id
        logger.info(f"Created Foundry agent '{self.agent_name}' with id={agent.id}")
        return self._agent_id

    def create_thread(self) -> str:
        thread = self.client.agents.threads.create()
        logger.info(f"[{self.agent_name}] Created thread {thread.id}")
        return thread.id

    # ---------- Conversation ----------

    def run(self, thread_id: str, user_message: str, extra_context: str = "") -> str:
        """
        Sends a user message on the given thread, runs the agent, resolves
        any tool calls locally, and returns the final assistant text response.
        """
        agent_id = self.ensure_agent()

        message_content = user_message
        if extra_context:
            message_content = f"[Context: {extra_context}]\n\n{user_message}"

        self.client.agents.messages.create(
            thread_id=thread_id,
            role="user",
            content=message_content,
        )

        run = self.client.agents.runs.create(thread_id=thread_id, agent_id=agent_id)
        run = self._poll_run_with_tools(thread_id, run.id)

        if run.status == "completed":
            return self._get_latest_assistant_message(thread_id)
        else:
            logger.error(f"[{self.agent_name}] Run ended with status: {run.status}")
            return ("I'm sorry, I ran into an issue processing that request. "
                    "Please try rephrasing or contact support at 1800-123-4567.")

    def _poll_run_with_tools(self, thread_id: str, run_id: str, timeout_s: int = 60):
        start = time.time()
        while time.time() - start < timeout_s:
            run = self.client.agents.runs.get(thread_id=thread_id, run_id=run_id)

            if run.status == "requires_action":
                tool_outputs = self._handle_tool_calls(run)
                run = self.client.agents.runs.submit_tool_outputs(
                    thread_id=thread_id, run_id=run_id, tool_outputs=tool_outputs
                )
                continue

            if run.status in ("completed", "failed", "cancelled", "expired"):
                return run

            time.sleep(0.8)

        raise TimeoutError(f"Run {run_id} timed out after {timeout_s}s")

    def _handle_tool_calls(self, run) -> List[Dict]:
        tool_outputs = []
        required_action = run.required_action
        tool_calls = required_action.submit_tool_outputs.tool_calls

        for call in tool_calls:
            tool_name = call.function.name
            try:
                arguments = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            logger.info(f"[{self.agent_name}] Tool call: {tool_name}({arguments})")
            result = execute_tool(tool_name, arguments)

            tool_outputs.append({
                "tool_call_id": call.id,
                "output": result,
            })

        return tool_outputs

    def _get_latest_assistant_message(self, thread_id: str) -> str:
        messages = self.client.agents.messages.list(thread_id=thread_id, order="desc", limit=5)
        for msg in messages:
            if msg.role == "assistant":
                parts = []
                for content_item in msg.content:
                    if hasattr(content_item, "text"):
                        parts.append(content_item.text.value)
                return "\n".join(parts).strip()
        return "I don't have a response for that right now."

    def cleanup(self):
        """Optionally delete the agent definition (call on app shutdown if desired)."""
        if self._agent_id:
            try:
                self.client.agents.delete_agent(self._agent_id)
                logger.info(f"Deleted agent {self._agent_id}")
            except HttpResponseError as e:
                logger.warning(f"Could not delete agent {self._agent_id}: {e}")
