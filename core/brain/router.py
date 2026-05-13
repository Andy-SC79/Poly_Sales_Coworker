"""
core/brain/router.py
---------------------
Intent classifier / stage router for the LangGraph orchestrator.
Determines which agent node should handle the current message based on:
  1. Channel source (admin vs. customer)
  2. Explicit intent keywords
  3. LLM-based classification for ambiguous cases
"""
import re
import structlog
from langchain_core.messages import HumanMessage

from core.brain.state import PolyState, SalesStage
from core.brain.model_selector import get_model

log = structlog.get_logger()

# ── Keyword-based fast routing ────────────────────────────────────────────────
_INTENT_PATTERNS: list[tuple[SalesStage, list[str]]] = [
    ("greeting",  ["hola", "buenas", "buenos días", "buenas tardes", "hey", "hi"]),
    ("presentation", ["qué me recomiendas", "qué producto", "dime más sobre", "muéstrame",
                      "qué tienes para", "necesito algo para", "cuál es el mejor"]),
    ("closing",   ["quiero comprar", "lo quiero", "cómo pago", "dónde pago", "cuál es el precio final",
                   "cómo pido", "hacer pedido", "confirmar", "mi dirección"]),
    ("objection", ["muy caro", "no sé", "no estoy seguro", "dudas", "me da desconfianza",
                   "funciona de verdad", "es confiable", "qué garantía"]),
    ("post_sale", ["mi pedido", "dónde está mi pedido", "cuándo llega", "número de seguimiento",
                   "rastrear", "estado del pedido"]),
    ("complaint", ["queja", "reclamo", "no llegó", "llegó dañado", "me cobraron mal",
                   "mal servicio", "problema con"]),
    ("escalation", ["humano", "persona real", "asesor", "hablar con alguien", "quiero hablar con un humano",
                    "soporte técnico", "asistencia humana"]),
]


def _keyword_route(text: str) -> SalesStage | None:
    """Fast keyword-matching. Returns a stage or None if ambiguous."""
    lower = text.lower()
    for stage, keywords in _INTENT_PATTERNS:
        if any(kw in lower for kw in keywords):
            return stage
    return None


async def _llm_classify(state: PolyState) -> SalesStage:
    """
    Use a lightweight LLM call to classify intent when keywords don't match.
    Returns one of the SalesStage literals.
    """
    last_msg = state["messages"][-1]
    text = last_msg.content if isinstance(last_msg, HumanMessage) else ""

    model = get_model("default")  # Use dynamic selection (local Ollama or Cloud)
    classifier_prompt = f"""
Clasifica la intención de este mensaje de WhatsApp en UNA de estas categorías:
greeting | discovery | presentation | objection | closing | post_sale | complaint | escalation

Mensaje: "{text}"

Responde SOLO con la categoría, sin explicación.
"""
    response = await model.ainvoke(classifier_prompt)
    stage_raw = response.content.strip().lower()

    valid: list[SalesStage] = [
        "greeting", "discovery", "presentation", "objection",
        "closing", "post_sale", "complaint", "escalation"
    ]
    return stage_raw if stage_raw in valid else "discovery"  # type: ignore[return-value]


async def route(state: PolyState) -> SalesStage:
    """
    Main routing function called by LangGraph's conditional edge.
    Returns the name of the next node to execute.
    """
    # Admin channel always goes to admin agent
    if state.get("is_admin"):
        log.info("router.admin_channel")
        return "admin"

    last_msg = state["messages"][-1]
    text = last_msg.content if hasattr(last_msg, "content") else ""

    # 1. Fast keyword match
    stage = _keyword_route(text)
    if stage:
        log.info("router.keyword_match", stage=stage)
        return stage

    # 2. Check if already escalated
    if state.get("escalation_pending"):
        log.info("router.escalation_active")
        return "escalation"

    # 3. LLM-based classification for ambiguous messages
    stage = await _llm_classify(state)
    log.info("router.llm_classified", stage=stage)
    return stage
