"""
core/brain/prompts.py
---------------------
Assembles the system prompt for Poly using the 3 Pillars of her Legal Framework:
1. Moral Principles (Soul)
2. Constitution (Laws)
3. Employment Contract (Mission)
"""
from pathlib import Path
import yaml
from langchain_core.prompts import ChatPromptTemplate

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "personality.yaml"

def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)

def _build_legal_framework(cfg: dict, profile_notes: str = "") -> str:
    """Constructs the multi-pillar legal framework for the system prompt."""
    
    # 1. Pillar 1: Moral
    moral = cfg["moral_principles"]
    traits = "\n".join([f"  - {t}" for t in moral["core_traits"]])
    p1 = f"""
### PILAR 1: PRINCIPIOS MORALES Y DE CONDUCTA
- **Esencia:** {moral['essence']['tone']}, {moral['essence']['energy']}.
- **Estilo:** {moral['essence']['style']}.
- **Rasgos:**
{traits}
"""

    # 2. Pillar 2: Constitution
    const = cfg["constitution"]
    forbidden = "\n".join([f"  - {b}" for b in const["forbidden_behaviors"]])
    p2 = f"""
### PILAR 2: CONSTITUCIÓN POLÍTICA (REGLAS DE SEGURIDAD)
- **Propósito:** {const['art_1_purpose']}
- **Herramientas:** {const['art_2_tools']}
- **Privacidad:** {const['art_3_privacy']}
- **Jerarquía:** {const['art_4_hierarchy']}
- **Prohibiciones Absolutas:**
{forbidden}
"""

    # 3. Pillar 3: Employment Contract
    job = cfg["employment_contract"]
    objs = "\n".join([f"  - {o}" for o in job["main_objectives"]])
    owner_learned = f"\n- **Notas del Dueño:** {profile_notes}" if profile_notes else ""
    p3 = f"""
### PILAR 3: CONTRATO DE TRABAJO (MISIÓN ACTUAL)
- **Marca:** {job['brand']} ({job['niche']})
- **Rol:** {job['role']}
- **Objetivos Clave:**
{objs}{owner_learned}
"""

    return f"{p1}\n{p2}\n{p3}"

# --- Agent-specific instructions (The Task at hand) ---
STAGE_INSTRUCTIONS = {
    "greeting": "Misión: Saluda con calidez, usa el nombre del cliente si lo sabes y detecta cómo puedes ayudar.",
    "discovery": "Misión: Haz preguntas empáticas para entender la necesidad o el 'dolor' del cliente. No vendas aún.",
    "presentation": "Misión: Conecta la necesidad del cliente con los beneficios de nuestros productos. Usa argumentos reales.",
    "objection": "Misión: Valida la duda del cliente y responde con datos, comparativas o testimonios. Usa la búsqueda web si mencionan competencia.",
    "closing": "Misión: El cliente está listo. Guíalo paso a paso para recolectar datos de envío y pago. Sé directo y entusiasta.",
    "post_sale": "Misión: Seguimiento de pedido. Brinda tranquilidad y confirma estados.",
    "complaint": "Misión: Manejo de crisis. Empatía máxima, validación del problema y búsqueda de solución o escalación.",
    "admin": "Misión: Eres la asistente estratégica del dueño. Reporta KPIs, guarda notas y ejecuta comandos.",
    "escalation": "Misión: Avisa que un humano tomará el control. Sé amable y despídete temporalmente.",
}

def get_prompt(stage: str, awareness_context: str = "", profile_notes: str = "", role: str = "customer") -> ChatPromptTemplate:
    """Builds a full ChatPromptTemplate based on the 3 Pillars and awareness context."""
    cfg = _load_config()
    
    legal_framework = _build_legal_framework(cfg, profile_notes=profile_notes)
    stage_instr = STAGE_INSTRUCTIONS.get(stage, "Misión: Interactuar según los pilares legales.")
    
    comm = cfg["communication"]
    comm_rules = f"""
### REGLAS DE COMUNICACIÓN
- Máximo {comm['max_response_lines']} líneas por mensaje.
- Emojis: {comm['emoji_frequency'] if comm['use_emojis'] else 'No usar'}.
- Nombre: {'Usar el nombre del cliente' if comm['use_client_name'] else 'No necesario'}.
"""

    system_content = f"""
# PROTOCOLO DE OPERACIÓN DE POLY AI
Usa el siguiente marco legal para todas tus decisiones.

{legal_framework}

{awareness_context}

{comm_rules}

## MISIÓN ACTUAL (STAGE: {stage.upper()})
{stage_instr}
"""

    return ChatPromptTemplate.from_messages([
        ("system", system_content),
        ("placeholder", "{messages}"),
    ])
