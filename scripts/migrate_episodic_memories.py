"""
scripts/migrate_episodic_memories.py
-------------------------------------
Script de migración única.
Lee el 'conversation_summary' existente de todos los clientes en la base de datos (Supabase)
y vectoriza cada viñeta (bullet point) en la nueva tabla 'episodic_memories' de pgvector.
"""

import asyncio
import structlog
import sys
import os
from pathlib import Path

# Add project root to python path so we can import local packages
sys.path.append(str(Path(__file__).parent.parent))

from integrations.supabase_client import get_supabase
from core.knowledge.catalog import index_episodic_memory

log = structlog.get_logger()

async def migrate_memories():
    log.info("migration.start", message="Iniciando migración de recuerdos existentes a vectores...")
    supabase = get_supabase()
    
    # Obtener clientes con historial conversacional
    response = supabase.table("customers").select("phone, conversation_summary").neq("conversation_summary", "").execute()
    customers = response.data
    
    if not customers:
        log.info("migration.idle", message="No hay recuerdos crudos para migrar.")
        return
        
    log.info("migration.processing", count=len(customers))
    
    migrated_count = 0
    for customer in customers:
        phone = customer.get("phone")
        raw_summary = customer.get("conversation_summary")
        
        if not raw_summary:
            continue
            
        # El historial actual está guardado con viñetas "- "
        # Dividimos el texto para indexar cada recuerdo como un vector independiente.
        bullets = [b.strip() for b in raw_summary.split("\n") if b.strip().startswith("-")]
        
        for bullet in bullets:
            # Quitamos el guion inicial
            clean_fact = bullet.lstrip("- ").strip()
            if clean_fact:
                await index_episodic_memory(phone, clean_fact)
                migrated_count += 1
                
        log.info("migration.customer_done", phone=phone, memories_indexed=len(bullets))
            
    log.info("migration.complete", total_memories_vectorized=migrated_count)

if __name__ == "__main__":
    asyncio.run(migrate_memories())
