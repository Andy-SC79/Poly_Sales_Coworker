"""
core/brain/model_selector.py
-----------------------------
Dynamic model router. Chooses the best LLM based on the task complexity
and available providers. Centralizes all model instantiation.

Priority logic:
  - Vision / image analysis  → Gemini 2.0 Flash
  - Complex reasoning         → GPT-4o Mini
  - Simple / fast / offline   → Ollama (phi3)

Runtime override:
  - Use set_active_model(key) to switch the default model at runtime.
  - Use get_active_model_info() to read the current active model.
  - Use get_available_models() to list models that can actually be used.
"""
from functools import lru_cache
from typing import Annotated
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from core.knowledge.catalog import index_text
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from config.settings import get_settings

settings = get_settings()

# Read from env — defaults to llama3:8b if not set
_OLLAMA_MODEL = getattr(settings, 'ollama_default_model', 'llama3:8b')

# ── Runtime Model Override ─────────────────────────────────────────────────────
# Catalogue of all known model keys with human-readable names and providers.
_MODEL_CATALOGUE = {
    "gpt-4o-mini":         {"label": "GPT-4o Mini",          "provider": "openai",  "needs": "openai_api_key"},
    "gpt-4o":              {"label": "GPT-4o",               "provider": "openai",  "needs": "openai_api_key"},
    "gemini-2.0-flash":    {"label": "Gemini 2.0 Flash",     "provider": "google",  "needs": "google_api_key"},
    "gemini-2.5-flash":    {"label": "Gemini 2.5 Flash",     "provider": "google",  "needs": "google_api_key"},
    "ollama":              {"label": f"Ollama ({_OLLAMA_MODEL})", "provider": "ollama", "needs": None},
}

# The default is the first OpenAI model if key is set, else the first available.
_runtime_model_override: dict = {"key": None}  # None = use task-based logic


def get_available_models() -> list[dict]:
    """Return the list of models that can actually be used with the current API keys."""
    available = []
    for key, meta in _MODEL_CATALOGUE.items():
        needs = meta["needs"]
        if needs is None:
            # Ollama is always listed (may fail at connect time)
            available.append({"key": key, **meta})
        elif getattr(settings, needs, ""):
            available.append({"key": key, **meta})
    return available


def get_active_model_info() -> dict:
    """Return info about the currently active model."""
    override_key = _runtime_model_override["key"]
    if override_key and override_key in _MODEL_CATALOGUE:
        meta = _MODEL_CATALOGUE[override_key]
        return {"key": override_key, "label": meta["label"], "provider": meta["provider"], "is_override": True}
    # Determine default from configured keys
    if settings.openai_api_key:
        return {"key": "gpt-4o-mini", "label": "GPT-4o Mini", "provider": "openai", "is_override": False}
    if settings.google_api_key:
        return {"key": "gemini-2.0-flash", "label": "Gemini 2.0 Flash", "provider": "google", "is_override": False}
    return {"key": "ollama", "label": f"Ollama ({_OLLAMA_MODEL})", "provider": "ollama", "is_override": False}


def set_active_model(model_key: str) -> bool:
    """Override the default model at runtime. Returns True if the key is valid and available."""
    available_keys = {m["key"] for m in get_available_models()}
    if model_key not in available_keys:
        return False
    _runtime_model_override["key"] = model_key
    return True


def _caller_from_state(state: dict | None) -> str | None:
    """Return the trusted actor identity for state-aware tools."""
    if state and state.get("is_admin"):
        return "admin"
    if state:
        return state.get("customer_id")
    return None

# ── Tool Definitions ──────────────────────────────────────────────────────────

@tool
async def update_catalog(content: str, product_name: str = "General", doc_type: str = "product"):
    """
    Agrega o actualiza información en el conocimiento de Poly.
    doc_type puede ser: 'product', 'policy' o 'company_info'.
    """
    from core.knowledge.catalog import index_text
    # Usamos el product_name como ID para evitar duplicados en el caso de productos
    doc_id = f"{doc_type}_{product_name.lower().replace(' ', '_')}"
    await index_text(content, metadata={"product_name": product_name, "type": doc_type}, doc_id=doc_id)
    return f"¡Hecho! He integrado la información de '{product_name}' como {doc_type}."

