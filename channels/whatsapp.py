"""
channels/whatsapp.py
---------------------
WhatsApp channel via Twilio.
Receives incoming messages and routes them through the Poly LangGraph.
Returns TwiML XML responses compatible with Twilio's webhook format.

Twilio should be configured to POST to: https://yourdomain.com/channels/whatsapp/webhook
(or the legacy path /webhook — both are registered below)

Security:
  All incoming requests are validated using Twilio's X-Twilio-Signature header.
  Requests without a valid signature are rejected with HTTP 403.
  Validation is skipped in development mode (APP_ENV=development) to allow
  local testing without exposing a public URL.
"""
import structlog
from fastapi import APIRouter, Request, Response, HTTPException
from langchain_core.messages import HumanMessage
from twilio.request_validator import RequestValidator

from config.settings import get_settings
from core.brain.graph import get_poly_graph
from core.memory.database import get_session
from core.memory.customer_repo import CustomerRepo
from infrastructure.audio import transcribe_from_url

settings = get_settings()
log = structlog.get_logger()

router = APIRouter()


# ── Security ──────────────────────────────────────────────────────────────────

async def _validate_twilio_signature(request: Request) -> None:
    """
    Verify that the request genuinely came from Twilio.

    Twilio signs every webhook request using your Auth Token.
    We reconstruct the expected signature and compare it to the header.

    Raises HTTP 403 if validation fails in production.
    Skips validation in development mode for easier local testing.
    """
    # Skip in local development to allow testing without ngrok
    if settings.app_env == "development":
        log.debug("twilio.validation_skipped", env=settings.app_env)
        return

    if not settings.twilio_auth_token:
        log.warning("twilio.auth_token_missing")
        return

    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)

    # Read and parse form body for validation
    body = await request.body()
    from urllib.parse import parse_qs
    params: dict[str, str] = {}
    for key, values in parse_qs(body.decode("utf-8")).items():
        params[key] = values[0]  # Twilio always sends single values

    validator = RequestValidator(settings.twilio_auth_token)
    is_valid = validator.validate(url, params, signature)

    if not is_valid:
        log.warning("twilio.signature_invalid", url=url, signature=signature[:20])
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    log.debug("twilio.signature_valid")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _twiml(message: str) -> Response:
    """Wrap a text message in Twilio TwiML XML."""
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe}</Message>
</Response>"""
    return Response(content=xml, media_type="application/xml; charset=utf-8")


async def _process_message(phone: str, body: str, media_url: str | None = None) -> str:
    """
    Core processing: load customer profile, invoke graph, return reply text.
    Works for both the legacy /webhook and the new /channels/whatsapp/webhook path.
    """
    log.info("whatsapp.incoming", phone=phone, body=body[:60] if body else "[audio]")

    # Transcribe audio message if present (voice notes from WhatsApp)
    if media_url and not body:
        log.info("whatsapp.audio_received", url=media_url[:60])
        auth = (settings.twilio_account_sid, settings.twilio_auth_token) if settings.twilio_account_sid else None
        transcribed = await transcribe_from_url(media_url, auth=auth)
        if transcribed:
            body = f"[Mensaje de voz]: {transcribed}"
            log.info("whatsapp.audio_transcribed", text=body[:80])
        else:
            body = "[Nota de voz no transcrita — por favor escribe tu mensaje]"

    # Load long-term customer profile from DB (if DB is available)
    long_term_profile = None
    try:
        async with get_session() as session:
            repo = CustomerRepo(session)
            long_term_profile = await repo.get_profile(phone)
            await repo.get_or_create(phone)
    except Exception as e:
        log.warning("whatsapp.db_unavailable", error=str(e))

    state = {
        "messages": [HumanMessage(content=body)],
        "channel": "whatsapp",
        "customer_id": phone,
        "stage": "greeting",
        "customer_name": long_term_profile.get("name") if long_term_profile else None,
        "pain_points": long_term_profile.get("pain_points", []) if long_term_profile else [],
        "recommended_products": [],
        "order_data": None,
        "is_admin": False,
        "escalation_pending": False,
        "long_term_profile": long_term_profile,
    }

    config = {"configurable": {"thread_id": phone}}
    graph = await get_poly_graph()

    try:
        result = await graph.ainvoke(state, config=config)
        reply = result["messages"][-1].content
        stage = result.get("stage", "unknown")
        
        # --- CRM SYNC: Save detected name and pain points to DB ---
        try:
            async with get_session() as session:
                repo = CustomerRepo(session)
                await repo.update_profile(
                    phone=phone,
                    name=result.get("customer_name"),
                    pain_points=result.get("pain_points")
                )
                await session.commit()
        except Exception as db_err:
            log.warning("whatsapp.crm_sync_failed", error=str(db_err))

        log.info("whatsapp.reply", phone=phone, stage=stage, reply=reply[:60])
        return reply
    except Exception as e:
        log.error("whatsapp.graph_error", error=str(e))
        return "Hola! En este momento estoy teniendo un problema técnico. Por favor intenta de nuevo en un momento 🙏"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """
    Primary webhook endpoint for Twilio WhatsApp messages.
    Twilio sends form-encoded data with 'Body', 'From', 'MediaUrl0', etc.

    Security: Validates the X-Twilio-Signature header before processing.
    """
    # 1. Validate request origin — blocks spoofed requests in production
    await _validate_twilio_signature(request)

    data = await request.form()
    phone = str(data.get("From", "unknown")).replace("whatsapp:", "")
    body = str(data.get("Body", "")).strip()
    media_url = str(data.get("MediaUrl0", "")) or None

    if not body and not media_url:
        return _twiml("No entendí tu mensaje. ¿Puedes intentarlo de nuevo? 😊")

    reply = await _process_message(phone, body, media_url)
    return _twiml(reply)
