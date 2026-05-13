"""
config/settings.py
------------------
Central configuration powered by Pydantic Settings.
All values are read from environment variables or the .env file.
This is the SINGLE SOURCE OF TRUTH for all settings in the project.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # --- LLM Providers ---
    openai_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "llama3:8b"

    # --- LangSmith ---
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "poly-ai-coworker"

    # --- PostgreSQL ---
    database_url: str

    # --- Qdrant ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "product_catalog"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Twilio / WhatsApp ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""

    # --- Audio ---
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""

    # --- Integrations ---
    droppi_api_key: str = ""
    droppi_base_url: str = "https://api.dropi.co"

    # --- Security ---
    webhook_secret: str = "change-me-in-production"


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance — call this everywhere."""
    return Settings()
