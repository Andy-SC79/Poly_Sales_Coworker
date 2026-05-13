"""
channels/telegram.py
--------------------
Telegram channel for administrators — Poly Admin Hub.

Available commands:
  /start   — Welcome message
  /help    — List all available commands
  /status  — System health check (DB, Qdrant, Ollama)
  /catalog — List indexed products
  /reindex — Re-index the product catalog from products.yaml

Free-text messages are processed by Poly in admin mode.
Voice messages are automatically transcribed via Whisper.
"""
import structlog
from datetime import datetime, timezone
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
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
        "/catalog — Ver productos indexados\n"
        "/reindex — Re-indexar el catálogo desde products.yaml\n\n"
        "💬 También puedes escribirme en lenguaje natural:\n"
        "• _\"Dame un resumen de ventas de hoy\"_\n"
        "• _\"¿Cuántos clientes nuevos hay esta semana?\"_\n"
        "• _\"Poly, aprende que el colágeno ahora cuesta 90,000\"_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — Health check for all services."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    lines = [f"🔍 *Estado del sistema* — {datetime.now(timezone.utc).strftime('%H:%M UTC')}\n"]

    # Check PostgreSQL
    try:
        from core.memory.database import engine
        async with engine.connect():
            lines.append("✅ PostgreSQL: Conectado")
    except Exception as e:
        lines.append(f"❌ PostgreSQL: Error ({type(e).__name__})")

    # Check Qdrant
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        cols = client.get_collections()
        names = [c.name for c in cols.collections]
        lines.append(f"✅ Qdrant: Conectado ({len(names)} colección/es)")
    except Exception as e:
        lines.append(f"❌ Qdrant: Error ({type(e).__name__})")

    # Check Ollama
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3) as http:
            r = await http.get(f"{settings.ollama_base_url}/api/tags")
            r.raise_for_status()
            model_count = len(r.json().get("models", []))
            lines.append(f"✅ Ollama: Activo ({model_count} modelos)")
    except Exception:
        lines.append("⚠️ Ollama: No disponible (se usará OpenAI)")

    # OpenAI Key
    lines.append(
        "✅ OpenAI: Configurado" if settings.openai_api_key
        else "❌ OpenAI: Sin API key"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def catalog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/catalog — List all indexed products."""
    if not _is_admin(update):
        await update.message.reply_text("🚫 Acceso no autorizado.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        from pathlib import Path
        import yaml
        path = Path("config/products.yaml")
        if not path.exists():
            await update.message.reply_text("⚠️ No se encontró config/products.yaml")
            return

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        products = data.get("products", [])

        if not products:
            await update.message.reply_text("El catálogo está vacío.")
            return

        lines = [f"📦 *Catálogo de Productos* ({len(products)} items)\n"]
        for p in products:
            lines.append(
                f"• *{p['name']}*\n"
                f"  💰 ${p['price']:,} COP\n"
                f"  📝 {p['description'][:60]}..."
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

        path = Path("config/products.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        products = data.get("products", [])

        documents = []
        for p in products:
            content = (
                f"Producto: {p['name']}\n"
                f"ID: {p['id']}\n"
                f"Precio: ${p['price']}\n"
                f"Descripción: {p['description']}\n"
                f"Beneficios: {', '.join(p['benefits'])}\n"
                f"Dosis: {p['dosage']}\n"
            )
            documents.append(Document(
                page_content=content.strip(),
                metadata={"id": p["id"], "name": p["name"], "price": p["price"], "type": "product"}
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

    state = {
        "messages": [HumanMessage(content=text)],
        "channel": "telegram",
        "customer_id": customer_id,
        "stage": "admin",
        "is_admin": True,
        "role": long_term_profile.get("role", "owner") if long_term_profile else "owner",
        "role_metadata": long_term_profile.get("role_metadata", {}) if long_term_profile else {},
        "customer_name": long_term_profile.get("name") if long_term_profile else "Admin",
        "pain_points": [],
        "recommended_products": [],
        "order_data": None,
        "escalation_pending": False,
        "long_term_profile": long_term_profile,
    }

    config = {"configurable": {"thread_id": f"admin_{chat_id}"}}

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        graph = await get_poly_graph()
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
    app.add_handler(CommandHandler("start",   start_command))
    app.add_handler(CommandHandler("help",    help_command))
    app.add_handler(CommandHandler("status",  status_command))
    app.add_handler(CommandHandler("catalog", catalog_command))
    app.add_handler(CommandHandler("reindex", reindex_command))
    app.add_handler(CommandHandler("reset_admin", reset_admin_command))
    app.add_handler(CommandHandler("init", init_command))

    # Register free-text and voice handlers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_admin_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))

    return app
