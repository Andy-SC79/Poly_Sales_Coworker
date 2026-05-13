"""
infrastructure/notifications.py
-------------------------------
Sends alerts and notifications to the Telegram Admin Hub.
"""
import structlog
import httpx
from config.settings import get_settings

settings = get_settings()
log = structlog.get_logger()

async def send_telegram_alert(message: str):
    """
    Send a direct message to the configured Admin Chat ID via Telegram API.
    Used for HITL alerts, sale confirmations, and system errors.
    """
    if not settings.telegram_bot_token or not settings.telegram_admin_chat_id:
        log.warning("notifications.telegram_missing_config")
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_admin_chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10)
            response.raise_for_status()
            log.info("notifications.telegram_sent")
    except Exception as e:
        log.error("notifications.telegram_failed", error=str(e))
