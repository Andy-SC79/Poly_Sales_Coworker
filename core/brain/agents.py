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
from pydantic import BaseModel, Field
from typing import List, Optional

log = structlog.get_logger()

class ProfileUpdate(BaseModel):
    """Schema for extracting and validating customer information."""
    name: Optional[str] = Field(None, description="The customer's full name (First + Last).")
    is_valid_name: bool = Field(True, description="False if the name looks like a joke, nickname, or fake (e.g. Micky Mouse).")
    rejection_reason: Optional[str] = Field(None, description="Why the name was rejected (e.g. 'Parece un apodo', 'Falta el apellido').")
    city: Optional[str] = Field(None, description="The city or location.")
    conversation_summary_addition: Optional[str] = Field(None, description="Hechos concisos e impersonales sobre el cliente en este turno. NO uses 'El cliente dijo' ni 'El cliente es'. Escribe directo: 'Le interesan los animales', 'Tiene dos hijos', 'Prefiere pagar en efectivo', 'Sufre de migraña'. Si no hay información relevante nueva, déjalo vacío.")
    email: Optional[str] = Field(None, description="El correo electrónico del cliente, si lo proporcionó.")
    address: Optional[str] = Field(None, description="La dirección exacta de envío, si la proporcionó.")
    alternative_phone: Optional[str] = Field(None, description="Un número de teléfono alternativo, si lo proporcionó.")

