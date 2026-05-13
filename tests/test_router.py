"""
tests/test_router.py
---------------------
Unit tests for the intent router — no API key needed.
Tests keyword matching and validates all stage literals.
Run with: python -m pytest tests/test_router.py -v
"""
import asyncio
import pytest
from langchain_core.messages import HumanMessage
from core.brain.state import PolyState
from core.brain.router import _keyword_route, route


def _make_state(text: str, is_admin: bool = False) -> PolyState:
    """Helper to build a minimal PolyState for testing."""
    return PolyState(
        messages=[HumanMessage(content=text)],
        channel="whatsapp",
        customer_id="+573001234567",
        stage="greeting",
        customer_name=None,
        pain_points=[],
        recommended_products=[],
        order_data=None,
        is_admin=is_admin,
        escalation_pending=False,
        long_term_profile=None,
    )


# ── Keyword Router Tests ──────────────────────────────────────────────────────

class TestKeywordRouter:
    def test_greeting_hola(self):
        assert _keyword_route("hola!") == "greeting"

    def test_greeting_buenos_dias(self):
        assert _keyword_route("Buenos días, ¿cómo están?") == "greeting"

    def test_closing_quiero_comprar(self):
        assert _keyword_route("quiero comprar el colágeno") == "closing"

    def test_closing_como_pago(self):
        assert _keyword_route("¿Cómo pago?") == "closing"

    def test_objection_muy_caro(self):
        assert _keyword_route("me parece muy caro") == "objection"

    def test_objection_no_se(self):
        assert _keyword_route("no sé si sirve de verdad") == "objection"

    def test_post_sale_pedido(self):
        assert _keyword_route("¿dónde está mi pedido?") == "post_sale"

    def test_complaint_queja(self):
        assert _keyword_route("tengo una queja con mi último pedido") == "complaint"

    def test_ambiguous_returns_none(self):
        """Unknown message should not be force-matched."""
        assert _keyword_route("me duele la espalda mucho") is None

    def test_ambiguous_question_returns_none(self):
        assert _keyword_route("¿tiene magnesio?") is None


# ── Admin Routing ─────────────────────────────────────────────────────────────

class TestAdminRouting:
    @pytest.mark.asyncio
    async def test_admin_channel_routes_to_admin(self):
        state = _make_state("dame un reporte de ventas", is_admin=True)
        result = await route(state)
        assert result == "admin"

    @pytest.mark.asyncio
    async def test_greeting_routes_correctly(self):
        state = _make_state("Hola, buenas tardes")
        result = await route(state)
        assert result == "greeting"

    @pytest.mark.asyncio
    async def test_closing_intent_routes_correctly(self):
        state = _make_state("quiero comprar, ¿cómo hago el pedido?")
        result = await route(state)
        assert result == "closing"
