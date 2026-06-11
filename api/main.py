"""
api/main.py
-----------
Clean FastAPI entry point for the Poly AI Coworker.
All heavy logic is delegated to the appropriate channel handlers.
"""
import asyncio
import sys

# Windows compatibility fix for asyncio event loop policy
if sys.platform == "win32":
    import selectors
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings

settings = get_settings()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    log.info("poly.startup", env=settings.app_env)

    from core.brain.graph import get_poly_graph
    import core.brain.graph as graph_module

    graph_module._poly_graph = await get_poly_graph()
    log.info("poly.graph_ready", checkpointer="MemorySaver")

    yield
    log.info("poly.shutdown")


app = FastAPI(
    title="Poly AI Coworker",
    description="Multi-Agent Sales & Support System — Vital Energy Shop",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "agent": "Poly", "env": settings.app_env}


# Channel Routers
from channels.whatsapp import router as whatsapp_router

# New canonical paths
app.include_router(whatsapp_router, prefix="/channels/whatsapp", tags=["WhatsApp"])

# Legacy path — keeps existing Twilio webhook config working without changes
app.include_router(whatsapp_router, prefix="", tags=["WhatsApp (legacy path)"])
