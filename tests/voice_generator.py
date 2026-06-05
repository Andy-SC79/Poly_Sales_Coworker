# pip install python-dotenv requests

import os
import requests
from dotenv import load_dotenv

# ============================================
# CONFIGURACIÓN
# ============================================

# Crea un archivo .env con:
# ELEVENLABS_API_KEY=tu_api_key_aqui

load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")

VOICE_ID = "8mBRP99B2Ng2QwsJMFQl"

TEXT = """
A veces la vida se llena de tantas cosas…
y sin darnos cuenta,
dejamos lo importante para después…

Hubo un tiempo en que ellos lo eran todo…

y ahora, entre días que pasan uno tras otro,
siguen esperando algo muy simple…

que alguien llegue… y esté.

y al final, no hace falta nada más
"""

# ============================================
# API ELEVENLABS
# ============================================

URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

HEADERS = {
    "xi-api-key": API_KEY,
    "Content-Type": "application/json",
}

PAYLOAD = {
    "text": TEXT,
    "model_id": "eleven_multilingual_v2",
    "voice_settings": {
        "stability": 0.45,
        "similarity_boost": 0.85,
        "style": 0.35,
        "use_speaker_boost": True
    }
}

# ============================================
# GENERAR AUDIO
# ============================================

print("Enviando solicitud a ElevenLabs...")
response = requests.post(URL, json=PAYLOAD, headers=HEADERS)

if response.status_code == 200:
    OUTPUT_FILE = "narracion_emotiva.mp3"
    
    with open(OUTPUT_FILE, "wb") as f:
        f.write(response.content)
    
    print(f"✅ Audio generado correctamente: {OUTPUT_FILE}")
    print(f"📁 Ubicación: {os.path.abspath(OUTPUT_FILE)}")
    print(f"📊 Tamaño: {len(response.content)} bytes")
else:
    print(f"❌ Error: {response.status_code}")
    print(response.text)