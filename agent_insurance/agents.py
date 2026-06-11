"""
agent_insurance/agents.py
LLM prompts, structured outputs, and agent nodes for the Sura Health Prequalification Agent.
"""
from typing import Dict, Any, Optional
import structlog
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from core.brain.model_selector import get_model
from agent_insurance.flow import InsuranceState, evaluate_qualification

log = structlog.get_logger()

# ── Structured output schema for extraction and reply generation ─────────────
class InsuranceExtraction(BaseModel):
    caller_name: Optional[str] = Field(None, description="Nombre de la persona que inicia la conversación.")
    is_for_self: Optional[bool] = Field(None, description="True si el seguro es para quien habla. False si es para otra persona (ej. padre, hijo, familiar).")
    candidate_relation: Optional[str] = Field(None, description="Parentesco del candidato si es para otra persona (ej. padre, madre, hijo).")
    candidate_name: Optional[str] = Field(None, description="Nombre de la persona que recibirá el seguro de salud (el candidato).")
    candidate_age: Optional[int] = Field(None, description="Edad del candidato (número entero).")
    candidate_has_eps: Optional[bool] = Field(None, description="True si el candidato tiene EPS en el régimen contributivo, False si tiene Sisben (subsidiado) o no tiene EPS.")
    candidate_eps: Optional[str] = Field(None, description="Nombre de la EPS a la que está afiliado el candidato.")
    email: Optional[str] = Field(None, description="Correo electrónico del cliente.")
    phone: Optional[str] = Field(None, description="Número de teléfono de contacto.")
    
    wants_other_product: Optional[bool] = Field(False, description="True si expresa interés explícito en seguros de otro tipo (auto, hogar, vida, etc.) en vez de salud.")
    other_product_interest: Optional[str] = Field(None, description="Descripción del otro seguro en el que está interesado.")
    
    agent_reply: str = Field(..., description="La respuesta en español del agente hacia el usuario, siguiendo el tono cálido y las instrucciones de la etapa actual.")

# ── Prompts per stage ────────────────────────────────────────────────────────
STAGE_INSTRUCTIONS = {
    "greeting": """
Eres Mateo, asesor digital de Sura. Tu objetivo es dar la bienvenida al cliente e identificar para quién es el seguro de salud.
Pide al cliente que te aclare si el plan de salud que busca es para él/ella mismo/a o para algún familiar (beneficiario).
Mantén una actitud atenta, empática y profesional. Escribe de forma natural y conversacional.
""",
    "prequalification": """
Tu objetivo es precalificar al candidato para el seguro de salud de Sura recopilando la información que falta.
Información recopilada hasta ahora:
- ¿Es para sí mismo?: {is_for_self}
- Nombre del candidato: {candidate_name}
- Edad del candidato: {candidate_age}
- ¿Tiene EPS contributiva?: {candidate_has_eps}
- Nombre de la EPS: {candidate_eps}

REGLAS DE PREGUNTAS:
1. Haz una pregunta a la vez para no abrumar al cliente.
2. Si no sabes el nombre o relación del candidato (si es para un tercero), pregúntalo primero.
3. Si falta la edad del candidato, pregúntala.
4. Si falta saber si está en el régimen contributivo de salud (EPS activa, excluyendo Sisben), pregúntale.
5. Si no sabes a qué EPS contributiva pertenece, pregúntalo.
Sé empático y conversacional. No parezcas un robot haciendo un cuestionario rígido.
""",
    "product_matching": """
El cliente ha precalificado con éxito para uno de nuestros planes de salud.
Detalles:
- Producto asignado: {matched_product}
- Motivo: {qualification_reason}

Instrucciones:
1. Explica al cliente de manera clara, entusiasta y amigable que ha calificado para el {matched_product}.
2. Presenta brevemente los beneficios del plan.
3. Pregúntale si está listo para agendar una cita virtual para formalizar los detalles y cotización final.
""",
    "contact_info": """
Tu objetivo es recolectar los datos de contacto del cliente para el registro y posterior seguimiento de la cita.
Información recopilada hasta ahora:
- Correo: {email}
- Teléfono: {phone}

Pregunta amablemente por los datos faltantes. Una vez que tengas ambos (email y teléfono), confirma que procederás a enviarle el link para agendar.
""",
    "scheduling": """
El cliente está listo para agendar.
Instrucciones:
1. Comparte el link de agendamiento de Calendly: https://calendly.com/sura-agent-mock/prequalification
2. Explícale que tanto él como su asesor de seguros asignado recibirán una notificación de confirmación una vez agendado.
3. Infórmale amigablemente que si no completa el agendamiento en las próximas horas, le escribiremos de nuevo dentro de las 24 horas para asistirle si tuvo algún inconveniente.
""",
    "other_products": """
El cliente está interesado en un producto diferente a salud (ej: {other_product_interest}).
Instrucciones:
1. Confírmale que Sura ofrece una gran variedad de soluciones para {other_product_interest} (como Auto, Hogar, Vida).
2. Pídele su nombre y número de teléfono (si no los ha dado) para que un asesor experto de ese ramo específico se ponga en contacto directo hoy mismo.
3. Despídete cordialmente.
""",
    "unqualified": """
El cliente o su candidato no califican para los planes de salud individuales de Sura.
Motivo del rechazo: {qualification_reason}

Instrucciones:
1. Explica de manera muy amable y respetuosa que debido al perfil ingresado (edad >= 70 o no pertenecer al régimen contributivo de EPS), en este momento no contamos con un plan de salud que se ajuste a sus necesidades.
2. Ofrece la opción de remitirlo a un asesor para otros tipos de seguros (auto, vida, hogar) si lo desea, o de lo contrario, dale una cordial despedida.
"""
}

