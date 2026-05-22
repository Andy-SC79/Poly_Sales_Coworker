import asyncio
import structlog
from core.memory.database import get_session
from core.memory.customer_repo import CustomerRepo
from core.memory.models import Customer
from sqlalchemy import select
from core.brain.model_selector import get_model
from langchain_core.messages import HumanMessage

log = structlog.get_logger()

async def main():
    log.info("memory_cleanup.started")
    model = get_model()
    
    async with get_session() as session:
        # Buscar clientes con historiales muy largos
        result = await session.execute(select(Customer).where(Customer.conversation_summary.isnot(None)))
        customers = result.scalars().all()
        
        for customer in customers:
            summary = customer.conversation_summary
            if summary and len(summary) > 500: # Si es mayor a 500 caracteres, vale la pena resumir
                prompt = f"""
                Eres un optimizador de memoria CRM. A continuación tienes un historial de notas sobre un cliente.
                Toma TODA la información útil (datos personales, objeciones, pedidos hechos, productos de interés) 
                y condénsala en una lista MUY CORTA de viñetas, eliminando la redundancia.
                
                No pierdas datos duros (como 'tiene 2 hijos' o 'pidió 1 colágeno' o 'dirección: calle 10').
                Elimina frases repetitivas como 'El cliente está buscando...'.
                
                HISTORIAL ACTUAL:
                {summary}
                
                DEVUELVE ÚNICAMENTE LA LISTA OPTIMIZADA EN VIÑETAS (- ).
                """
                
                try:
                    res = await model.ainvoke([HumanMessage(content=prompt)])
                    optimized = res.content.strip()
                    
                    if optimized and len(optimized) < len(summary):
                        customer.conversation_summary = optimized
                        log.info("memory_cleanup.optimized", phone=customer.phone, old_len=len(summary), new_len=len(optimized))
                except Exception as e:
                    log.error("memory_cleanup.error", phone=customer.phone, error=str(e))
                    
        await session.commit()
    log.info("memory_cleanup.finished")

if __name__ == "__main__":
    asyncio.run(main())
