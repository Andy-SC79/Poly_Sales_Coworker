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
from fastapi import APIRouter, Request, Response, HTTPException, BackgroundTasks
from infrastructure.twilio_client import send_whatsapp_message
from langchain_core.messages import HumanMessage
from twilio.request_validator import RequestValidator

from config.settings import get_settings
from core.brain.graph import get_poly_graph, get_best_reply_from_messages
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
    """Wrap a text message in Twilio TwiML XML. Returns empty Response if message is empty."""
    if not message:
        xml = "<?xml version=\"1.0\" encoding=\"UTF-8\"?><Response></Response>"
        return Response(content=xml, media_type="application/xml; charset=utf-8")
        
    safe = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Message>{safe}</Message>
</Response>"""
    return Response(content=xml, media_type="application/xml; charset=utf-8")


def _build_initial_state(phone: str, body: str, long_term_profile: dict | None) -> dict:
    profile = long_term_profile or {}
    return {
        "messages": [HumanMessage(content=body)],
        "channel": "whatsapp",
        "customer_id": phone,
        "stage": "greeting",
        "customer_name": profile.get("name"),
        "city": profile.get("city"),
        "email": profile.get("email"),
        "address": profile.get("address"),
        "alternative_phone": profile.get("alternative_phone"),
        "conversation_summary": profile.get("conversation_summary"),
        "discovery_notes": None,
        "recommended_products": [],
        "order_data": None,
        "current_order_id": None,
        "is_admin": False,
        "is_paused": False,
        "escalation_pending": False,
        "long_term_profile": long_term_profile,
        "role": "customer",
        "role_metadata": {},
        "admin_notes": None,
        "last_interaction_at": None,
        "permissions": [],
        "model_provider": "default",
    }


def _build_delta_state(phone: str, body: str, long_term_profile: dict | None) -> dict:
    profile = long_term_profile or {}
    state = {
        "messages": [HumanMessage(content=body)],
        "channel": "whatsapp",
        "customer_id": phone,
        "is_admin": False,
        "role": "customer",
    }
    if long_term_profile is not None:
        state["long_term_profile"] = long_term_profile
    for target, source in [
        ("customer_name", "name"),
        ("city", "city"),
        ("email", "email"),
        ("address", "address"),
        ("alternative_phone", "alternative_phone"),
        ("conversation_summary", "conversation_summary"),
    ]:
        if profile.get(source) is not None:
            state[target] = profile.get(source)
    return state


def _build_invocation_state(
    phone: str,
    body: str,
    long_term_profile: dict | None,
    checkpoint_values: dict | None,
) -> dict:
    if checkpoint_values:
        return _build_delta_state(phone, body, long_term_profile)
    return _build_initial_state(phone, body, long_term_profile)


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

    # Load long-term customer profile from Supabase
    long_term_profile = None
    try:
        repo = CustomerRepo()
        long_term_profile = await repo.get_profile(phone)
        await repo.get_or_create(phone)
    except Exception as e:
        log.warning("whatsapp.crm_unavailable", error=str(e))

    config = {"configurable": {"thread_id": phone}}
    graph = await get_poly_graph()
    snapshot = await graph.aget_state(config)
    state = _build_invocation_state(
        phone=phone,
        body=body,
        long_term_profile=long_term_profile,
        checkpoint_values=getattr(snapshot, "values", None),
    )

    try:
        result = await graph.ainvoke(state, config=config)
        reply = get_best_reply_from_messages(result.get("messages", []))
        stage = result.get("stage", "unknown")
        
        if not isinstance(reply, str) or not reply.strip():
            reply = None
        
        # --- CRM SYNC: Save detected name and pain points to Supabase ---
        try:
            repo = CustomerRepo()
            await repo.update_profile(
                phone=phone,
                name=result.get("customer_name"),
                city=result.get("city"),
                conversation_summary=result.get("conversation_summary"),
                email=result.get("email"),
                address=result.get("address"),
                alternative_phone=result.get("alternative_phone")
            )
        except Exception as db_err:
            log.warning("whatsapp.crm_sync_failed", error=str(db_err))

        log.info(
            "whatsapp.reply",
            phone=phone,
            stage=stage,
            reply=reply[:60] if isinstance(reply, str) else None,
        )
        
        # --- SHADOWING / ESCALACIÓN: Si el mensaje pide silencio, no enviamos nada a Twilio ---
        if isinstance(reply, str) and ("[SILENCIO]" in reply or "[Silencio:" in reply):
            log.info("whatsapp.silence_detected", phone=phone)
            return None

        return reply
    except Exception as e:
        log.error("whatsapp.graph_error", error=str(e))
        return "Hola! En este momento estoy teniendo un problema técnico. Por favor intenta de nuevo en un momento 🙏"


import asyncio

async def _background_processing(phone: str, body: str, media_url: str | None, already_replied: bool = False):
    """
    Continues processing if the webhook timed out, and sends the final message.
    """
    if already_replied:
        # Si ya respondimos en el webhook, no hacemos nada más aquí
        return
        
    reply = await _process_message(phone, body, media_url)
    if reply:
        await send_whatsapp_message(phone, reply)


@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Hybrid Webhook: Attempts fast response (4s), falls back to background for slow tasks.
    """
    log.info("whatsapp.webhook_hit", method=request.method, url=str(request.url))
    await _validate_twilio_signature(request)
    data = await request.form()
    
    phone = str(data.get("From", "unknown")).replace("whatsapp:", "")
    body = str(data.get("Body", "")).strip()
    media_url = str(data.get("MediaUrl0", "")) or None

    if not body and not media_url:
        return _twiml("No entendí tu mensaje. ¿Puedes intentarlo de nuevo? 😊")

    # Intentamos procesar (Damos un margen amplio de 12 segundos para ahorrar mensajes)
    try:
        processing_task = asyncio.create_task(_process_message(phone, body, media_url))
        
        # Esperamos hasta 12 segundos. La mayoría de respuestas tardan 4-7s.
        done, pending = await asyncio.wait([processing_task], timeout=12.0)
        
        if processing_task in done:
            # ÉXITO: Respondemos en la misma conexión (1 solo mensaje gastado)
            reply = processing_task.result()
            return _twiml(reply)
        else:
            # TARDÓ DEMASIADO (Probablemente Supabase o Audio pesado)
            # Solo aquí gastamos el 2do mensaje de cortesía
            wait_msg = "¡Recibido! Dame un momento mientras proceso esto... ⏳"
            
            async def send_later():
                reply = await processing_task
                if reply:
                    await send_whatsapp_message(phone, reply)
            
            background_tasks.add_task(send_later)
            return _twiml(wait_msg)

    except Exception as e:
        log.error("whatsapp.hybrid_error", error=str(e))
        return _twiml("Lo siento, tuve un problema al procesar tu mensaje. ¿Podrías repetirlo?")
