"""
agent_sales/router.py
Copied sales-specific router from core.brain.router to live in agent_sales.
"""
import structlog
from pydantic import BaseModel, Field
from typing import Literal

from core.brain.state import PolyState, SalesStage
from core.brain.model_selector import get_model

log = structlog.get_logger()

class RouteDecision(BaseModel):
    """Esquema de decisión para el enrutador de Poly."""
    stage: SalesStage = Field(description="La etapa de venta a la que debemos mover la conversación.")
    reasoning: str = Field(description="Explicación breve de por qué se eligió esta etapa.")
    confidence: float = Field(description="Nivel de confianza de la decisión (0.0 a 1.0).")

async def route(state: PolyState) -> SalesStage:
    """
    Función de enrutamiento principal. 
    Analiza el historial completo para determinar el siguiente paso lógico.
    """
    current_stage = state.get("stage", "greeting")

    # 1. Admin & Escalation checks
    if state.get("is_admin"):
        return "admin"

    if state.get("escalation_pending"):
        return "escalation"

    # 2. Shadowing / Coworker logic
    last_msg = state["messages"][-1]
    text = (last_msg.content if hasattr(last_msg, "content") else "").lower()
    
    # Triggers para retomar o pausar (pueden ser más complejos)
    resume_triggers = ["te dejo con poly", "poly retoma", "poly responde", "poly toma el pedido"]
    pause_triggers = ["yo me encargo", "poly silencio", "espera un momento"]

    if any(t in text for t in resume_triggers):
        return "greeting"
    
    if any(t in text for t in pause_triggers) or state.get("is_paused"):
        if not any(t in text for t in resume_triggers):
            return "silence"

    # 3. LLM-based structured classification (Primary reasoning)
    decision = await _llm_classify(state)
    
    # 3. Stickiness & Logic override
    if decision.confidence < 0.6 and current_stage == "closing" and len(text) < 150:
        log.info("router.sticky_closing_override", confidence=decision.confidence)
        return "closing"

    log.info("router.decision", stage=decision.stage, confidence=decision.confidence, reasoning=decision.reasoning)
    return decision.stage

async def _llm_classify(state: PolyState) -> RouteDecision:
    """Uses the LLM to classify the conversation stage with reasoning."""
    history = [m for m in state["messages"][-6:] if not hasattr(m, "tool_call_id")]
    messages_str = "\n".join([f"{m.type}: {m.content}" for m in history])
    
    current_stage = state.get("stage", "greeting")
    
    system_prompt = f"""
Eres el Supervisor de Flujo de Poly AI, una experta en ventas consultivas. 
Tu misión es analizar la conversación y decidir en qué etapa de venta estamos.

ETAPAS DISPONIBLES:
- greeting: Saludos iniciales o re-enganche.
- discovery: El cliente está contando sus necesidades o nosotros estamos preguntando.
- presentation: Estamos explicando beneficios o precios de un producto específico.
- objection: El cliente tiene dudas, quejas sobre precio o comparaciones.
- closing: El cliente mostró intención de compra clara o estamos recolectando sus datos de envío.
- post_sale: Seguimiento de pedidos hechos o dudas tras la compra.
- complaint: El cliente está enojado o tiene un problema serio de servicio.
- escalation: El cliente pide hablar con un humano explícitamente.

CONTEXTO:
- Etapa Actual: {current_stage}
- Historial Reciente:
{messages_str}
CONSEJOS DE ENRUTAMIENTO (GRAVEDAD COMERCIAL Y FLUIDEZ):
1. **Flexibilidad de Contexto:** Si el cliente estaba en 'post_sale' pero repentinamente muestra interés en un nuevo producto, cámbialo a 'presentation' o 'closing' de inmediato.
2. **Gravedad Comercial:** Si la intención del cliente es ambigua, hace preguntas genéricas o salta entre temas, la prioridad siempre es empujarlo hacia el embudo de ventas ('discovery' -> 'presentation' -> 'closing'). El soporte es secundario frente a la venta.
3. Si el cliente está proporcionando datos personales (nombre, dirección, etc.), la etapa DEBE ser 'closing'.
4. Si el cliente quiere 'intentar de nuevo' tras un fallo técnico de venta, la etapa DEBE ser 'closing'.
5. Si el cliente tiene dudas, problemas o quejas explícitas SOBRE UN PEDIDO (ej. revisar un error, quejas por demora, buscar otro número de pedido), la etapa DEBE ser 'post_sale'.
"""

    model = get_model("default") 
    structured_model = model.with_structured_output(RouteDecision)
    
    try:
        decision = await structured_model.ainvoke([
            ("system", system_prompt),
            ("human", "Analiza el contexto y decide el siguiente stage lógico.")
        ])
        return decision
    except Exception as e:
        log.error("router.llm_error", error=str(e))
        return RouteDecision(stage=current_stage, reasoning="Fallback por error", confidence=1.0)
