from channels.telegram import _build_admin_invocation_state
from channels.whatsapp import _build_invocation_state


def test_whatsapp_first_turn_builds_full_state():
    state = _build_invocation_state(
        phone="+573001234567",
        body="hola",
        long_term_profile={"name": "Carlos", "conversation_summary": "Le interesa colageno"},
        checkpoint_values={},
    )

    assert state["stage"] == "greeting"
    assert state["current_order_id"] is None
    assert state["escalation_pending"] is False
    assert state["customer_name"] == "Carlos"


def test_whatsapp_existing_thread_builds_delta_without_resetting_persistent_fields():
    state = _build_invocation_state(
        phone="+573001234567",
        body="ok",
        long_term_profile={"name": "Carlos"},
        checkpoint_values={
            "stage": "closing",
            "current_order_id": "P-000042",
            "escalation_pending": True,
            "order_data": {"x": 1},
        },
    )

    assert state["messages"]
    assert state["customer_id"] == "+573001234567"
    assert "stage" not in state
    assert "current_order_id" not in state
    assert "escalation_pending" not in state
    assert "order_data" not in state


def test_telegram_existing_thread_builds_admin_delta_without_resetting_order_state():
    state = _build_admin_invocation_state(
        customer_id="admin_123",
        text="revisa ventas",
        long_term_profile={"role": "owner", "role_metadata": {"x": 1}},
        checkpoint_values={"current_order_id": "P-000042", "stage": "admin"},
    )

    assert state["is_admin"] is True
    assert state["role"] == "owner"
    assert "current_order_id" not in state
    assert "stage" not in state
