"""
agent_insurance/run_tests_auto.py
Automated validation of Sura health prequalification scenarios.
"""
import asyncio
from langchain_core.messages import HumanMessage
from agent_insurance.agents import run_insurance_agent
from agent_insurance.flow import InsuranceState

async def run_scenario(name: str, inputs: list) -> dict:
    print(f"\n==================================================")
    print(f"[SCENARIO]: {name}")
    print(f"==================================================")
    
    state = {
        "messages": [],
        "channel": "whatsapp",
        "customer_id": "+573115551234",
        "stage": "greeting",
        "is_for_self": None,
        "caller_name": None,
        "candidate_relation": None,
        "candidate_name": None,
        "candidate_age": None,
        "candidate_has_eps": None,
        "candidate_eps": None,
        "is_qualified": None,
        "qualification_reason": None,
        "matched_product": None,
        "email": None,
        "phone": None,
        "appointment_status": "none",
        "appointment_date": None,
        "other_product_interest": None
    }
    
    # Initial turn (greeting response)
    state = await run_insurance_agent(state)
    print(f"Mateo: {state['messages'][-1].content}")
    print(f"  [etapa: {state['stage']}]")
    
    for i, user_text in enumerate(inputs):
        print(f"Usuario: {user_text}")
        state["messages"].append(HumanMessage(content=user_text))
        state = await run_insurance_agent(state)
        print(f"Mateo: {state['messages'][-1].content}")
        print(f"  [etapa: {state['stage']} | calif: {state.get('is_qualified')} | prod: {state.get('matched_product')}]")
        
    return state

async def main():
    # Scenario 1: Unqualified due to age >= 78
    s1 = await run_scenario("Candidato No Califica (Edad >= 78)", [
        "Hola, quiero cotizar un seguro para mi papá.",
        "Se llama Alberto y tiene 82 años.",
        "Sí, tiene EPS Sanitas contributiva."
    ])
    assert s1["is_qualified"] is False, "S1: Debería ser calificado=False"
    assert s1["stage"] == "unqualified", "S1: Debería terminar en unqualified"
    
    # Scenario 2: Qualified for Plan de Salud 60+ Sura
    s2 = await run_scenario("Califica para Plan 60+ Sura", [
        "Hola, busco seguro para mí.",
        "Soy María, tengo 64 años.",
        "Sí, tengo EPS Sanitas.",
        "Me interesa agendar la cita.",
        "Mi email es maria@gmail.com y celular es 3123456789"
    ])
    assert s2["is_qualified"] is True, "S2: Debería calificar"
    assert s2["matched_product"] == "Plan de Salud 60+ Sura", "S2: Producto incorrecto"
    assert s2["stage"] == "scheduling", "S2: Debería llegar a la etapa de scheduling"
    
    # Scenario 3: Qualified for Salud Para Todos Integral (PSI)
    s3 = await run_scenario("Califica para PSI (menor de 60, EPS Sura)", [
        "Hola, busco seguro para mí.",
        "Soy Andrés, tengo 35 años.",
        "Sí, estoy en EPS Sura."
    ])
    assert s3["is_qualified"] is True, "S3: Debería calificar"
    assert s3["matched_product"] == "Plan Salud Para Todos Integral (PSI)", "S3: Producto incorrecto"
    
    # Scenario 4: Other insurance products (Auto)
    s4 = await run_scenario("Interés en otros productos (Auto)", [
        "Hola, quiero cotizar un seguro para mi carro nuevo."
    ])
    assert s4["stage"] == "other_products", "S4: Debería redireccionar a other_products"
    
    # Scenario 5: Change of candidate mind (is_for_self change)
    s5 = await run_scenario("Cambio de opinión sobre el candidato", [
        "Hola, busco seguro para mí.",
        "Mejor quiero cotizar para mi papá Alberto.",
        "Tiene 64 años y está en EPS Sanitas."
    ])
    assert s5["is_for_self"] is False, "S5: Debería cambiar is_for_self a False"
    assert s5["candidate_name"] == "Alberto", "S5: Candidato debería ser Alberto"
    assert s5["is_qualified"] is True, "S5: Debería calificar"
    assert s5["matched_product"] == "Plan de Salud 60+ Sura", "S5: Debería calificar para plan 60+"
    
    print("\n>>> ¡Todos los escenarios automatizados pasaron las aserciones de validación con éxito!")

if __name__ == "__main__":
    asyncio.run(main())
