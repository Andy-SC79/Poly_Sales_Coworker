"""
core/brain/awareness.py
------------------------
Provides spatiotemporal context for Poly. 
Infers location from phone numbers and calculates time elapsed between interactions.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Mapping of country codes to friendly names and timezones
# Focused on Spanish-speaking countries as per project context
_COUNTRY_MAP = {
    "57": {"name": "Colombia", "tz": "America/Bogota"},
    "34": {"name": "España", "tz": "Europe/Madrid"},
    "52": {"name": "México", "tz": "America/Mexico_City"},
    "54": {"name": "Argentina", "tz": "America/Argentina/Buenos_Aires"},
    "56": {"name": "Chile", "tz": "America/Santiago"},
    "51": {"name": "Perú", "tz": "America/Lima"},
    "58": {"name": "Venezuela", "tz": "America/Caracas"},
    "593": {"name": "Ecuador", "tz": "America/Guayaquil"},
    "502": {"name": "Guatemala", "tz": "America/Guatemala"},
    "506": {"name": "Costa Rica", "tz": "America/Costa_Rica"},
    "507": {"name": "Panamá", "tz": "America/Panama"},
    "1": {"name": "USA", "tz": "America/New_York"}, # Default to NY for +1
}

def get_context_awareness(customer_id: str, last_interaction_at: datetime = None) -> str:
    """
    Generate a natural language block describing the current time and location context.
    
    Args:
        customer_id: Usually a phone number (e.g. "+57300...") or telegram ID.
        last_interaction_at: The timestamp of the last message in this thread.
    """
    now_utc = datetime.now(timezone.utc)
    
    # 1. Infer Location
    country_name = "desconocido"
    local_time_str = now_utc.strftime("%H:%M")
    
    clean_id = customer_id.replace("+", "").replace(" ", "")
    matched_tz = "UTC"
    
    # Try to match prefix (longest first)
    for prefix in sorted(_COUNTRY_MAP.keys(), key=len, reverse=True):
        if clean_id.startswith(prefix):
            info = _COUNTRY_MAP[prefix]
            country_name = info["name"]
            matched_tz = info["tz"]
            # Convert UTC to local time
            try:
                local_now = now_utc.astimezone(ZoneInfo(matched_tz))
                local_time_str = local_now.strftime("%I:%M %p")
            except Exception:
                local_time_str = now_utc.strftime("%H:%M")
            break

    # 2. Calculate Time Delta
    recency_msg = ""
    if last_interaction_at:
        # Ensure last_interaction_at is timezone aware
        if last_interaction_at.tzinfo is None:
            last_interaction_at = last_interaction_at.replace(tzinfo=timezone.utc)
            
        diff = now_utc - last_interaction_at
        seconds = diff.total_seconds()
        
        if seconds < 60:
            recency_msg = "Acabas de hablar con el usuario hace unos segundos."
        elif seconds < 3600:
            mins = int(seconds // 60)
            recency_msg = f"Tu última interacción fue hace {mins} minutos."
        elif seconds < 86400:
            hours = int(seconds // 3600)
            recency_msg = f"Han pasado {hours} horas desde que hablaron por última vez hoy."
        else:
            days = int(seconds // 86400)
            recency_msg = f"Han pasado {days} días desde su última conversación."

    # 3. Build Block
    day_name = now_utc.strftime("%A")
    # Simple Spanish translation for days
    days_es = {
        "Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles",
        "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo"
    }
    day_es = days_es.get(day_name, day_name)
    
    block = (
        f"## Contexto Espacio-Temporal\n"
        f"- Ubicación probable del cliente: {country_name}\n"
        f"- Hora local del cliente ({matched_tz}): {local_time_str} ({day_es})\n"
        f"- Recencia: {recency_msg if recency_msg else 'Es el primer contacto o ha pasado mucho tiempo.'}\n"
    )
    
    return block
