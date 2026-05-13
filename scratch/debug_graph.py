
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from core.brain.graph import get_poly_graph
from langchain_core.messages import HumanMessage
from core.brain.state import PolyState

async def test_invoke():
    print("--- Iniciando prueba interna del Cerebro ---")
    try:
        graph = await get_poly_graph()
        
        state = {
            "messages": [HumanMessage(content="Hola Poly, prueba de sistema")],
            "channel": "debug",
            "customer_id": "test_user",
            "stage": "greeting",
            "is_admin": False,
            "customer_name": None,
            "pain_points": [],
            "recommended_products": [],
            "order_data": None,
            "escalation_pending": False,
            "long_term_profile": None,
        }
        
        config = {"configurable": {"thread_id": "test_thread"}}
        
        print("--- Invocando al grafo ---")
        result = await graph.ainvoke(state, config=config)
        
        print("\nRESULTADO:")
        print(result["messages"][-1].content)
        
    except Exception as e:
        print("\nERROR DETECTADO:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_invoke())
