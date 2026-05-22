"""
scripts/sleep_compaction.py
----------------------------
"Modo Sueño" de Poly.
Este script se ejecuta asíncronamente o como un Cron Job nocturno.
Recorre todos los clientes que tuvieron interacciones recientes (que tienen datos en conversation_summary),
y utiliza un LLM para condensar sus notas crudas en un Perfil Base ultra-denso (profile_notes).
Una vez condensado, limpia el conversation_summary crudo.
"""

import asyncio
import structlog
import sys
import os
from pathlib import Path

# Add project root to python path so we can import local packages
sys.path.append(str(Path(__file__).parent.parent))

from integrations.supabase_client import get_supabase
from core.brain.model_selector import get_model
from pydantic import BaseModel, Field

log = structlog.get_logger()

class CondensedProfile(BaseModel):
    condensed_notes: str = Field(description="Resumen ultra-denso e impersonal de todo el perfil del cliente (dolores, gustos, métodos de pago preferidos, profesión, etc.). Combina la información previa con la nueva. Máximo 100 palabras.")

async def sleep_compaction():
    log.info("sleep.start", message="Iniciando el ciclo de sueño y consolidación de memoria...")
    supabase = get_supabase()
    
    # Obtener clientes que necesitan consolidación
    response = supabase.table("customers").select("*").neq("conversation_summary", "").execute()
    customers = response.data
    
    if not customers:
        log.info("sleep.idle", message="No hay clientes para consolidar hoy. Poly sigue durmiendo.")
        return
        
    log.info("sleep.processing", count=len(customers))
    
    model = get_model()
    structured_llm = model.with_structured_output(CondensedProfile)
    
    for customer in customers:
        phone = customer.get("phone")
        old_notes = customer.get("notes") or "Sin perfil base previo."
        raw_summary = customer.get("conversation_summary") or ""
        
        prompt = f"""
        Eres el subsistema de consolidación de memoria a largo plazo.
        
        INFORMACIÓN PREVIA DEL CLIENTE:
        {old_notes}
        
        NUEVAS INTERACCIONES (Crudas):
        {raw_summary}
        
        TAREA:
        Toma la información previa y las nuevas interacciones, y re-escribe un ÚNICO perfil base consolidado.
        Debe ser extremadamente conciso, impersonal y directo. 
        Ejemplo de formato: "Sufre de artritis. Prefiere contraentrega. Trabaja de noche. Tiene una hija llamada Sofia."
        No pierdas detalles importantes, pero elimina toda la verbosidad de las interacciones crudas.
        """
        
        try:
            result = await structured_llm.ainvoke(prompt)
            new_notes = result.condensed_notes
            
            # Actualizar en Supabase
            supabase.table("customers").update({
                "notes": new_notes,
                "conversation_summary": "" # Limpiamos el caché crudo
            }).eq("phone", phone).execute()
            
            log.info("sleep.customer_compacted", phone=phone)
            
        except Exception as e:
            log.error("sleep.compaction_failed", phone=phone, error=str(e))
            
    log.info("sleep.complete", message="Ciclo de sueño completado. Memorias consolidadas.")

if __name__ == "__main__":
    asyncio.run(sleep_compaction())
