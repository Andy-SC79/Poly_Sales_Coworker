from core.brain.prompts import get_prompt

def test_prompts():
    print("--- Test: Prompt para Cliente en Etapa de Objeción ---")
    awareness = "## Contexto Espacio-Temporal\n- Ubicación: Colombia\n- Hora: 7:32 PM\n- Recencia: Hace 2 horas"
    prompt = get_prompt(stage="objection", awareness_context=awareness, role="customer")
    
    # Check the system message
    system_msg = prompt.messages[0].prompt.template
    print(system_msg)

if __name__ == "__main__":
    test_prompts()
