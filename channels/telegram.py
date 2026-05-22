"""
channels/telegram.py
--------------------
Telegram channel for administrators — Poly Admin Hub.

Available commands:
  /start       — Welcome message
  /help        — List all available commands
  /status      — System health check (Supabase, Qdrant, Redis, active model)
  /models      — List available LLMs and switch active model
  /catalog     — List indexed products
  /reindex     — Re-index the product catalog from catalog.yaml

Free-text messages are processed by Poly in admin mode.
Voice messages are automatically transcribed via Whisper.
"""
import structlog
from datetime import datetime, timezone
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config.settings import get_settings
from core.brain.graph import get_poly_graph
from langchain_core.messages import HumanMessage
from infrastructure.audio import transcribe_from_bytes

settings = get_settings()
log = structlog.get_logger()

# ── Auth Guard ────────────────────────────────────────────────────────────────

def _is_admin(update: Update) -> bool:
    return str(update.effective_chat.id) == settings.telegram_admin_chat_id


# ── Commands ──────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — Welcome message."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return
    user_name = update.effective_user.first_name
    text = (
        f"👋 ¡Hola {user_name}! Soy *Poly*, tu panel de control de ventas.\n\n"
        "Usa /help para ver todos los comandos disponibles.\n"
        "O simplemente escríbeme lo que necesitas 💬"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    log.info("telegram.start_command", user=user_name)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help — List all available commands."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return
    text = (
        "📋 *Comandos disponibles:*\n\n"
        "/start — Bienvenida\n"
        "/help — Esta ayuda\n"
        "/status — Estado del sistema\n"
        "/models — Ver y cambiar modelo de IA activo\n"
        "/catalog — Ver productos indexados\n"
        "/reindex — Re-indexar el catálogo desde catalog.yaml\n\n"
        "💬 También puedes escribirme en lenguaje natural:\n"
        "• _\"Dame un resumen de ventas de hoy\"_\n"
        "• _\"¿Cuántos clientes nuevos hay esta semana?\"_\n"
        "• _\"Poly, aprende que el colágeno ahora cuesta 90,000\"_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — Health check for all active services."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    now = datetime.now(timezone.utc).strftime("%H:%M UTC")
    lines = [f"🔍 *Estado del Sistema* — {now}\n"]

    # ── Active Model ─────────────────────────────────────────────────────────
    from core.brain.model_selector import get_active_model_info
    model_info = get_active_model_info()
    provider_icons = {"openai": "🟢", "google": "🔵", "ollama": "🟡"}
    icon = provider_icons.get(model_info["provider"], "⚪")
    override_tag = " _(override manual)_" if model_info["is_override"] else " _(por defecto)_"
    lines.append(f"{icon} *Modelo activo:* {model_info['label']}{override_tag}")

    # ── Supabase / PostgreSQL ─────────────────────────────────────────────────
    try:
        import psycopg
        from urllib.parse import urlparse
        db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await psycopg.AsyncConnection.connect(db_url, autocommit=True, connect_timeout=8)
        await conn.close()
        # Extract host for display
        parsed = urlparse(db_url)
        host_short = parsed.hostname.split(".")[0] if parsed.hostname else "supabase"
        lines.append(f"✅ *Supabase (PostgreSQL):* Conectado · `{host_short}`")
    except Exception as e:
        lines.append(f"❌ *Supabase:* Error ({type(e).__name__})")

    # ── Qdrant ────────────────────────────────────────────────────────────────
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        cols = client.get_collections()
        names = [c.name for c in cols.collections]
        lines.append(f"✅ *Qdrant:* {len(names)} colección/es · `{settings.qdrant_host}:{settings.qdrant_port}`")
    except Exception as e:
        lines.append(f"❌ *Qdrant:* No disponible ({type(e).__name__})")

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=5)
        await r.ping()
        await r.aclose()
        lines.append(f"✅ *Redis:* Conectado · `{settings.redis_url.split('@')[-1]}`")
    except Exception as e:
        lines.append(f"❌ *Redis:* No disponible ({type(e).__name__})")

    # ── API Keys configuradas ─────────────────────────────────────────────────
    lines.append("")
    lines.append("🔑 *API Keys:*")
    lines.append("  ✅ OpenAI" if settings.openai_api_key else "  ❌ OpenAI — sin key")
    lines.append("  ✅ Google/Gemini" if settings.google_api_key else "  ⚠️ Google/Gemini — sin key")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/models — Show available LLMs and allow switching the active one."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    from core.brain.model_selector import get_available_models, get_active_model_info
    available = get_available_models()
    active = get_active_model_info()

    provider_icons = {"openai": "🟢", "google": "🔵", "ollama": "🟡"}

    # Build inline keyboard — one button per model
    keyboard = []
    for model in available:
        icon = provider_icons.get(model["provider"], "⚪")
        is_active = model["key"] == active["key"]
        label = f"{'✦ ' if is_active else ''}{icon} {model['label']}{' ← activo' if is_active else ''}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"set_model:{model['key']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    override_tag = " _(override manual)_" if active["is_override"] else " _(por defecto)_"
    text = (
        f"🤖 *Modelos de IA disponibles*\n\n"
        f"Activo: *{active['label']}*{override_tag}\n\n"
        f"Toca un botón para cambiar:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)


async def handle_model_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback for inline model selection buttons."""
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("set_model:"):
        return

    model_key = query.data.split("set_model:", 1)[1]

    from core.brain.model_selector import set_active_model, get_available_models, get_active_model_info
    success = set_active_model(model_key)

    if not success:
        await query.edit_message_text("❌ Modelo no disponible. Verifica que la API key esté configurada.")
        return

    active = get_active_model_info()
    available = get_available_models()
    provider_icons = {"openai": "🟢", "google": "🔵", "ollama": "🟡"}

    # Rebuild keyboard with new active selection highlighted
    keyboard = []
    for model in available:
        icon = provider_icons.get(model["provider"], "⚪")
        is_active = model["key"] == active["key"]
        label = f"{'✦ ' if is_active else ''}{icon} {model['label']}{' ← activo' if is_active else ''}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"set_model:{model['key']}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"✅ *Modelo cambiado a: {active['label']}*\n\n"
        f"Poly usará este modelo en todas las conversaciones activas.\n"
        f"_(El cambio es temporal — se resetea al reiniciar)_"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    log.info("telegram.model_switched", model=active["key"], label=active["label"])


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/catalog — List all indexed products."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        from pathlib import Path
        import yaml
        path = Path("config/catalog.yaml")
        if not path.exists():
            await update.message.reply_text("⚠️ No se encontró config/catalog.yaml")
            return

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        products = data.get("products") or data.get("items") or []

        if not products:
            await update.message.reply_text("El catálogo está vacío.")
            return


        lines = [f"📦 *Catálogo de Productos* ({len(products)} items)\n"]
        for p in products:
            price_display = "Consulte con Poly"
            price = None
            # 1. Usar base_price si existe
            if 'base_price' in p and isinstance(p['base_price'], (int, float)):
                price = p['base_price']
            # 2. Buscar el menor precio en offers
            elif 'offers' in p and isinstance(p['offers'], list) and len(p['offers']) > 0:
                offer_prices = [o.get('price') for o in p['offers'] if isinstance(o, dict) and 'price' in o and isinstance(o['price'], (int, float))]
                if offer_prices:
                    price = min(offer_prices)
            # 3. Mostrar el precio si se encontró
            if price is not None:
                price_display = f"${price:,} COP"

            lines.append(
                f"• *{p.get('name', 'Sin nombre')}*\n"
                f"  💰 {price_display}\n"
                f"  📝 {p.get('description', '')[:60]}..."
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        log.error("telegram.catalog_command_error", error=str(e))
        await update.message.reply_text(f"❌ Error leyendo catálogo: {e}")


async def reindex_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reindex — Re-index product catalog into Qdrant."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    await update.message.reply_text("⏳ Iniciando re-indexación del catálogo...")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        from pathlib import Path
        import yaml
        from langchain_core.documents import Document
        from core.knowledge.catalog import index_documents
        from qdrant_client import QdrantClient

        path = Path("config/catalog.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        products = data.get("products") or data.get("items") or []


        documents = []
        for p in products:
            price = None
            # 1. Usar base_price si existe
            if 'base_price' in p and isinstance(p['base_price'], (int, float)):
                price = p['base_price']
            # 2. Buscar el menor precio en offers
            elif 'offers' in p and isinstance(p['offers'], list) and len(p['offers']) > 0:
                offer_prices = [o.get('price') for o in p['offers'] if isinstance(o, dict) and 'price' in o and isinstance(o['price'], (int, float))]
                if offer_prices:
                    price = min(offer_prices)
            # 3. Mostrar el precio si se encontró
            price_display = f"${price:,} COP" if price is not None else "Consultar Ofertas"

            content = (
                f"Producto: {p.get('name', 'Sin nombre')}\n"
                f"ID: {p.get('id', '')}\n"
                f"Precio: {price_display}\n"
                f"Descripción: {p.get('description', '')}\n"
                f"Beneficios: {', '.join(p.get('benefits', []))}\n"
                f"Dosis: {p.get('dosage', '')}\n"
            )
            documents.append(Document(
                page_content=content.strip(),
                metadata={"id": p.get("id", ""), "name": p.get("name", ""), "price": price, "type": "product"}
            ))

        # Clear and re-index
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        client.delete_collection(settings.qdrant_collection_name)
        await index_documents(documents)

        await update.message.reply_text(
            f"✅ Catálogo re-indexado: *{len(documents)} productos* cargados correctamente.",
            parse_mode="Markdown"
        )
        log.info("telegram.reindex_done", count=len(documents))

    except Exception as e:
        log.error("telegram.reindex_error", error=str(e))
        await update.message.reply_text(f"❌ Error durante la re-indexación: {e}")


async def reset_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset_admin — Clear all learned admin memory."""
    if not _is_admin(update):
        return
    
    from core.memory.database import get_session
    from core.memory.customer_repo import CustomerRepo
    customer_id = f"admin_{update.effective_chat.id}"
    
    try:
        async with get_session() as session:
            from core.memory.models import Customer
            from sqlalchemy import delete
            await session.execute(delete(Customer).where(Customer.phone == customer_id))
            await session.commit()
        await update.message.reply_text("🧹 Memoria del administrador borrada. Soy una hoja en blanco para ti.")
        log.info("telegram.admin_reset", user=customer_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Error al resetear: {e}")


async def init_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/init — Load seed instructions into admin profile."""
    if not _is_admin(update):
        return
    
    from pathlib import Path
    import yaml
    from core.memory.database import get_session
    from core.memory.customer_repo import CustomerRepo
    customer_id = f"admin_{update.effective_chat.id}"
    
    path = Path("config/owner_seed.yaml")
    if not path.exists():
        await update.message.reply_text("⚠️ No se encontró config/owner_seed.yaml")
        return

    try:
        seed = yaml.safe_load(path.read_text(encoding="utf-8"))
        owner = seed.get("owner", {})
        goals = seed.get("business_goals", {})
        prefs = seed.get("preferences", {})
        
        notes = (
            f"Dueño: {owner.get('name')} ({owner.get('role')})\n"
            f"Objetivos: {goals.get('primary')} / {goals.get('secondary')}\n"
            f"Preferencia de tono: {prefs.get('tone')}\n"
            f"Estilo de trabajo: {prefs.get('working_style')}\n"
            f"Reglas: {prefs.get('communication_rules')}\n"
            f"Instrucciones iniciales: {seed.get('initial_instructions', '')}"
        )

        async with get_session() as session:
            repo = CustomerRepo(session)
            await repo.update_profile(
                phone=customer_id,
                name=owner.get("name"),
                role="owner",
                profile_notes=notes
            )
            await session.commit()
            
        await update.message.reply_text(f"✅ ¡Sistema inicializado para *{owner.get('name')}*! He cargado tus objetivos y preferencias.", parse_mode="Markdown")
        log.info("telegram.admin_init", user=customer_id)
    except Exception as e:
        log.error("telegram.init_error", error=str(e))
        await update.message.reply_text(f"❌ Error durante la inicialización: {e}")


# ── Free-text & Voice Handlers ────────────────────────────────────────────────

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process free-text messages sent to the admin bot."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 No tienes permiso para usar este panel.")
        log.warning("telegram.unauthorized_access", chat_id=update.effective_chat.id)
        return

    text = update.message.text
    log.info("telegram.admin_message", text=text)

    # Lógica de PUENTE hacia WhatsApp
    triggers = ["dile al cliente", "responde", "contéstale"]
    if any(text.lower().startswith(t) for t in triggers):
        from infrastructure.notifications import LAST_ESCALATED_CUSTOMER
        from infrastructure.twilio_client import send_whatsapp_message
        
        if not LAST_ESCALATED_CUSTOMER:
            await update.message.reply_text("❌ No tengo un cliente activo en este momento. Espera a que alguien pida ayuda.")
            return

        # Extraer el mensaje real (ej: "Poly dile al cliente que espere" -> "que espere")
        actual_message = text
        for t in triggers:
            if actual_message.lower().startswith(t):
                actual_message = actual_message[len(t):].strip(": ").strip()
                break
        
        if not actual_message:
            await update.message.reply_text("⚠️ ¿Qué quieres que le diga? Escribe: *Dile al cliente [mensaje]*", parse_mode="Markdown")
            return

        success = await send_whatsapp_message(LAST_ESCALATED_CUSTOMER, actual_message)
        if success:
            await update.message.reply_text(f"✅ Enviado a WhatsApp ({LAST_ESCALATED_CUSTOMER}):\n_{actual_message}_", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Error al enviar mensaje a WhatsApp. Revisa el log.")
        return

    await _respond_to_admin(update, context, update.effective_chat.id, text)


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribe and process voice messages sent to the admin bot."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        audio_bytes = await voice_file.download_as_bytearray()
        transcribed = await transcribe_from_bytes(bytes(audio_bytes), filename="voice.ogg")

        if transcribed:
            log.info("telegram.voice_transcribed", text=transcribed[:80])
            await update.message.reply_text(f"🎙️ Escuché: _{transcribed}_", parse_mode="Markdown")
            await _respond_to_admin(update, context, update.effective_chat.id, transcribed)
        else:
            await update.message.reply_text("No pude transcribir el audio. Por favor escribe tu mensaje.")
    except Exception as e:
        log.error("telegram.voice_error", error=str(e))
        await update.message.reply_text("Error procesando el audio.")


def _build_initial_admin_state(customer_id: str, text: str, long_term_profile: dict | None) -> dict:
    profile = long_term_profile or {}
    return {
        "messages": [HumanMessage(content=text)],
        "channel": "telegram",
        "customer_id": customer_id,
        "stage": "admin",
        "customer_name": profile.get("name") or "Admin",
        "city": profile.get("city"),
        "email": profile.get("email"),
        "address": profile.get("address"),
        "alternative_phone": profile.get("alternative_phone"),
        "conversation_summary": None,
        "discovery_notes": None,
        "recommended_products": [],
        "order_data": None,
        "current_order_id": None,
        "is_admin": True,
        "is_paused": False,
        "escalation_pending": False,
        "long_term_profile": long_term_profile,
        "role": profile.get("role", "owner"),
        "role_metadata": profile.get("role_metadata", {}),
        "admin_notes": None,
        "last_interaction_at": None,
        "permissions": ["admin"],
        "model_provider": "default",
    }


def _build_delta_admin_state(customer_id: str, text: str, long_term_profile: dict | None) -> dict:
    profile = long_term_profile or {}
    state = {
        "messages": [HumanMessage(content=text)],
        "channel": "telegram",
        "customer_id": customer_id,
        "is_admin": True,
        "role": profile.get("role", "owner"),
        "role_metadata": profile.get("role_metadata", {}),
    }
    if long_term_profile is not None:
        state["long_term_profile"] = long_term_profile
    if profile.get("name"):
        state["customer_name"] = profile.get("name")
    return state


def _build_admin_invocation_state(
    customer_id: str,
    text: str,
    long_term_profile: dict | None,
    checkpoint_values: dict | None,
) -> dict:
    if checkpoint_values:
        return _build_delta_admin_state(customer_id, text, long_term_profile)
    return _build_initial_admin_state(customer_id, text, long_term_profile)


async def _respond_to_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
) -> None:
    customer_id = f"admin_{chat_id}"
    # Load long-term profile (for admin, this stores goals/instructions)
    long_term_profile = None
    from core.memory.database import get_session
    from core.memory.customer_repo import CustomerRepo
    try:
        async with get_session() as session:
            repo = CustomerRepo(session)
            long_term_profile = await repo.get_profile(customer_id)
            await repo.get_or_create(customer_id)
    except Exception as e:
        log.warning("telegram.db_unavailable", error=str(e))

    config = {"configurable": {"thread_id": f"admin_{chat_id}"}}

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        graph = await get_poly_graph()
        snapshot = await graph.aget_state(config)
        state = _build_admin_invocation_state(
            customer_id=customer_id,
            text=text,
            long_term_profile=long_term_profile,
            checkpoint_values=getattr(snapshot, "values", None),
        )
        result = await graph.ainvoke(state, config=config)
        reply = result["messages"][-1].content
        
        # --- CRM SYNC: Save admin notes to profile_notes ---
        if result.get("admin_notes"):
            try:
                async with get_session() as session:
                    repo = CustomerRepo(session)
                    await repo.update_profile(
                        phone=customer_id,
                        profile_notes=result.get("admin_notes")
                    )
                    await session.commit()
            except Exception as db_err:
                log.warning("telegram.crm_sync_failed", error=str(db_err))

        await update.message.reply_text(reply)
    except Exception as e:
        log.error("telegram.graph_error", error=str(e))
        await update.message.reply_text("❌ Error procesando el comando admin.")


# ── Application Factory ───────────────────────────────────────────────────────

def build_telegram_app():
    """Construct the Telegram application instance with all command handlers."""
    if not settings.telegram_bot_token:
        log.warning("telegram.token_missing")
        return None

    app = ApplicationBuilder().token(settings.telegram_bot_token).build()

    # Register all commands
    app.add_handler(CommandHandler("start",       start_command))
    app.add_handler(CommandHandler("help",        help_command))
    app.add_handler(CommandHandler("status",      status_command))
    app.add_handler(CommandHandler("models",      models_command))
    app.add_handler(CommandHandler("catalog",     catalog_command))
    app.add_handler(CommandHandler("reindex",     reindex_command))
    app.add_handler(CommandHandler("reset_admin", reset_admin_command))
    app.add_handler(CommandHandler("init",        init_command))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_model_selection, pattern=r"^set_model:"))

    # Register free-text and voice handlers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_admin_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    return app
