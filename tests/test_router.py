import pytest
from langchain_core.messages import HumanMessage

from core.brain.router import RouteDecision, route


def _make_state(text: str, stage: str = "greeting", is_admin: bool = False) -> dict:
    return {
        "messages": [HumanMessage(content=text)],
        "channel": "whatsapp",
        "customer_id": "+573001234567",
        "stage": stage,
        "is_admin": is_admin,
        "escalation_pending": False,
        "is_paused": False,
    }


class TestRouting:
    @pytest.mark.asyncio
    async def test_admin_routes_to_admin_without_llm(self):
        state = _make_state("dame un reporte de ventas", is_admin=True)
        assert await route(state) == "admin"

    @pytest.mark.asyncio
    async def test_escalation_pending_routes_to_escalation(self):
        state = _make_state("hola")
        state["escalation_pending"] = True
        assert await route(state) == "escalation"

    @pytest.mark.asyncio
    async def test_low_confidence_closing_stickiness_does_not_raise_name_error(self, monkeypatch):
        async def fake_classify(state):
            return RouteDecision(
                stage="discovery",
                reasoning="ambiguous short reply",
                confidence=0.2,
            )

        monkeypatch.setattr("core.brain.router._llm_classify", fake_classify)
        state = _make_state("ok", stage="closing")

        assert await route(state) == "closing"