# ── Main Agent Function ─────────────────────────────────────────────────────
async def run_insurance_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Core execution turn for the Insurance prequalification agent.
    Takes current state, invokes the model with structured output, 
    and applies flow evaluation logic.
    """
    # Initialize keys if missing
    current_stage = state.get("stage") or "greeting"
    messages = state.get("messages", [])
    
    # Pre-qualification state wrapper
    flow_state = InsuranceState(
        stage=current_stage,
        is_for_self=state.get("is_for_self"),
        caller_name=state.get("caller_name"),
        candidate_relation=state.get("candidate_relation"),
        candidate_name=state.get("candidate_name"),
        candidate_age=state.get("candidate_age"),
        candidate_has_eps=state.get("candidate_has_eps"),
        candidate_eps=state.get("candidate_eps"),
        is_qualified=state.get("is_qualified"),
        qualification_reason=state.get("qualification_reason"),
        matched_product=state.get("matched_product"),
        email=state.get("email"),
        phone=state.get("phone"),
        appointment_status=state.get("appointment_status", "none"),
        appointment_date=state.get("appointment_date")
    )
    
    # 1. Format the stage prompt instruction
    formatted_instruction = STAGE_INSTRUCTIONS.get(current_stage, STAGE_INSTRUCTIONS["greeting"]).format(
        is_for_self=flow_state.get("is_for_self", "Pendiente"),
        candidate_name=flow_state.get("candidate_name", "Pendiente"),
        candidate_age=flow_state.get("candidate_age", "Pendiente"),
        candidate_has_eps=flow_state.get("candidate_has_eps", "Pendiente"),
        candidate_eps=flow_state.get("candidate_eps", "Pendiente"),
        matched_product=flow_state.get("matched_product", "Pendiente"),
        qualification_reason=flow_state.get("qualification_reason", "N/A"),
        email=flow_state.get("email", "Pendiente"),
        phone=flow_state.get("phone", "Pendiente"),
        other_product_interest=state.get("other_product_interest", "otros ramos")
    )
    
    system_msg = SystemMessage(content=f"""
Eres un asistente de seguros inteligente y amable. Tu labor es guiar al usuario a través del flujo.
INSTRUCCIONES DE ETAPA ACTUAL:
{formatted_instruction}

