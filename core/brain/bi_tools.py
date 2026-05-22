"""
core/brain/bi_tools.py
-----------------------
Business Intelligence tools for Poly.
Allows the agent to query and analyze sales data, customer behavior, 
and performance metrics directly from Supabase.
"""
import structlog
from integrations.supabase_client import get_supabase
from core.brain.model_selector import get_model

log = structlog.get_logger()

async def query_business_intelligence(question: str):
    """
    Realiza un análisis profundo de los datos de negocio (Ventas, Clientes, Eventos).
    Puede responder preguntas sobre tendencias, totales, comparativas y comportamiento.
    """
    supabase = get_supabase()
    
    # 1. Usar un modelo para decidir qué tablas consultar
    planner_prompt = f"""
Eres la Analista de Datos de Vital Energy Shop. Tu misión es traducir una pregunta del dueño en una estrategia de consulta.
TABLAS DISPONIBLES EN SUPABASE:
- customers: [phone, name, city, email, notes, last_interaction_at]
- ORDERS: [todas las columnas de pedidos, incluyendo ID, Cliente, Producto, Tracking Number, Status, Notas, etc.]
- sales_events: [customer_phone, event_type, product_name, created_at]

PREGUNTA DEL DUEÑO: "{question}"

Responde con una estrategia clara: qué tablas mirarás y qué cálculos harás.
"""
    model = get_model("default")
    strategy = await model.ainvoke(planner_prompt)
    
    log.info("bi.planner", question=question, strategy=strategy.content[:100])

    # 2. Ejecutar consultas según la pregunta (Lógica flexible simplificada)
    # En una versión avanzada usaríamos Text-to-SQL, aquí haremos consultas clave:
    
    results = {}
    
    try:
        if "vend" in question.lower() or "venta" in question.lower() or "pedido" in question.lower():
            # Consulta de ventas (Cruda y completa)
            res = supabase.table("ORDERS").select("*").order("Timestamp", desc=True).limit(100).execute()
            results["ORDERS"] = res.data
        
        if "client" in question.lower() or "quien" in question.lower():
            # Consulta de clientes
            res = supabase.table("customers").select("*").order("last_interaction_at", desc=True).limit(50).execute()
            results["customers"] = res.data
            
        if "objecion" in question.lower() or "evento" in question.lower():
            # Consulta de eventos
            res = supabase.table("sales_events").select("*").limit(50).execute()
            results["events"] = res.data

        # 3. Sintetizar la respuesta final con el LLM
        analysis_prompt = f"""
Basándote en los siguientes datos de Supabase, responde a la pregunta del dueño con precisión y profesionalismo.
DATOS RECUPERADOS: {str(results)[:2000]} # Limitamos para evitar saturar el contexto

PREGUNTA: "{question}"
ESTRATEGIA INICIAL: {strategy.content}

Instrucciones:
- Sé específico (da números si los hay).
- Si no hay datos suficientes, admítelo.
- Sugiere una acción basada en los datos.
"""
        final_answer = await model.ainvoke(analysis_prompt)
        return final_answer.content

    except Exception as e:
        log.error("bi.query_failed", error=str(e))
        return f"Lo siento, tuve un problema al consultar los datos: {str(e)}"
