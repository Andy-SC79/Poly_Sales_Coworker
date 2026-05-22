"""
core/brain/state.py
-------------------
Central state definition for the LangGraph agent graph.
This TypedDict is the single data structure passed between ALL agents.
Every agent reads from it and writes back to it.
"""
from datetime import datetime
from typing import Annotated, Literal
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ── Sales pipeline stages ────────────────────────────────────────────────────
SalesStage = Literal[
    "greeting",       # First contact / re-engagement
    "discovery",      # Uncovering needs / pain points
    "presentation",   # Showing product value
    "objection",      # Handling doubts or pushback
    "closing",        # Collecting order details
    "post_sale",      # Order confirmed — tracking & support
    "complaint",      # Handling issues
    "admin",          # Telegram admin command (not a customer)
    "escalation",     # Human-in-the-loop — waiting for owner response
    "silence",        # Shadowing mode — observe but do not reply
]


# ── Channel source ────────────────────────────────────────────────────────────
ChannelSource = Literal["whatsapp", "telegram", "unknown"]


# ── Main Graph State ──────────────────────────────────────────────────────────
class PolyState(TypedDict):
    # --- Conversation ---
    messages: Annotated[list[BaseMessage], add_messages]  # Full conversation history
    channel: ChannelSource                                 # Where the message came from
    customer_id: str                                       # Phone number or Telegram chat ID

    # --- Sales Pipeline ---
    stage: SalesStage                                      # Current stage of the funnel
    customer_name: str | None                              # Extracted name
    city: str | None                                       # Extracted city
    email: str | None                                      # Extracted email
    address: str | None                                    # Extracted address
    alternative_phone: str | None                          # Extracted alternative phone
    conversation_summary: str | None                       # Discovered profile summary (needs, interests, etc)
    discovery_notes: str | None                            # Temporary notes from profiler (e.g. fake name warning)
    recommended_products: list[dict]                       # RAG results

    # --- Closing ---
    order_data: dict | None                                # JSON order being built
    current_order_id: str | None                           # ID of the submitted order in Supabase

    # --- Admin & Coworker ---
    is_admin: bool                                         # True if message is from owner via Telegram
    is_paused: bool = False                                # True if a human is in control
    escalation_pending: bool                               # True if Poly is waiting for human answer

    # --- Metadata ---
    long_term_profile: dict | None                         # Loaded from PostgreSQL at session start
    role: str                                              # customer | owner | employee | agent
    role_metadata: dict                                    # Specific settings for the role
    admin_notes: str | None                                # Instructions or goals from the owner
    
    # --- Spatiotemporal & Security ---
    last_interaction_at: datetime | None                   # Timestamp of the previous message
    permissions: list[str]                                 # List of allowed actions (e.g., ["web_search"])
    model_provider: str                                    # default | ollama | openai | google