INSTRUCCIONES CLAVE DE EXTRACCIÓN:
- Extrae toda la información relevante de la conversación y guárdala en los campos correspondientes.
- Si el usuario dice que el seguro es para sí mismo, pon is_for_self=True y asigna su nombre a caller_name y candidate_name.
- Si es para alguien más, pon is_for_self=False, extrae la relación (ej: padre, madre) y el nombre/edad/EPS del candidato si se mencionan.
- Si el usuario cambia de opinión sobre quién recibirá el seguro (por ejemplo, decide cotizar para un familiar en vez de sí mismo, o viceversa), asegúrate de actualizar is_for_self al nuevo valor y extraer la información correspondiente del nuevo candidato.
- Si menciona otros seguros (como auto, casa, vida, SOAT), pon wants_other_product=True y descríbelo.
""")

    # Send conversation messages history (up to last 10 messages for speed)
    history = []
    for m in messages[-10:]:
        if isinstance(m, (AIMessage, HumanMessage, SystemMessage)):
            history.append(m)
        elif isinstance(m, dict):
            m_type = m.get("type", "human")
            content = m.get("content", "")
            if m_type == "human":
                history.append(HumanMessage(content=content))
            elif m_type == "ai":
                history.append(AIMessage(content=content))
                
    messages_to_send = [system_msg] + history
    
    # Get model and bind structured output
    model = get_model()
    structured_llm = model.with_structured_output(InsuranceExtraction)
    
    try:
        response: InsuranceExtraction = await structured_llm.ainvoke(messages_to_send)
    except Exception as e:
        log.error("insurance_agent.llm_error", error=str(e))
        # Fallback to avoid breaking
        response = InsuranceExtraction(
            agent_reply="Hola, soy Mateo de Sura. ¿En qué te puedo ayudar hoy con tu seguro de salud?"
        )
        
    # 2. Update local flow state with newly extracted variables
    old_is_for_self = state.get("is_for_self")
    new_is_for_self = response.is_for_self
    
    is_for_self_changed = (old_is_for_self is not None and 
                           new_is_for_self is not None and 
                           old_is_for_self != new_is_for_self)
                           
    if is_for_self_changed:
        log.info("insurance_agent.is_for_self_changed", old=old_is_for_self, new=new_is_for_self)
        # Reset candidate details
        flow_state["candidate_name"] = None
        flow_state["candidate_relation"] = None
        flow_state["candidate_age"] = None
        flow_state["candidate_has_eps"] = None
        flow_state["candidate_eps"] = None
        flow_state["is_qualified"] = None
        flow_state["qualification_reason"] = None
        flow_state["matched_product"] = None
        flow_state["appointment_status"] = "none"
        flow_state["appointment_date"] = None
        # Reset stage to prequalification to ask questions again
        flow_state["stage"] = "prequalification"

    if response.caller_name is not None: flow_state["caller_name"] = response.caller_name
    if response.is_for_self is not None: flow_state["is_for_self"] = response.is_for_self
    if response.candidate_relation is not None: flow_state["candidate_relation"] = response.candidate_relation
    if response.candidate_name is not None: flow_state["candidate_name"] = response.candidate_name
    if response.candidate_age is not None: flow_state["candidate_age"] = response.candidate_age
    if response.candidate_has_eps is not None: flow_state["candidate_has_eps"] = response.candidate_has_eps
    if response.candidate_eps is not None: flow_state["candidate_eps"] = response.candidate_eps
    if response.email is not None: flow_state["email"] = response.email
    if response.phone is not None: flow_state["phone"] = response.phone
    
    # Copy caller_name to candidate_name if is_for_self is True
    if flow_state.get("is_for_self") is True:
        if flow_state.get("caller_name") and not flow_state.get("candidate_name"):
            flow_state["candidate_name"] = flow_state["caller_name"]
            
    # 3. Apply business rules to evaluate qualification if target criteria are present
    if (flow_state.get("candidate_age") is not None and 
        flow_state.get("candidate_has_eps") is not None and 
        (flow_state.get("candidate_has_eps") is False or flow_state.get("candidate_eps") is not None)):
        flow_state = evaluate_qualification(flow_state)
        
    # 4. Handle redirects / other products
    if response.wants_other_product:
        flow_state["stage"] = "other_products"
        if response.other_product_interest:
            state["other_product_interest"] = response.other_product_interest
            
    # 5. Determine the next stage sequence if stage transitions aren't explicitly overridden by the rules
    if flow_state["stage"] == "greeting":
        if flow_state.get("is_for_self") is not None:
            flow_state["stage"] = "prequalification"
            
    elif flow_state["stage"] == "prequalification":
        # Check if we have everything for prequalification
        has_age = flow_state.get("candidate_age") is not None
        has_eps_status = flow_state.get("candidate_has_eps") is not None
        has_eps_name = flow_state.get("candidate_eps") is not None or flow_state.get("candidate_has_eps") is False
        
        if has_age and has_eps_status and has_eps_name:
            # Prequalification evaluation already ran above and updated flow_state["stage"] to "product_matching" or "unqualified"
            pass
            
    elif flow_state["stage"] == "product_matching":
        # Check if they want to proceed (we can check messages or let LLM decide to ask for contact details)
        # For simplicity, if they express interest, go to contact info
        last_msg = messages[-1].content.lower() if messages else ""
        if any(w in last_msg for w in ["si", "claro", "bueno", "proceder", "agendar", "me interesa", "ok", "vale"]):
            flow_state["stage"] = "contact_info"
            
    elif flow_state["stage"] == "contact_info":
        if flow_state.get("email") and flow_state.get("phone"):
            flow_state["stage"] = "scheduling"
            
    elif flow_state["stage"] == "scheduling":
        # Remains in scheduling until webhook is processed
        pass

    # Save updates back to original state dictionary
    for k, v in flow_state.items():
        state[k] = v
        
    # Set the final reply in the state message list
    reply_msg = AIMessage(content=response.agent_reply)
    state["messages"] = messages + [reply_msg]
    
    return state
