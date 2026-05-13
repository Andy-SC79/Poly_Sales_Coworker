"""
core/brain/model_selector.py
-----------------------------
Dynamic model router. Chooses the best LLM based on the task complexity
and available providers. Centralizes all model instantiation.

Priority logic:
  - Vision / image analysis  → Gemini 2.0 Flash
  - Complex reasoning         → GPT-4o Mini
  - Simple / fast / offline   → Ollama (phi3)
"""
from functools import lru_cache
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

from config.settings import get_settings

settings = get_settings()

# Read from env — defaults to llama3:8b if not set
_OLLAMA_MODEL = getattr(settings, 'ollama_default_model', 'llama3:8b')

# ── Tool Definitions ──────────────────────────────────────────────────────────

web_search_tool = DuckDuckGoSearchRun(
    name="web_search",
    description=(
        "Busca información en internet sobre productos de la competencia, "
        "datos científicos de bienestar o noticias actuales. "
        "Úsalo solo para respaldar la venta o asesorar mejor al cliente. "
        "No lo uses para temas personales o ajenos al negocio."
    )
)

def get_model(task: str = "default", permissions: list[str] = None) -> BaseChatModel:
    """
    Return the appropriate LLM for the given task type, with tools bound if permitted.
    """
    model_instance = None
    
    # 1. Vision tasks — Prefer Gemini
    if task == "vision" and settings.google_api_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        model_instance = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=settings.google_api_key,
            temperature=0.7,
        )

    # 2. Primary / Production Default: GPT-4o Mini
    elif task in ["complex", "default"] and settings.openai_api_key:
        model_instance = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.openai_api_key,
            temperature=0.7,
            max_tokens=512,
        )

    # 3. Local / Offline — Use Ollama
    else:
        try:
            model_instance = ChatOllama(
                model=_OLLAMA_MODEL,
                base_url=settings.ollama_base_url,
                temperature=0.7,
            )
        except Exception:
            # Fallback to Gemini if everything else fails and key is there
            if settings.google_api_key:
                from langchain_google_genai import ChatGoogleGenerativeAI
                model_instance = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=settings.google_api_key,
                    temperature=0.7,
                )

    if not model_instance:
        raise ValueError("No LLM provider configured")

    # 4. Bind Tools based on permissions
    available_tools = []
    if permissions and "web_search" in permissions:
        available_tools.append(web_search_tool)
    
    if available_tools:
        # Note: Ollama binding might differ depending on version, 
        # but ChatOpenAI and ChatGoogleGenerativeAI support .bind_tools
        return model_instance.bind_tools(available_tools)
    
    return model_instance


@lru_cache(maxsize=4)
def get_cached_model(task: str = "default") -> BaseChatModel:
    """Cached version — reuse model instances for efficiency."""
    return get_model(task)
