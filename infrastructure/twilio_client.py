"""
infrastructure/twilio_client.py
------------------------------
Client for sending proactive WhatsApp messages via Twilio REST API.
Used for background tasks when the LLM processing exceeds the 15s webhook timeout.
"""
import structlog
from twilio.rest import Client
from config.settings import get_settings

settings = get_settings()
log = structlog.get_logger()

async def send_whatsapp_message(to_phone: str, message: str):
    """
    Sends a proactive WhatsApp message using the Twilio REST API.
    to_phone: The customer's phone number (with or without 'whatsapp:' prefix).
    message:  The text content to send.
    """
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        log.error("twilio.client_error", reason="Missing credentials in .env")
        return False

    try:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        
        # Ensure correct formatting for WhatsApp
        to_address = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
        from_address = settings.twilio_whatsapp_from
        if not from_address.startswith("whatsapp:"):
            from_address = f"whatsapp:{from_address}"

        # Twilio SDK is synchronous, but we wrap it in a thread pool implicitly 
        # or just call it directly as it's a fast API call compared to LLM.
        client.messages.create(
            from_=from_address,
            body=message,
            to=to_address
        )
        
        log.info("twilio.message_sent", to=to_phone, preview=message[:40])
        return True
    except Exception as e:
        log.error("twilio.message_failed", error=str(e))
        return False