@tool
async def verify_fact(product_name: str):
    """
    Verifica el precio y stock REAL de un producto.
    Consulta el catálogo maestro (YAML) y los proveedores externos.
    Úsalo SIEMPRE antes de dar un precio final para evitar errores.
    """
    import yaml
    from integrations.dropshipping_api import dropshipping_api
    
    # 1. Check local master

    try:
        with open("config/catalog.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            items = data.get("products") or data.get("items") or []
            for p in items:
                if product_name.lower() in p.get("name", "").lower():
                    price = None
                    # 1. Usar base_price si existe
                    if 'base_price' in p and isinstance(p['base_price'], (int, float)):
                        price = p['base_price']
                    # 2. Buscar el menor precio en offers
                    elif 'offers' in p and isinstance(p['offers'], list) and len(p['offers']) > 0:
                        offer_prices = [o.get('price') for o in p['offers'] if isinstance(o, dict) and 'price' in o and isinstance(o['price'], (int, float))]
                        if offer_prices:
                            price = min(offer_prices)
                    price_display = f"${price:,}" if price is not None else "Consulte con Poly"
                    return f"DATO OFICIAL (Local): {p.get('name', 'Sin nombre')} - Precio: {price_display} - Stock/Dispo: {p.get('stock', 'N/A')}"
    except Exception:
        pass
        
    # 2. Check external Dropshipping API
    ext = await dropshipping_api.search_products(product_name)
    if ext:
        p = ext[0]
        return f"DATO OFICIAL (Proveedor Externo): {p['name']} - Precio: ${p['price']} - Stock: {p.get('stock', 'N/A')}"
        
    return f"No encontré datos oficiales para '{product_name}'."

@tool
async def submit_order_to_supabase(
    state: Annotated[dict, InjectedState()],
    nombres: str,
    apellidos: str,
    whatsapp: str,
    departamento: str,
    ciudad: str,
    main_address: str,
    neighborhood: str,
    producto: str,
    valor_a_pagar: str,
    reference_point: str = "",
    order_id: str = None,
    indicativo_pais: str = "+57",
    numero_alternativo: str = "",
    notas: str = "",
    email: str = "",
    metodo_pago: str = "Contraentrega",
    oferta: str = "Precio Regular",
    sku: str = "",
    dropi_product_id: int = None
):
    """
    Registra un pedido final en Supabase. 
    Si ya existe un 'order_id', lo actualizará.
    La identidad autorizada se inyecta automaticamente desde el canal.
    """
    from integrations.supabase_orders import submit_order_to_supabase as submit_fn
    try:
        return await submit_fn(
            nombres=nombres, apellidos=apellidos, whatsapp=whatsapp,
            departamento=departamento, ciudad=ciudad, main_address=main_address,
            neighborhood=neighborhood, reference_point=reference_point,
            producto=producto, valor_a_pagar=valor_a_pagar, order_id=order_id,
            indicativo_pais=indicativo_pais, numero_alternativo=numero_alternativo,
            notas_adicionales=notas, email=email, metodo_pago=metodo_pago,
            oferta=oferta, sku=sku, dropi_product_id=dropi_product_id,
            caller_whatsapp=_caller_from_state(state)
        )
    except TypeError as e:
        return {
            "id": None,
            "message": f"❌ Error interno en submit_order_to_supabase: {str(e)}"
        }
    except Exception as e:
        return {
            "id": None,
            "message": f"❌ Error inesperado en submit_order_to_supabase: {str(e)}"
        }

@tool
async def cancelar_pedido(state: Annotated[dict, InjectedState()], order_id: str):
    """
    Anula un pedido existente en el sistema.
    Úsalo si el cliente solicita explícitamente cancelar su compra.
    Debes tener el order_id (ej: P-000007).
    La identidad autorizada se inyecta automaticamente desde el canal.
    """
    from integrations.supabase_orders import update_order_status
    return await update_order_status(order_id, "Anulado", _caller_from_state(state))

@tool
async def escalar_consulta_humana(state: Annotated[dict, InjectedState()], pregunta: str):
    """
    Úsalo cuando NO sepas la respuesta a una pregunta del cliente o haya un problema complejo.
    Pausa tu flujo y notifica a tu supervisor humano.
    NO le digas al cliente que se comunique con servicio al cliente, usa esto en su lugar.
    La identidad del cliente se inyecta automaticamente desde el canal.
    """
    from infrastructure.notifications import send_telegram_alert
    caller_whatsapp = _caller_from_state(state)
    msg = f"🚨 *ESCALACIÓN DESDE HERRAMIENTA*\n👤 Cliente: {caller_whatsapp}\n💬 Pregunta/Problema: {pregunta}"
    await send_telegram_alert(msg, customer_id=caller_whatsapp)
    return f"PAUSA: Se ha enviado la alerta al supervisor en Telegram. Dile al cliente: 'Un momento por favor, voy a consultar eso con mi supervisor y ya regreso contigo.'"

@tool
async def validate_order_data(
    full_name: str, 
    whatsapp_number: str,
    email: str | None = None,
    alternative_phone: str = None,
    department: str = None, 
    city: str = None, 
    main_address: str = None,
    neighborhood: str = None,
    reference_point: str = "",
    payment_method: str = None, 
    product_name: str = None, 
    quantity: int = 1,
    sku: str = ""
):
    """
    Valida los datos del pedido antes de enviarlos a Supabase.
    Incluye validación de Correo (MX) y Nomenclatura de Dirección.
    Úsalo cuando el cliente te dé sus datos.
    """
    from core.brain.validation import validate_order
    data = {
        "full_name": full_name,
        "email": email,
        "whatsapp_number": whatsapp_number,
        "alternative_phone": alternative_phone,
        "department": department,
        "city": city,
        "main_address": main_address,
        "neighborhood": neighborhood,
        "reference_point": reference_point,
        "payment_method": payment_method,
        "product_name": product_name,
        "quantity": quantity,
        "sku": sku
    }
    return validate_order(data)

@tool
async def search_external_catalog(query: str):
    """
    Busca productos en proveedores de Dropshipping externos.
    Úsalo para ampliar la oferta si el cliente busca algo que no manejamos localmente.
    """
    from integrations.dropshipping_api import dropshipping_api
    results = await dropshipping_api.search_products(query)
    return f"Resultados externos:\n{results}" if results else "No hay coincidencias en proveedores externos."


@tool
async def add_order_note(
    state: Annotated[dict, InjectedState()],
    order_id: str,
    notas_adicionales: str,
):
    """
    Agrega una nota interna a un pedido sin alterar su estado logistico.
    La identidad autorizada del cliente se inyecta automaticamente desde el canal.
    """
    from integrations.supabase_orders import add_order_note as add_note_fn

    return await add_note_fn(
        order_id=order_id,
        notas_adicionales=notas_adicionales,
        caller_whatsapp=_caller_from_state(state),
    )


@tool
async def check_order_status(
    state: Annotated[dict, InjectedState()],
    order_id: str | None = None,
    whatsapp: str | None = None,
    tracking_number: str | None = None,
    verification_name: str | None = None,
    verification_city: str | None = None,
    verification_address_fragment: str | None = None,
):
    """
    Consulta el estado de un pedido. En modo cliente, el backend valida el
    WhatsApp de origen o exige dos datos de verificacion si el pedido no
    coincide con ese origen. En modo admin devuelve detalle operacional.
    """
    from integrations.supabase_queries import check_order_status as check_fn

    return await check_fn(
        order_id=order_id,
        whatsapp=whatsapp,
        tracking_number=tracking_number,
        caller_whatsapp=_caller_from_state(state),
        is_admin=bool(state.get("is_admin")) if state else False,
        verification_name=verification_name,
        verification_city=verification_city,
        verification_address_fragment=verification_address_fragment,
    )


submit_order_to_supabase.description = (
    "Registra o actualiza un pedido en Supabase. La identidad autorizada "
    "del cliente o admin se inyecta automaticamente desde el estado del canal."
)
cancelar_pedido.description = (
    "Anula un pedido existente. La identidad autorizada se inyecta "
    "automaticamente desde el estado del canal."
)
escalar_consulta_humana.description = (
    "Notifica al supervisor humano cuando hay una consulta o problema complejo. "
    "La identidad del cliente se toma automaticamente del canal."
)


web_search_tool = DuckDuckGoSearchRun(
    name="web_search",
    description=(
        "Busca en Google/DuckDuckGo sobre competencia o temas generales. "
        "NO lo uses para precios propios, usa 'verify_fact' para eso."
    )
)


def get_customer_tools():
    """Tools available to customer-facing agents."""
    return [
        verify_fact,
        search_external_catalog,
        check_order_status,
        add_order_note,
        validate_order_data,
        submit_order_to_supabase,
        cancelar_pedido,
        escalar_consulta_humana,
        web_search_tool,
    ]


def get_admin_tools():
    """Tools available to admin agents, including customer-safe tools."""
    from core.brain.bi_tools import query_business_intelligence
    from core.brain.architect import read_system_config, update_system_config, restore_system_config
    from core.brain.admin_tools import read_customer_profile, edit_customer_profile, update_tracking_number

    return get_customer_tools() + [
        update_catalog,
        tool(query_business_intelligence),
        tool(read_system_config),
        tool(update_system_config),
        tool(restore_system_config),
        read_customer_profile,
        edit_customer_profile,
        update_tracking_number,
    ]


def _instantiate_model(model_key: str) -> "BaseChatModel | None":
    """Instantiate an LLM from a catalogue key. Returns None if unavailable."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    if model_key == "gpt-4o-mini" and settings.openai_api_key:
        return ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key, temperature=0.7, max_tokens=512)
    if model_key == "gpt-4o" and settings.openai_api_key:
        return ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key, temperature=0.7, max_tokens=512)
    if model_key == "gemini-2.0-flash" and settings.google_api_key:
        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=settings.google_api_key, temperature=0.7)
    if model_key == "gemini-2.5-flash" and settings.google_api_key:
        return ChatGoogleGenerativeAI(model="gemini-2.5-flash-preview-05-20", google_api_key=settings.google_api_key, temperature=0.7)
    if model_key == "ollama":
        return ChatOllama(model=_OLLAMA_MODEL, base_url=settings.ollama_base_url, temperature=0.7)
    return None


def get_model(task: str = "default", is_admin: bool = False) -> BaseChatModel:
    """
    Return the appropriate LLM for the given task type, with tools bound if permitted.
    Respects the runtime model override set via set_active_model().
    """
    model_instance = None

    # 0. Runtime override — always takes priority (except for explicit vision/ollama tasks)
    override_key = _runtime_model_override["key"]
    if override_key and task not in ("vision", "ollama"):
        model_instance = _instantiate_model(override_key)

    if model_instance is None:
        # 1. Vision tasks — Prefer Gemini
        if task == "vision" and settings.google_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            model_instance = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                google_api_key=settings.google_api_key,
                temperature=0.7,
            )

        # 2. Forced Ollama
        elif task == "ollama":
            model_instance = ChatOllama(
                model=_OLLAMA_MODEL,
                base_url=settings.ollama_base_url,
                temperature=0.7,
            )

        # 3. Primary / Production Default: GPT-4o Mini
        elif task in ["complex", "default"] and settings.openai_api_key:
            model_instance = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=settings.openai_api_key,
                temperature=0.7,
                max_tokens=512,
            )

        # 4. Local / Offline — Use Ollama
        else:
            try:
                model_instance = ChatOllama(
                    model=_OLLAMA_MODEL,
                    base_url=settings.ollama_base_url,
                    temperature=0.7,
                )
            except Exception:
                # Fallback to Gemini if everything else fails and key is there
                if settings.google_api_key:
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    model_instance = ChatGoogleGenerativeAI(
                        model="gemini-2.0-flash",
                        google_api_key=settings.google_api_key,
                        temperature=0.7,
                    )

    if not model_instance:
        raise ValueError("No LLM provider configured")

    # 5. RBAC Tool Binding (Role-Based Access Control)
    available_tools = get_admin_tools() if is_admin else get_customer_tools()

    if available_tools:
        return model_instance.bind_tools(available_tools)

    return model_instance


@lru_cache(maxsize=4)
def get_cached_model(task: str = "default") -> BaseChatModel:
    """Cached version — reuse model instances for efficiency."""
    return get_model(task)
