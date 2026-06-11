# Poly AI Coworker — Asistente de Ventas de Alto Rendimiento

Poly es un agente de IA autónomo para ventas en WhatsApp y Telegram. Está diseñado para acompañar al cliente desde la consulta inicial hasta el cierre de pedido y el seguimiento, con memoria conversacional, RAG y un hub administrativo en Telegram.

## 🚀 Qué incluye este repositorio

- `api/`: endpoints HTTP y webhooks.
- `channels/`: adaptadores para WhatsApp (Twilio) y Telegram.
- `core/`: grafo de estados, agentes, selector de modelos y herramientas.
- `config/`: personalidad, prompts y settings centralizados.
- `integrations/`: Supabase, Droppi y almacenamiento vectorial.
- `workers/` y `scripts/`: tareas de mantenimiento y soporte.

## ⚙️ Requisitos

- Python 3.11+
- Poetry (recomendado)
- Claves API de OpenAI / Google / Twilio / Telegram / Supabase / ElevenLabs (según el flujo que uses)
- Docker / Docker Compose opcional para servicios locales

## 📦 Instalación

```bash
git clone <repo-url>
cd sales-agent-ve
poetry install
cp .env.example .env
```

Si prefieres usar `pip` en vez de Poetry:

```bash
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

## 🔧 Configuración

1. Copia `./.env.example` a `./.env`.
2. Completa tus credenciales reales.
3. No subas `./.env` al repositorio; está ignorado por `.gitignore`.

## ▶️ Ejecución local

```bash
poetry run python telegram_runner.py
poetry run python poly_chat.py
```

Para servicios compatibles con Docker:

```bash
docker-compose up -d
```

## 🧩 Archivos importantes

- `config/settings.py`
- `config/db_schema.yaml`
- `config/personality.yaml`
- `core/brain/`
- `integrations/`
- `channels/`

## 🛡️ Seguridad

- Usa siempre `.env.example` como plantilla.
- Nunca compartas secretos ni claves reales en git.
- Si agregas un proveedor nuevo, actualiza `.env.example`.

---

*Este repositorio está listo para clonar y montar en un nuevo repositorio limpio.*
