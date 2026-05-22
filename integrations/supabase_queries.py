import asyncio
import re
import structlog

from integrations.supabase_client import get_supabase
from integrations.supabase_orders import extract_phone_parts

log = structlog.get_logger()


def _clean_phone(raw_phone: str | None) -> str:
    if not raw_phone:
        return ""
    _, clean = extract_phone_parts(raw_phone)
    return clean[-10:] if clean else ""


def _norm(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"[^0-9a-zA-Z]+", " ", text).casefold().strip()


def _format_order_id(order: dict) -> str:
    order_num = order.get("Order ID", 0)
    try:
        return f"P-{int(order_num):06d}"
    except Exception:
        return "Desconocido"


def _order_phone_matches(order: dict, caller_whatsapp: str | None) -> bool:
    db_phone = _clean_phone(order.get("Whatsapp"))
    caller_phone = _clean_phone(caller_whatsapp)
    return bool(db_phone and caller_phone and db_phone == caller_phone)


def _challenge_score(
    order: dict,
    verification_name: str | None = None,
    verification_city: str | None = None,
    verification_address_fragment: str | None = None,
) -> tuple[int, list[str]]:
    matches = []

    expected_name = _norm(f"{order.get('Nombres', '')} {order.get('Apellidos', '')}")
    provided_name = _norm(verification_name)
    if provided_name and (
        provided_name in expected_name or expected_name in provided_name
    ):
        matches.append("nombre")

    expected_city = _norm(order.get("Ciudad", ""))
    provided_city = _norm(verification_city)
    if provided_city and (
        provided_city in expected_city or expected_city in provided_city
    ):
        matches.append("ciudad")

    expected_address = _norm(
        f"{order.get('Direccion', '')} {order.get('DirecciÃ³n', '')} "
        f"{order.get('Indicaciones_Adicionales', '')}"
    )
    provided_address = _norm(verification_address_fragment)
    if provided_address and provided_address in expected_address:
        matches.append("direccion")

    return len(matches), matches


def _format_customer_order(order: dict) -> str:
    tracking = order.get("Tracking Number") or "Aun no asignado"
    delivery_notes = order.get("Delivery_Notes") or "Ninguna"
    lines = [
        "Pedido encontrado:",
        f"- ID: {_format_order_id(order)}",
        f"- Producto: {order.get('Producto', 'N/A')}",
        f"- Oferta: {order.get('Oferta', 'N/A')}",
        f"- Valor a pagar: {order.get('Valor a Pagar', '0')}",
        f"- Estado: {order.get('Status', 'Pendiente')}",
        f"- Guia: {tracking}",
        f"- Notas de transportadora: {delivery_notes}",
        f"- Creado en: {order.get('Timestamp', '')}",
    ]
    return "\n".join(lines)


def _format_admin_order(order: dict) -> str:
    return "\n".join([
        "Pedido Encontrado. DATOS CRUDOS DE LA BASE DE DATOS:",
        f"  - ID Interno: {_format_order_id(order)}",
        f"  - Cliente: {order.get('Nombres', '')} {order.get('Apellidos', '')}",
        f"  - Telefono Registrado: {order.get('Indicativo Pais', '')} {order.get('Whatsapp', '')}",
        f"  - Telefono Alternativo: {order.get('NÃºmero Alternativo', 'N/A')}",
        f"  - Producto: {order.get('Producto', 'N/A')}",
        f"  - Oferta Aplicada: {order.get('Oferta', 'N/A')}",
        f"  - Valor a Pagar: {order.get('Valor a Pagar', '0')}",
        f"  - Estado (Status): {order.get('Status', 'Pendiente')}",
        f"  - Numero de Guia (Tracking_Number): {order.get('Tracking Number', 'Aun no asignado')}",
        f"  - Notas de Transportadora (Delivery_Notes): {order.get('Delivery_Notes', 'Ninguna')}",
        f"  - Direccion de Envio: {order.get('Direccion', order.get('DirecciÃ³n', ''))}",
        f"  - Notas Adicionales: {order.get('Notas_Adicionales', '')}",
        f"  - Notas Internas: {order.get('Notas', '')}",
        f"  - Creado en: {order.get('Timestamp', '')}",
    ])


async def check_order_status(
    order_id: str | None = None,
    whatsapp: str | None = None,
    tracking_number: str | None = None,
    caller_whatsapp: str | None = None,
    is_admin: bool = False,
    verification_name: str | None = None,
    verification_city: str | None = None,
    verification_address_fragment: str | None = None,
) -> str:
    """
    Search an order by ID, WhatsApp, or tracking number.

    Customer mode is protected:
    - Phone searches always use caller_whatsapp, ignoring arbitrary phone input.
    - Orders owned by caller_whatsapp are returned in sanitized form.
    - Orders not owned by caller_whatsapp require ID/tracking plus two matching
      challenge facts: name, city, or address fragment.

    Admin mode returns the detailed operational record.
    """
    if not order_id and not whatsapp and not tracking_number and not caller_whatsapp:
        return "Debes proporcionar el ID del pedido, numero de guia o consultar desde el WhatsApp del cliente."

    supabase = get_supabase()
    query = supabase.table("ORDERS").select("*")

    if tracking_number:
        query = query.eq("Tracking Number", tracking_number).order("Timestamp", desc=True).limit(1)
    elif order_id:
        clean_id = str(order_id).replace("P-", "").lstrip("0")
        try:
            query = query.eq("Order ID", int(clean_id))
        except ValueError:
            return "El ID del pedido proporcionado no es valido."
    else:
        lookup_phone = whatsapp if is_admin and whatsapp else caller_whatsapp
        clean_wp = _clean_phone(lookup_phone)
        if not clean_wp:
            return "No tengo un numero de WhatsApp valido para consultar pedidos."
        query = query.eq("Whatsapp", clean_wp).order("Timestamp", desc=True).limit(1)

    def _sync_query():
        return query.execute()

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _sync_query)

        if not response.data:
            return "No se encontro ningun pedido con esa informacion en la base de datos."

        order = response.data[0]
        if is_admin:
            return _format_admin_order(order)

        if _order_phone_matches(order, caller_whatsapp):
            return _format_customer_order(order)

        if not (order_id or tracking_number):
            return "Por seguridad, solo puedo consultar pedidos asociados al WhatsApp desde el que me escribes."

        score, matched = _challenge_score(
            order,
            verification_name=verification_name,
            verification_city=verification_city,
            verification_address_fragment=verification_address_fragment,
        )
        if score < 2:
            matched_text = ", ".join(matched) if matched else "ningun dato"
            return (
                "Por seguridad necesito validar al menos dos datos del pedido "
                "(nombre, ciudad o una parte de la direccion). "
                f"Por ahora coincide: {matched_text}."
            )

        return _format_customer_order(order)

    except Exception as e:
        log.error("order.query_failed", error=str(e))
        return f"Error al consultar la base de datos: {str(e)}"
