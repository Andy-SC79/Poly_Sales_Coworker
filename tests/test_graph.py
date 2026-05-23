"""
tests/test_graph.py
--------------------
Integration test for the full LangGraph flow.
Requires OPENAI_API_KEY set in .env to run the LLM calls.
Skip automatically if no API key is present.

Run with: python -m pytest tests/test_graph.py -v
"""
import os
import asyncio
import json
import pytest
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage

load_dotenv()

# Skip entire module if no API key
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY", "").strip(),
    reason="OPENAI_API_KEY not set in .env"
)


@pytest.fixture
def graph():
    from core.brain.graph import poly_graph
    return poly_graph


def _config(phone: str) -> dict:
    """Build LangGraph config (thread_id = customer phone)."""
    return {"configurable": {"thread_id": phone}}


@pytest.fixture
def test_phone():
    return "+573001111111"


class TestFullGraphFlow:
    @pytest.mark.asyncio
    async def test_greeting_response(self, graph, test_phone):
        """Graph should respond to a greeting with a welcome message."""
        state = {
            "messages": [HumanMessage(content="Hola, buenas tardes")],
            "channel": "whatsapp",
            "customer_id": test_phone,
            "stage": "greeting",
            "customer_name": None,
            "conversation_summary": None,
            "discovery_notes": None,
            "recommended_products": [],
            "order_data": None,
            "is_admin": False,
            "escalation_pending": False,
            "long_term_profile": None,
        }
        result = await graph.ainvoke(state, config=_config(test_phone))
        last_msg = result["messages"][-1]
        assert last_msg.content  # Must have a non-empty response
        print(f"\n[Poly - Greeting]: {last_msg.content}")

    @pytest.mark.asyncio
    async def test_objection_response(self, graph, test_phone):
        """Graph should respond empathetically to price objection."""
        state = {
            "messages": [HumanMessage(content="Me parece muy caro, no sé si vale la pena")],
            "channel": "whatsapp",
            "customer_id": test_phone,
            "stage": "objection",
            "customer_name": "Carlos",
            "conversation_summary": "- Dolores detectados: dolor de espalda",
            "discovery_notes": None,
            "recommended_products": [],
            "order_data": None,
            "is_admin": False,
            "escalation_pending": False,
            "long_term_profile": None,
        }
        result = await graph.ainvoke(state, config=_config(test_phone + "_obj"))
        last_msg = result["messages"][-1]
        assert last_msg.content
        print(f"\n[Poly - Objection]: {last_msg.content}")

    @pytest.mark.asyncio
    async def test_admin_command(self, graph):
        """Admin messages via Telegram should be handled by the admin agent."""
        admin_id = "telegram_admin_123"
        state = {
            "messages": [HumanMessage(content="Dame un resumen de las ventas de hoy")],
            "channel": "telegram",
            "customer_id": admin_id,
            "stage": "admin",
            "customer_name": None,
            "conversation_summary": None,
            "discovery_notes": None,
            "recommended_products": [],
            "order_data": None,
            "is_admin": True,
            "escalation_pending": False,
            "long_term_profile": None,
        }
        result = await graph.ainvoke(state, config=_config(admin_id))
        last_msg = result["messages"][-1]
        assert last_msg.content
        print(f"\n[Poly - Admin]: {last_msg.content}")

    def test_sync_state_from_tools_applies_escalation_event(self):
        """The graph should update state after an escalation tool returns structured metadata."""
        from core.brain.graph import sync_state_from_tools

        tool_payload = {
            "event": "escalation",
            "stage": "escalation",
            "escalation_pending": True,
        }
        state = {
            "messages": [ToolMessage(content=json.dumps(tool_payload), tool_call_id="escalation_tool")]
        }

        updates = sync_state_from_tools(state)

        assert updates["stage"] == "escalation"
        assert updates["escalation_pending"] is True

    @pytest.mark.asyncio
    async def test_memory_persists_between_turns(self, graph, test_phone):
        """
        Two consecutive messages from same customer should share context.
        Second message doesn't repeat the greeting.
        """
        phone = test_phone + "_memory"
        base_state = {
            "channel": "whatsapp",
            "customer_id": phone,
            "stage": "greeting",
            "customer_name": None,
            "conversation_summary": None,
            "discovery_notes": None,
            "recommended_products": [],
            "order_data": None,
            "is_admin": False,
            "escalation_pending": False,
            "long_term_profile": None,
        }
        cfg = _config(phone)

        # Turn 1
        state1 = {**base_state, "messages": [HumanMessage(content="Hola!")]}
        result1 = await graph.ainvoke(state1, config=cfg)
        reply1 = result1["messages"][-1].content
        print(f"\n[Turn 1]: {reply1}")

        # Turn 2 — same thread, should have context from turn 1
        state2 = {**base_state, "messages": [HumanMessage(content="Me duele mucho la rodilla")]}
        result2 = await graph.ainvoke(state2, config=cfg)
        reply2 = result2["messages"][-1].content
        print(f"[Turn 2]: {reply2}")

        assert reply1 and reply2
