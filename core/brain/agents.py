"""
core/brain/agents.py
---------------------
Specialized agent node functions for the LangGraph graph.
Each function receives the current PolyState, calls the LLM with the
appropriate stage prompt, and returns a state delta.
"""
from datetime import datetime, timezone
import structlog
from langchain_core.messages import AIMessage, SystemMessage

from core.brain.state import PolyState, SalesStage
from core.brain.prompts import get_prompt
from core.brain.model_selector import get_model
from core.brain.awareness import get_context_awareness
from core.knowledge.catalog import search_products
from infrastructure.notifications import send_telegram_alert

log = structlog.get_logger()


# ── Helper ────────────────────────────────────────────────────────────────────

async def _invoke_agent(state: PolyState, stage: SalesStage) -> dict:
    """Core logic: build prompt for the stage, call LLM, return state update."""
    
    # 1. RAG: Build an enriched query
    messages = state["messages"][-3:]  # Take last 3 messages for context
    query_parts = [m.content for m in messages if hasattr(m, "content")]
    if state.get("pain_points"):
        query_parts.append(" ".join(state["pain_points"]))
    
    enriched_query = " ".join(query_parts)
    search_results = await search_products(enriched_query, k=2)
    products_context = "\n---\n".join([doc.page_content for doc in search_results])
    
    log.info("agent.invoking", stage=stage, customer=state.get("customer_id"))

    # 2. Awareness Context (Spatiotemporal)
    # We use state.get("last_interaction_at") which should be updated by the caller or a previous turn
    awareness_block = get_context_awareness(
        customer_id=state.get("customer_id", "unknown"),
        last_interaction_at=state.get("last_interaction_at")
    )

    # 3. RBAC & Permissions
    # By default, only Admin has web_search, BUT we can allow it for customers 
    # if they are in 'objection' or 'presentation' stage as per "Constitución".
    permissions = []
    if state.get("is_admin") or stage in ["objection", "presentation"]:
        permissions.append("web_search")

    # 4. Build the message context
    rag_instruction = (
        "REGLA DE ORO: Solo puedes recomendar los productos que aparezcan en el 'CATÁLOGO REAL' abajo. "
        "Si el cliente pregunta por algo que no está ahí, di amablemente que no lo manejas por ahora. "
        "NUNCA inventes nombres de productos ni beneficios.\n\n"
        f"CATÁLOGO REAL:\n{products_context if products_context else 'No hay productos relevantes en el catálogo.'}"
    )
    
    prompt = get_prompt(
        stage=stage,
        profile_notes=state.get("long_term_profile", {}).get("profile_notes", "Sin notas previas."),
        awareness_context=awareness_block,
        role=state.get("role", "customer")
    )
    
    # Inyectamos los permisos al selector de modelos
    model = get_model("default", permissions=permissions)
    
    # Pre-pend the RAG instruction to the message list
    messages_to_send = [SystemMessage(content=rag_instruction)] + state["messages"]

    # 5. Invoke LLM
    try:
        chain = prompt | model
        response = await chain.ainvoke({"messages": messages_to_send})
    except Exception as e:
        log.error("agent.llm_error", error=str(e))
        raise

    # 6. Post-processing (only if NOT a tool call)
    if hasattr(response, "tool_calls") and response.tool_calls:
        # If it's a tool call, we return the message and let the graph handle it.
        # We don't clean content yet.
        return {
            "messages": [response],
            "stage": stage,
            "last_interaction_at": datetime.now(timezone.utc)
        }

    # Extract hidden [PAIN: category], [NAME: name], and [NOTE: info] tags
    import re
    text = response.content
    pain_tags = re.findall(r"\[PAIN:\s*(.*?)\]", text, re.IGNORECASE)
    name_tags = re.findall(r"\[NAME:\s*(.*?)\]", text, re.IGNORECASE)
    note_tags = re.findall(r"\[NOTE:\s*(.*?)\]", text, re.IGNORECASE)
    
    # Clean response text
    clean_content = re.sub(r"\[(PAIN|NAME|NOTE):\s*.*?\]", "", text, flags=re.IGNORECASE).strip()
    response.content = clean_content

    update = {
        "messages": [response],
        "stage": stage,
        "recommended_products": [doc.metadata for doc in search_results],
        "pain_points": list(set((state.get("pain_points") or []) + pain_tags)),
        "customer_name": name_tags[0] if name_tags else state.get("customer_name"),
        "last_interaction_at": datetime.now(timezone.utc)
    }
    
    if note_tags:
        update["admin_notes"] = note_tags[0]
        
    return update


# ── Agent Nodes ───────────────────────────────────────────────────────────────

async def greeting_agent(state: PolyState) -> dict:
    """Handle first contact and re-engagement."""
    return await _invoke_agent(state, "greeting")


async def discovery_agent(state: PolyState) -> dict:
    """Ask questions to uncover the customer's needs and pain points."""
    return await _invoke_agent(state, "discovery")


async def presentation_agent(state: PolyState) -> dict:
    """Present product benefits tailored to discovered needs (uses RAG results)."""
    return await _invoke_agent(state, "presentation")


async def objection_agent(state: PolyState) -> dict:
    """Handle doubts about price, effectiveness, trust, etc."""
    return await _invoke_agent(state, "objection")


async def closing_agent(state: PolyState) -> dict:
    """Collect order information step by step and build the order JSON."""
    return await _invoke_agent(state, "closing")


async def post_sale_agent(state: PolyState) -> dict:
    """Handle post-purchase follow-up and order tracking queries."""
    return await _invoke_agent(state, "post_sale")


async def complaint_agent(state: PolyState) -> dict:
    """Handle complaints and escalations with empathy and resolution."""
    return await _invoke_agent(state, "complaint")


async def admin_agent(state: PolyState) -> dict:
    """
    Process admin commands received via Telegram.
    The owner can request reports, send messages, change Poly's config, etc.
    """
    return await _invoke_agent(state, "admin")


async def escalation_agent(state: PolyState) -> dict:
    """
    Handle requests for human assistance.
    Notifies the admin and responds to the customer via LLM.
    """
    customer_id = state.get("customer_id", "Desconocido")
    last_msg = state["messages"][-1].content if state["messages"] else "Sin mensaje"
    
    # 1. Notify Admin (if not already notified in this turn)
    if not state.get("escalation_pending"):
        alert_msg = (
            f"🚨 *ALERTA DE ESCALACIÓN*\n\n"
            f"👤 *Cliente:* {customer_id}\n"
            f"💬 *Último mensaje:* {last_msg}\n\n"
            f"Poly se ha pausado. Por favor atiende al cliente en WhatsApp."
        )
        await send_telegram_alert(alert_msg)
        log.info("agent.escalation_notified", customer=customer_id)

    # 2. Invoke LLM for the actual response to the customer
    update = await _invoke_agent(state, "escalation")
    update["escalation_pending"] = True
    return update
