
import asyncio
import structlog
from core.brain.model_selector import get_model
from core.brain.state import SalesStage

async def test_tools():
    print("--- Diagnóstico de Herramientas de Poly ---")
    
    # Test 1: Permisos de Cliente en Closing
    print("\n[Test 1] Permisos de Cliente (Closing):")
    model = get_model(permissions=["verify_fact", "submit_order"])
    if hasattr(model, "kwargs") and "tools" in model.kwargs:
        tools = [t.get("function", {}).get("name") for t in model.kwargs["tools"]]
        print(f"Herramientas vinculadas: {tools}")
    else:
        print("No se vincularon herramientas.")

    # Test 2: Permisos de Admin
    print("\n[Test 2] Permisos de Admin:")
    model = get_model(permissions=["verify_fact", "web_search", "update_catalog", "search_external_catalog"])
    if hasattr(model, "kwargs") and "tools" in model.kwargs:
        tools = [t.get("function", {}).get("name") for t in model.kwargs["tools"]]
        print(f"Herramientas vinculadas: {tools}")
    else:
        print("No se vincularon herramientas.")

if __name__ == "__main__":
    asyncio.run(test_tools())
