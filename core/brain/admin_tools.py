"""
core/brain/admin_tools.py
-------------------------
Herramientas de autonomía avanzadas (CRM Memory y Logística DB) 
restringidas exclusivamente para el rol de administrador.
"""
import structlog
from langchain_core.tools import tool
from core.memory.database import get_session
from core.memory.customer_repo import CustomerRepo
from integrations.supabase_client import get_supabase
from datetime import datetime, timezone

log = structlog.get_logger()

@tool
async def read_customer_profile(phone: str):
    """
    Busca y lee el perfil completo de un cliente en la base de datos CRM.
    Devuelve su nombre, ciudad, resumen de conversaciones, rol y notas.
    """
    async with get_session() as session:
        repo = CustomerRepo(session)
        profile = await repo.get_profile(phone)
        if not profile:
            return f"No se encontró ningún cliente con el número {phone}."
        return str(profile)

@tool
async def edit_customer_profile(phone: str, field: str, value: str):
    """
    Actualiza manualmente un campo del perfil del cliente en el CRM.
    Campos permitidos: name, city, conversation_summary, profile_notes, email, address, alternative_phone.
    Úsalo para corregir datos, o limpiar el historial (pasando un value vacío '' en conversation_summary).
    """
    allowed_fields = ["name", "city", "conversation_summary", "profile_notes", "email", "address", "alternative_phone"]
    if field not in allowed_fields:
        return f"Error: Campo no permitido. Debe ser uno de {allowed_fields}"
        
    async with get_session() as session:
        repo = CustomerRepo(session)
        kwargs = {field: value}
        await repo.update_profile(phone, **kwargs)
        await session.commit()
        return f"Éxito: El campo '{field}' del cliente {phone} fue actualizado a '{value}'."

@tool
async def update_tracking_number(order_id: str, tracking_number: str, delivery_notes: str = ""):
    """
    Asigna o actualiza un número de guía a un pedido existente en Supabase, 
    y opcionalmente añade notas de la transportadora. 
    Esto bloquea el pedido impidiendo que el cliente lo cancele.
    """
    supabase = get_supabase()
    clean_id = str(order_id).replace("P-", "").lstrip("0")
    try:
        int_id = int(clean_id)
        # Verificamos si existe primero
        existing = supabase.table("ORDERS").select('"Order ID"').eq("Order ID", int_id).execute()
        if not existing.data:
            return f"Error: No se encontró ningún pedido con ID {int_id}"
            
        payload = {
            "Tracking Number": tracking_number,
            "Status": "Despachado",
            "Timestamp": datetime.now(timezone.utc).isoformat()
        }
        if delivery_notes:
            payload["Delivery_Notes"] = delivery_notes
            
        supabase.table("ORDERS").update(payload).eq("Order ID", int_id).execute()
        return f"Éxito: Guía {tracking_number} asignada al pedido {order_id}. Estado cambiado a 'Despachado'."
    except Exception as e:
        log.error("admin_tools.update_tracking_failed", error=str(e))
        return f"Error al actualizar la guía: {str(e)}"
