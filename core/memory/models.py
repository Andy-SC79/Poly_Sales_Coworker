"""
core/memory/models.py
---------------------
SQLAlchemy async ORM models for PostgreSQL.
Tables:
  - customers      : Long-term client profile (CRM)
  - conversations  : Session metadata per customer
  - orders         : Confirmed sales (JSON payload + Droppi status)
  - events         : Analytics events (stage changes, closures, objections)
  - complaints     : Complaint & claim tickets
"""
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, JSON, DateTime, Boolean, Integer,
    ForeignKey, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ─────────────────────────────────────────────────────────────────────

class OrderStatus(str, enum.Enum):
    pending   = "pending"
    confirmed = "confirmed"
    shipped   = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class ComplaintStatus(str, enum.Enum):
    open       = "open"
    in_review  = "in_review"
    resolved   = "resolved"
    closed     = "closed"


# ── Models ────────────────────────────────────────────────────────────────────

class Customer(Base):
    """Long-term client profile — the CRM."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(100))

    # Corporate Role & Identity
    role: Mapped[str] = mapped_column(String(20), default="customer") # customer | owner | employee | agent
    role_metadata: Mapped[dict | None] = mapped_column(JSON, default=dict) # Role-specific config

    # Discovered profile (from discovery agent)
    conversation_summary: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(100))
    address: Mapped[str | None] = mapped_column(Text)
    alternative_phone: Mapped[str | None] = mapped_column(String(20))
    profile_notes: Mapped[str | None] = mapped_column(Text)  # AI-generated summary / Owner prefs

    # Lifecycle
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="customer")
    events: Mapped[list["AnalyticsEvent"]] = relationship(back_populates="customer")


class Conversation(Base):
    """Session metadata — one row per chat session."""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20))     # whatsapp | telegram
    thread_id: Mapped[str] = mapped_column(String(80), unique=True)  # LangGraph thread
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_stage: Mapped[str | None] = mapped_column(String(30))
    summary: Mapped[str | None] = mapped_column(Text)    # AI-generated session summary

    customer: Mapped["Customer"] = relationship(back_populates="conversations")


class Order(Base):
    """Confirmed sale ready for fulfillment (Droppi or manual)."""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_payload: Mapped[dict] = mapped_column(JSON)       # Full JSON with products, address, etc.
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus), default=OrderStatus.pending
    )
    droppi_order_id: Mapped[str | None] = mapped_column(String(80))
    tracking_number: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    customer: Mapped["Customer"] = relationship(back_populates="orders")


class Complaint(Base):
    """Complaint and claim ticket."""
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[ComplaintStatus] = mapped_column(
        SAEnum(ComplaintStatus), default=ComplaintStatus.open
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    customer: Mapped["Customer"] = relationship(back_populates="complaints")


class AnalyticsEvent(Base):
    """Funnel analytics — one row per meaningful agent transition."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(60))   # e.g. "stage_change", "sale_closed"
    stage_from: Mapped[str | None] = mapped_column(String(30))
    stage_to: Mapped[str | None] = mapped_column(String(30))
    event_meta: Mapped[dict | None] = mapped_column(JSON)  # renamed from 'metadata' (SQLAlchemy reserved)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    customer: Mapped["Customer"] = relationship(back_populates="events")
