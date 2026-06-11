"""
core/memory/customer_repo.py
-----------------------------
Repository pattern for all customer-related CRM operations.
This implementation is Supabase-first and uses Supabase as the single source of truth.
"""
import structlog
from datetime import datetime, timezone

from config.db_schema import field as schema_field, table as schema_table
from integrations.supabase_client import get_supabase

log = structlog.get_logger()

class CustomerRepo:
    def __init__(self):
        self.supabase = get_supabase()

    def _normalize_phone(self, phone: str) -> str:
        """Limpia el número para evitar duplicados (ej: +57300 -> 300)."""
        if not phone:
            return ""
        clean = "".join(filter(str.isdigit, phone))
        if clean.startswith("57") and len(clean) == 12:
            return clean[2:]
        return clean

    def _record_to_profile(self, record: dict) -> dict:
        """Convert a Supabase customer record into the profile shape used by Poly."""
        if not record:
            return {}

        metadata = record.get(schema_field("customer", "metadata"), {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}

        return {
            "phone": record.get(schema_field("customer", "phone")),
            "name": record.get(schema_field("customer", "name")),
            "city": record.get(schema_field("customer", "city")),
            "conversation_summary": record.get(schema_field("customer", "conversation_summary"), ""),
            "profile_notes": record.get(schema_field("customer", "notes")),
            "role": str(metadata.get("role", "customer")),
            "role_metadata": metadata.get("role_metadata", {}),
            "email": record.get(schema_field("customer", "email")),
            "address": record.get(schema_field("customer", "address")),
            "alternative_phone": record.get(schema_field("customer", "alternative_phone")),
            "metadata": metadata,
        }

    async def get_profile(self, phone: str) -> dict | None:
        """Get customer profile summary for LLM context from Supabase."""
        phone = self._normalize_phone(phone)
        if not phone:
            return None

        try:
            customers_table = schema_table("customers")
            phone_field = schema_field("customer", "phone")
            res = self.supabase.table(customers_table).select("*").eq(phone_field, phone).limit(1).execute()
            if res.data:
                return self._record_to_profile(res.data[0])
        except Exception as e:
            log.warning("customer.supabase_read_failed", error=str(e), phone=phone)
        return None

    async def get_or_create(self, phone: str) -> tuple[dict, bool]:
        """Return existing customer profile or create a new one in Supabase."""
        phone = self._normalize_phone(phone)
        if not phone:
            return {}, True

        customers_table = schema_table("customers")
        phone_field = schema_field("customer", "phone")
        try:
            res = self.supabase.table(customers_table).select("*").eq(phone_field, phone).limit(1).execute()
            if res.data:
                return self._record_to_profile(res.data[0]), False

            payload = {
                phone_field: phone,
                schema_field("customer", "name"): "Sin nombre",
                schema_field("customer", "city"): "",
                schema_field("customer", "notes"): "",
                schema_field("customer", "conversation_summary"): "",
                schema_field("customer", "metadata"): {"role": "customer"},
                schema_field("customer", "last_interaction_at"): datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table(customers_table).insert(payload).execute()
            return self._record_to_profile(payload), True
        except Exception as e:
            log.warning("customer.supabase_create_failed", error=str(e), phone=phone)
            return {}, True

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
        """Update customer profile data in Supabase."""
        phone = self._normalize_phone(phone)
        if not phone:
            raise ValueError("Phone is required")

        current = await self.get_profile(phone) or {}
        metadata = current.get("metadata", {}) or {}
        if role is not None:
            metadata["role"] = role
        if role_metadata is not None:
            metadata["role_metadata"] = role_metadata

        data = {
            schema_field("customer", "phone"): phone,
            schema_field("customer", "name"): name if name is not None else current.get("name", "Sin nombre"),
            schema_field("customer", "city"): city if city is not None else current.get("city", ""),
            schema_field("customer", "notes"): profile_notes if profile_notes is not None else current.get("profile_notes", ""),
            schema_field("customer", "conversation_summary"): conversation_summary if conversation_summary is not None else current.get("conversation_summary", ""),
            schema_field("customer", "metadata"): metadata,
            schema_field("customer", "last_interaction_at"): datetime.now(timezone.utc).isoformat(),
        }

        if email is not None:
            data[schema_field("customer", "email")] = email
        elif current.get("email") is not None:
            data[schema_field("customer", "email")] = current.get("email")

        if address is not None:
            data[schema_field("customer", "address")] = address
        elif current.get("address") is not None:
            data[schema_field("customer", "address")] = current.get("address")

        if alternative_phone is not None:
            data[schema_field("customer", "alternative_phone")] = alternative_phone
        elif current.get("alternative_phone") is not None:
            data[schema_field("customer", "alternative_phone")] = current.get("alternative_phone")

        if department is not None:
            data["department"] = department

        try:
            customers_table = schema_table("customers")
            self.supabase.table(customers_table).upsert(data, on_conflict=schema_field("customer", "phone")).execute()
            log.info("customer.profile_updated", phone=phone)
        except Exception as e:
            log.warning("customer.supabase_update_failed", error=str(e), phone=phone)

    async def log_event(
        self,
        phone: str,
        event_type: str,
        product_name: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a sales event directly in Supabase."""
        phone = self._normalize_phone(phone)
        if not phone:
            return

        try:
            sales_events_table = schema_table("sales_events")
            payload = {
                schema_field("customer", "phone"): phone,
                "event_type": event_type,
                "metadata": metadata or {},
            }
            if product_name:
                payload["product_name"] = product_name
            self.supabase.table(sales_events_table).insert(payload).execute()
        except Exception as e:
            log.warning("event.supabase_insert_failed", error=str(e), phone=phone)
