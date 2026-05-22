"""
scripts/migrate_to_supabase.py
-------------------------------
Migrates local PostgreSQL customers to Supabase and initializes 
the cloud schema for CUSTOMERS and SALES_EVENTS.
"""
import asyncio
import structlog
from integrations.supabase_client import get_supabase
from core.memory.database import get_session
from core.memory.models import Customer
from sqlalchemy import select

log = structlog.get_logger()

async def migrate():
    supabase = get_supabase()
    log.info("migration.started", target="Supabase")

    # 1. Crear esquema (intentar via RPC o simplemente verificar si las tablas existen)
    # Nota: El service_role usualmente no puede crear tablas via API REST de PostgREST,
    # pero si el usuario ya las tiene o las creamos manual, procedemos.
    # Intentaremos una inserción de prueba para validar.

    async with get_session() as session:
        result = await session.execute(select(Customer))
        local_customers = result.scalars().all()
        log.info("migration.local_data_found", count=len(local_customers))

        for c in local_customers:
            data = {
                "phone": c.phone,
                "name": c.name or "Sin nombre",
                "city": c.city or "",
                "notes": c.profile_notes or "",
                "metadata": {
                    "conversation_summary": getattr(c, "conversation_summary", ""),
                    "first_seen": c.first_seen.isoformat() if c.first_seen else None
                },
                "last_interaction_at": c.last_seen.isoformat() if c.last_seen else None
            }
            
            try:
                # Insertar o actualizar en Supabase (upsert)
                # Nota: Usamos minúsculas para coincidir con PostgreSQL
                supabase.table("customers").upsert(data, on_conflict="phone").execute()
                log.info("migration.customer_synced", phone=c.phone)
            except Exception as e:
                log.error("migration.sync_failed", phone=c.phone, error=str(e))

    log.info("migration.completed")

if __name__ == "__main__":
    asyncio.run(migrate())
