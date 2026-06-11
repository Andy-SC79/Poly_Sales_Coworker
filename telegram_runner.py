"""
telegram_runner.py
------------------
Runs the Telegram bot in polling mode for local development.
For production, use webhook mode via FastAPI instead.
"""
import asyncio
import sys

# Windows compatibility fix for asyncio event loop policy
if sys.platform == "win32":
    import selectors
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from telegram import BotCommand
from channels.telegram import build_telegram_app

log = structlog.get_logger()

# Commands to register in Telegram's menu (shows autocomplete when user types /)
BOT_COMMANDS = [
    BotCommand("start",       "Bienvenida al panel de control"),
    BotCommand("help",        "Ver todos los comandos disponibles"),
    BotCommand("status",      "Estado del sistema (Supabase, Redis, modelo)"),
    BotCommand("models",      "Ver y cambiar el modelo de IA activo"),
    BotCommand("catalog",     "Ver productos indexados en el catálogo"),
    BotCommand("reindex",     "Re-indexar catálogo"),
    BotCommand("init",        "Inicializar sistema con owner_seed.yaml"),
    BotCommand("reset_admin", "Borrar memoria del administrador (reset)"),
]


async def main():
    log.info("telegram.runner_starting")

    from config.settings import get_settings
    settings = get_settings()

    app = build_telegram_app()
    if not app:
        log.error("telegram.runner_failed", reason="No app built. Check TELEGRAM_BOT_TOKEN.")
        return

    from core.brain.graph import get_poly_graph
    import core.brain.graph as graph_module

    try:
        graph_module._poly_graph = await get_poly_graph()
        log.info("telegram.graph_ready", persistence=False)

        async with app:
            await app.initialize()
            await app.bot.set_my_commands(BOT_COMMANDS)
            log.info("telegram.commands_registered", count=len(BOT_COMMANDS))

            await app.start()
            log.info("telegram.polling_active")
            await app.updater.start_polling()

            try:
                while True:
                    await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                log.info("telegram.runner_stopping")
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
    except Exception as e:
        log.error("telegram.runner_fatal_error", error=str(e))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