async def profile_extractor(state: PolyState) -> dict:
    """
    Analyzes the conversation to extract and VALIDATE customer data.
    """
    model = get_model()
    history = state['messages'][-2:]
    
    prompt = f"""
    Eres un auditor de datos CRM de alta seguridad. Tu misión es detectar si el cliente está dando información REAL o si está "tomando el pelo" (bromeando/mintiendo).
    
    Analiza el último mensaje del cliente: {history}
    
    REGLAS ESTRICTAS DE VALIDACIÓN:
    1. NOMBRE: Debe ser un nombre y apellido humano real. 
    2. DETECTA BROMAS: Rechaza personajes de ficción (Pitufo, Mickey, Goku), objetos (Cable Pelao, Mesa), o insultos.
    3. DETECTA INCOMPLETOS: Si solo da el nombre (ej: "Juan"), márcalo como is_valid_name=True pero pon en la nota que falta el apellido.
    4. SI ES UNA BROMA: Pon is_valid_name=False y en rejection_reason explica qué tipo de broma es.
    """
    
    try:
        structured_llm = model.with_structured_output(ProfileUpdate)
        extraction = await structured_llm.ainvoke(prompt)
        
        updates = {}
        # Lógica de seguridad: No sobrescribir un nombre real con una broma
        if extraction.name:
            if extraction.is_valid_name:
                if len(extraction.name.split()) >= 2:
                    updates["customer_name"] = extraction.name
                    updates["discovery_notes"] = "" # Limpiamos notas si el nombre es perfecto
                else:
                    updates["discovery_notes"] = "El nombre está incompleto (falta el apellido)."
            else:
                updates["discovery_notes"] = f"ALERTA: El cliente está bromeando con el nombre '{extraction.name}'. Motivo: {extraction.rejection_reason}"
                log.info("agent.fake_name_detected", name=extraction.name, reason=extraction.rejection_reason)
            
        if extraction.city: updates["city"] = extraction.city
        
        if extraction.conversation_summary_addition:
            # 1. Update raw string summary (for the nightly sleep compaction later)
            existing = state.get("conversation_summary") or ""
            new_summary = f"{existing}\n- {extraction.conversation_summary_addition}".strip()
            updates["conversation_summary"] = new_summary
            
            # 2. Add directly to Supabase vector memory for immediate RAG retrieval!
            from core.knowledge.catalog import index_episodic_memory
            import asyncio
            # Fire and forget indexing to avoid blocking the main chat flow
            asyncio.create_task(index_episodic_memory(state.get("customer_id", ""), extraction.conversation_summary_addition))
            
        if extraction.email: updates["email"] = extraction.email
        if extraction.address: updates["address"] = extraction.address
        if extraction.alternative_phone: updates["alternative_phone"] = extraction.alternative_phone
            
        return updates
    except Exception as e:
        log.warning("agent.extraction_failed", error=str(e))
        return {}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _invoke_agent(state: PolyState, stage: SalesStage) -> dict:
    """Core logic: build prompt for the stage, call LLM, return state update."""
    
    # 1. RAG: Build an enriched query for Product Catalog
    messages = state["messages"][-3:]  # Take last 3 messages for context
    query_parts = [m.content for m in messages if hasattr(m, "content")]
    enriched_query = " ".join(query_parts)
    
    search_results = await search_products(enriched_query, k=2)
    products_context = "\n---\n".join([doc.page_content for doc in search_results])
    
    # 1.5 RAG: Build Episodic Memory Context for the Customer
    from core.knowledge.catalog import search_episodic_memories
    customer_id = state.get("customer_id", "")
    memories_results = await search_episodic_memories(customer_id, enriched_query, k=3)
    memories_context = "\n".join([f"- {doc.page_content}" for doc in memories_results]) if memories_results else "No hay recuerdos específicos recientes sobre este tema."
    
    log.info("agent.invoking", stage=stage, customer=state.get("customer_id"))

    # 2. Awareness Context (Spatiotemporal)
    # We use state.get("last_interaction_at") which should be updated by the caller or a previous turn
    awareness_block = get_context_awareness(
        customer_id=state.get("customer_id", "unknown"),
        last_interaction_at=state.get("last_interaction_at")
    )

    # 3. RBAC & Permissions (ADITIVO Y ROBUSTO)
    is_admin = bool(state.get("is_admin"))

    # 4. Build the message context
    rag_instruction = (
        "### REGLAS DE ORO DE OPERACIÓN:\n"
        "1. PRECISIÓN: Solo recomienda productos del catálogo. Si dudas de un precio, usa 'verify_fact'.\n"
        "2. PERSISTENCIA: Si una herramienta falla, explica al cliente que estás verificando y vuelve a intentarlo.\n"
        "3. EMPATÍA: Escucha el dolor del cliente antes de ofrecer la solución.\n\n"
        f"CONTEXTO DEL CATÁLOGO:\n{products_context if products_context else 'No hay información adicional.'}"
    )
    
    disc_notes = state.get("discovery_notes") or ""
    cust_name = state.get("customer_name") or ""
    
    profile_notes = (state.get("long_term_profile") or {}).get("profile_notes", "")
    
    full_crm_notes = f"""
Nombre: {cust_name if cust_name else 'Aún no proporcionado'}
Perfil Base: {profile_notes if profile_notes else 'Sin perfil condensado.'}
Recuerdos asociados a lo que el cliente acaba de decir:
{memories_context}
Notas temporales de esta sesión: {disc_notes}
"""

    prompt = get_prompt(
        stage=stage,
        profile_notes=(state.get("long_term_profile") or {}).get("profile_notes", "Sin notas previas."),
        awareness_context=awareness_block,
        crm_notes=full_crm_notes,
        role=state.get("role", "customer"),
        whatsapp_origin=state.get("customer_id", "desconocido"),
        current_order_id=state.get("current_order_id")
    )
    
    model_provider = state.get("model_provider", "default")
    model = get_model(model_provider, is_admin=is_admin)
    
    # 4.5 Sanitize messages to prevent OpenAI 400 errors (Dangling tool calls from DB crashes)
    cleaned_messages = []
    messages_list = state["messages"]
    
    # 1. Recolectar todos los IDs de herramientas que SÍ tienen respuesta
    valid_tool_ids = set()
    for msg in messages_list:
        # Extraer de objetos LangChain
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            valid_tool_ids.add(msg.tool_call_id)
        # Extraer de diccionarios
        elif isinstance(msg, dict) and msg.get("tool_call_id"):
            valid_tool_ids.add(msg.get("tool_call_id"))
            
    # 2. Reconstruir la lista filtrando tool_calls huérfanos
    from langchain_core.messages import AIMessage
    for msg in messages_list:
        t_calls = []
        is_ai_with_tools = False
        
        # Caso 1: Objeto Langchain
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            t_calls.extend(msg.tool_calls)
            is_ai_with_tools = True
        if hasattr(msg, "invalid_tool_calls") and msg.invalid_tool_calls:
            t_calls.extend(msg.invalid_tool_calls)
            is_ai_with_tools = True
        elif hasattr(msg, "additional_kwargs"):
            if msg.additional_kwargs.get("tool_calls"):
                t_calls.extend(msg.additional_kwargs.get("tool_calls"))
                is_ai_with_tools = True
            if msg.additional_kwargs.get("invalid_tool_calls"):
                t_calls.extend(msg.additional_kwargs.get("invalid_tool_calls"))
                is_ai_with_tools = True
        # Caso 2: Diccionario
        elif isinstance(msg, dict):
            if msg.get("tool_calls"):
                t_calls.extend(msg.get("tool_calls"))
                is_ai_with_tools = True
            if msg.get("invalid_tool_calls"):
                t_calls.extend(msg.get("invalid_tool_calls"))
                is_ai_with_tools = True
            
        if is_ai_with_tools:
            missing_any = False
            for tc in t_calls:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id and tc_id not in valid_tool_ids:
                    missing_any = True
                    break
                    
            if missing_any:
                log.warning("agent.sanitized_dangling_tool_call_v3", original_msg=str(msg)[:100])
                # Crear un mensaje limpio, perdiendo la propiedad tool_calls a propósito
                clean_content = msg.content if hasattr(msg, "content") else msg.get("content", "...")
                cleaned_messages.append(AIMessage(content=clean_content or "Tool call cancelado por el sistema."))
                continue
                
        cleaned_messages.append(msg)

    messages_to_send = [SystemMessage(content=rag_instruction)] + cleaned_messages

    # DEBUG DUMP
    try:
        with open("debug_prompt.txt", "w", encoding="utf-8") as f:
            for m in messages_to_send:
                f.write(f"ROLE: {m.type if hasattr(m, 'type') else m.get('type', 'unknown')}\n")
                f.write(f"CONTENT: {m.content if hasattr(m, 'content') else m.get('content', '')}\n")
                if hasattr(m, 'tool_calls') and m.tool_calls:
                    f.write(f"TOOL_CALLS: {m.tool_calls}\n")
                f.write("-" * 50 + "\n")
    except Exception as e:
        log.error("debug_dump_failed", error=str(e))

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
    
    # Fuerza Bruta: Eliminar los dobles asteriscos de Markdown que rompen WhatsApp
    clean_content = clean_content.replace("**", "*")
    
    response.content = clean_content

    update = {
        "messages": [response],
        "stage": stage,
        "recommended_products": [doc.metadata for doc in search_results],
        "conversation_summary": state.get("conversation_summary"),
        "customer_name": name_tags[0] if name_tags else state.get("customer_name"),
        "last_interaction_at": datetime.now(timezone.utc)
    }
    
    if pain_tags:
        existing = update["conversation_summary"] or ""
        update["conversation_summary"] = f"{existing}\n- Dolores detectados: {', '.join(pain_tags)}".strip()
    
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
    If already escalated, stays silent. If new, notifies admin and informs customer.
    """
    customer_id = state.get("customer_id", "Desconocido")
    
    # Si ya estábamos en escalación, SILENCIO TOTAL
    if state.get("escalation_pending"):
        log.info("agent.escalation_silent_mode", customer=customer_id)
        return {
            "messages": [AIMessage(content="[SILENCIO]")],
            "stage": "escalation"
        }

    # 1. Notify Admin (Primera vez)
    last_msg = state["messages"][-1].content if state["messages"] else "Sin mensaje"
    alert_msg = (
        f"🚨 *NUEVA ESCALACIÓN*\n\n"
        f"👤 *Cliente:* {customer_id}\n"
        f"💬 *Último mensaje:* {last_msg}\n\n"
        f"Poly se ha silenciado. Atiende al cliente desde Telegram o WhatsApp."
    )
    await send_telegram_alert(alert_msg, customer_id=state.get("customer_id"))
    log.info("agent.escalation_notified", customer=customer_id)

    # 2. Inform customer once
    reply = "He avisado a mi equipo humano. Por favor, regálame un momento mientras un compañero revisa tu situación. 🙏"
    return {
        "messages": [AIMessage(content=reply)],
        "stage": "escalation",
        "escalation_pending": True
    }


async def silence_agent(state: PolyState) -> dict:
    """
    Shadowing mode: Poly observes but does not reply.
    """
    from langchain_core.messages import AIMessage
    # Devolvemos un mensaje vacío o un indicador de silencio
    return {
        "messages": [AIMessage(content="[Silencio: Poly está observando]")],
        "is_paused": True
    }
