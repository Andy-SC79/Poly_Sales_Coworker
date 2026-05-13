"""
core/memory/customer_repo.py
-----------------------------
Repository pattern for all customer-related DB operations.
Abstracts SQLAlchemy queries so agents don't touch the DB directly.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.models import Customer, Conversation, AnalyticsEvent

log = structlog.get_logger()


class CustomerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, phone: str) -> tuple[Customer, bool]:
        """
        Return existing customer or create a new one.
        Returns (customer, created: bool).
        """
        result = await self.session.execute(
            select(Customer).where(Customer.phone == phone)
        )
        customer = result.scalar_one_or_none()
        if customer:
            return customer, False

        customer = Customer(phone=phone)
        self.session.add(customer)
        await self.session.flush()
        log.info("customer.created", phone=phone)
        return customer, True

    async def update_profile(
        self,
        phone: str,
        name: str | None = None,
        role: str | None = None,
        role_metadata: dict | None = None,
        pain_points: list | None = None,
        profile_notes: str | None = None,
    ) -> None:
        """Update discovered customer/member data."""
        customer, _ = await self.get_or_create(phone)
        if name:
            customer.name = name
        if role:
            customer.role = role
        if role_metadata:
            existing = customer.role_metadata or {}
            customer.role_metadata = {**existing, **role_metadata}
        if pain_points:
            existing = customer.pain_points or []
            customer.pain_points = list(set(existing + pain_points))
        if profile_notes:
            customer.profile_notes = profile_notes
        await self.session.flush()
        log.info("customer.profile_updated", phone=phone, role=customer.role)

    async def get_profile(self, phone: str) -> dict | None:
        """Load profile for injection into state at session start."""
        result = await self.session.execute(
            select(Customer).where(Customer.phone == phone)
        )
        customer = result.scalar_one_or_none()
        if not customer:
            return None
        return {
            "id": customer.id,
            "name": customer.name,
            "role": customer.role,
            "role_metadata": customer.role_metadata or {},
            "city": customer.city,
            "pain_points": customer.pain_points or [],
            "profile_notes": customer.profile_notes,
            "first_seen": customer.first_seen.isoformat(),
        }

    async def log_event(
        self,
        phone: str,
        event_type: str,
        stage_from: str | None = None,
        stage_to: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a funnel analytics event."""
        customer, _ = await self.get_or_create(phone)
        event = AnalyticsEvent(
            customer_id=customer.id,
            event_type=event_type,
            stage_from=stage_from,
            stage_to=stage_to,
            event_meta=metadata,
        )
        self.session.add(event)
        await self.session.flush()
