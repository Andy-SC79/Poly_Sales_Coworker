"""
infrastructure/audio.py
------------------------
Audio transcription service using OpenAI Whisper API.

Supports:
  - WhatsApp voice messages (OGG/Opus format from Twilio)
  - Telegram voice messages (OGG/Opus format)
  - General audio files via URL

Requirements:
  - OPENAI_API_KEY set in .env
  - ffmpeg installed on the system (for format conversion)
"""
import structlog
import httpx
import tempfile
import os
from pathlib import Path

from config.settings import get_settings

settings = get_settings()
log = structlog.get_logger()


async def transcribe_from_url(
    audio_url: str,
    auth: tuple[str, str] | None = None,
    language: str = "es",
) -> str | None:
    """
    Download an audio file from a URL and transcribe it using OpenAI Whisper.

    Args:
        audio_url:  Public URL to the audio file (Twilio or Telegram CDN).
        auth:       Optional (user, password) tuple for authenticated downloads
                    (required for Twilio media URLs).
        language:   BCP-47 language code hint for better accuracy. Default: "es" (Spanish).

    Returns:
        Transcribed text string, or None if transcription failed.
    """
    if not settings.openai_api_key:
        print("\n❌ [AUDIO ERROR] No hay OPENAI_API_KEY en el .env")
        log.error("audio.transcription_skipped", reason="No OPENAI_API_KEY configured")
        return None

    print(f"\n🎧 [AUDIO] Intentando descargar: {audio_url[:50]}...")

    try:
        # 1. Download audio to a temporary file
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            if auth:
                response = await client.get(audio_url, auth=auth)
            else:
                response = await client.get(audio_url)
            
            if response.status_code != 200:
                print(f"❌ [AUDIO ERROR] Twilio devolvió error {response.status_code}")
                response.raise_for_status()

        # Detect extension from content type
        content_type = response.headers.get("content-type", "audio/ogg")
        print(f"📄 [AUDIO] Formato detectado: {content_type}")
        extension = _content_type_to_ext(content_type)

        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        print(f"💾 [AUDIO] Archivo guardado temporalmente: {tmp_path}")

        # 2. Transcribe using OpenAI Whisper API
        transcription = await _whisper_transcribe(tmp_path, language)
        
        if not transcription:
            print("❌ [AUDIO ERROR] La transcripción de Whisper llegó vacía")
        else:
            print(f"✅ [AUDIO OK] Transcripción: {transcription[:50]}...")
            
        return transcription

    except Exception as e:
        print(f"❌ [AUDIO EXCEPCIÓN] Error crítico: {str(e)}")
        log.error("audio.transcription_failed", error=str(e))
        return None
    finally:
        # Clean up temp file
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def transcribe_from_bytes(
    audio_bytes: bytes,
    filename: str = "audio.ogg",
    language: str = "es",
) -> str | None:
    """
    Transcribe audio from raw bytes (useful for Telegram file downloads).
    """
    if not settings.openai_api_key:
        log.error("audio.transcription_skipped", reason="No OPENAI_API_KEY configured")
        return None

    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix or ".ogg", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        return await _whisper_transcribe(tmp_path, language)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def _whisper_transcribe(file_path: str, language: str = "es") -> str | None:
    """
    Call the OpenAI Whisper API to transcribe a local audio file.
    Uses the async OpenAI client via httpx directly to avoid blocking the event loop.
    """
    import asyncio

    def _sync_transcribe():
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        with open(file_path, "rb") as f:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
                response_format="text",
            )
        return response

    # Run in thread pool to avoid blocking the async event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _sync_transcribe)

    text = str(result).strip()
    print(f"🎙️ [WHISPER] Resultado crudo: {text[:50]}...")
    log.info("audio.transcribed", text_preview=text[:80])
    return text


def _content_type_to_ext(content_type: str) -> str:
    """Map MIME type to file extension."""
    mapping = {
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
        "audio/amr": ".amr",
    }
    for mime, ext in mapping.items():
        if mime in content_type:
            return ext
    return ".ogg"  # Default for WhatsApp
