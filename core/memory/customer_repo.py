"""
core/memory/customer_repo.py
-----------------------------
Repository pattern for all customer-related DB operations.
Syncs data on Supabase Cloud.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from core.memory.models import Customer, Conversation, AnalyticsEvent
from integrations.supabase_client import get_supabase

log = structlog.get_logger()

class CustomerRepo:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.supabase = get_supabase()

    def _normalize_phone(self, phone: str) -> str:
        """Limpia el número para evitar duplicados (ej: +57300 -> 300)."""
        if not phone: return ""
        # Eliminar todo lo que no sea número
        clean = "".join(filter(str.isdigit, phone))
        # Si empieza por 57 y tiene 12 dígitos, quitar el 57
        if clean.startswith("57") and len(clean) == 12:
            return clean[2:]
        return clean

    async def get_profile(self, phone: str) -> dict | None:
        """Get customer profile summary for LLM context."""
        customer, _ = await self.get_or_create(phone)
        if not customer:
            return None
            
        return {
            "name": customer.name,
            "city": customer.city,
            "conversation_summary": customer.conversation_summary or "",
            "profile_notes": customer.profile_notes,
            "role": customer.role,
            "role_metadata": customer.role_metadata or {},
            "email": customer.email,
            "address": customer.address,
            "alternative_phone": customer.alternative_phone,
        }

    async def get_or_create(self, phone: str) -> tuple[Customer, bool]:
        """
        Return existing customer or create a new one.
        Syncs with Supabase if missing locally.
        """
        phone = self._normalize_phone(phone)
        # 1. Local check
        result = await self.session.execute(
            select(Customer).where(Customer.phone == phone)
        )
        customer = result.scalar_one_or_none()
        
        if customer:
            return customer, False

        # 2. Supabase check (Sync back if exists there but not locally)
        try:
            res = self.supabase.table("customers").select("*").eq("phone", phone).execute()
            if res.data:
                s_cust = res.data[0]
                customer = Customer(
                    phone=phone,
                    name=s_cust.get("name"),
                    city=s_cust.get("city"),
                    profile_notes=s_cust.get("notes")
                )
                self.session.add(customer)
                await self.session.flush()
                return customer, False
        except Exception as e:
            log.warning("customer.supabase_sync_failed", error=str(e))

        # 3. Create new if nowhere
        customer = Customer(phone=phone)
        self.session.add(customer)
        await self.session.flush()
        
        # Sync to Supabase
        self._sync_to_supabase(customer)
        
        log.info("customer.created", phone=phone)
        return customer, True

    async def update_profile(
        self,
        phone: str,
        name: str | None = None,
        city: str | None = None,
        role: str | None = None,
        role_metadata: dict | None = None,
        conversation_summary: str | None = None,
        profile_notes: str | None = None,
        email: str | None = None,
        address: str | None = None,
        alternative_phone: str | None = None,
        department: str | None = None,
    ) -> None:
        """Update discovered customer data and sync to Cloud."""
        customer, _ = await self.get_or_create(phone)
        if name: customer.name = name
        if city: customer.city = city
        if role: customer.role = role
        if profile_notes: customer.profile_notes = profile_notes
        if email: customer.email = email
        if address: customer.address = address
        if alternative_phone: customer.alternative_phone = alternative_phone
        
        if conversation_summary:
            customer.conversation_summary = conversation_summary
            
        await self.session.flush()
        
        # Cloud Sync
        cloud_data = {
            "name": customer.name,
            "city": customer.city,
            "notes": customer.profile_notes,
            "conversation_summary": customer.conversation_summary,
            "metadata": {
                "role": customer.role
            }
        }
        if email: cloud_data["email"] = email
        if address: cloud_data["address"] = address
        if alternative_phone: cloud_data["alternative_phone"] = alternative_phone
        if department: cloud_data["department"] = department

        self._sync_to_supabase(customer, extra_data=cloud_data)
        log.info("customer.profile_updated", phone=phone)

    async def log_event(
        self,
        phone: str,
        event_type: str,
        product_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a sales event in local DB and Supabase Sales Events."""
        customer, _ = await self.get_or_create(phone)
        
        # 1. Local Event
        event = AnalyticsEvent(
            customer_id=customer.id,
            event_type=event_type,
            event_meta=metadata,
        )
        self.session.add(event)
        await self.session.flush()

        # 2. Supabase Sales Event
        try:
            self.supabase.table("sales_events").insert({
                "customer_phone": phone,
                "event_type": event_type,
                "product_name": product_name,
                "metadata": metadata or {}
            }).execute()
        except Exception as e:
            log.warning("event.supabase_sync_failed", error=str(e))

    def _sync_to_supabase(self, customer: Customer, extra_data: dict = None):
        """Helper to push local state to Supabase."""
        try:
            data = {
                "phone": customer.phone,
                "name": customer.name or "Sin nombre",
                "city": customer.city or "",
                "notes": customer.profile_notes or "",
                "last_interaction_at": datetime.now(timezone.utc).isoformat()
            }
            if extra_data:
                data.update(extra_data)
                
            self.supabase.table("customers").upsert(data, on_conflict="phone").execute()
        except Exception as e:
            log.warning("customer.sync_to_cloud_failed", error=str(e))
