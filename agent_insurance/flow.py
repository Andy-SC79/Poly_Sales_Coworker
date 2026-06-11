"""
agent_insurance/flow.py
Core decision logic and data models for the Sura Health prequalification flow.
"""
from typing import TypedDict, Literal, List, Optional

# List of valid contributive EPS systems in Colombia (Sisben is excluded)
VALID_CONTRIBUTIVE_EPS = [
    "sura",
    "salud total eps",
    "salud total",
    "eps sanitas",
    "sanitas",
    "nueva eps",
    "famisanar",
    "aliansalud eps",
    "aliansalud",
    "compensar eps",
    "compensar",
    "servicio occidental de salud",
    "sos",
    "salud mia",
    "salud mía",
    "comfenalco valle",
    "comfenalco",
    "coosalud",
    "mutual ser"
]

class InsuranceState(TypedDict, total=False):
    # Stage management
    # "greeting" -> "prequalification" -> "product_matching" -> "contact_info" -> "scheduling" -> "completed" / "unqualified" / "other_products"
    stage: str
    
    # Party details
    is_for_self: Optional[bool]             # True if caller is the candidate, False if for someone else
    caller_name: Optional[str]
    candidate_relation: Optional[str]       # e.g., "padre", "hijo", "esposa"
    candidate_name: Optional[str]
    candidate_age: Optional[int]
    candidate_has_eps: Optional[bool]
    candidate_eps: Optional[str]
    
    # Qualification results
    is_qualified: Optional[bool]
    qualification_reason: Optional[str]
    matched_product: Optional[str]
    
    # Contact info
    email: Optional[str]
    phone: Optional[str]
    
    # Appointment scheduling
    appointment_status: Literal["none", "link_sent", "scheduled"]
    appointment_date: Optional[str]         # e.g., "2026-06-15 10:00"
    last_interaction_at: Optional[str]      # timestamp
    follow_up_scheduled: Optional[bool]     # True if follow-up within 24h is active

def normalize_string(val: Optional[str]) -> str:
    if not val:
        return ""
    # Basic normalization for search
    return val.strip().lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")

def is_eps_valid_contributive(eps_name: str) -> bool:
    norm_eps = normalize_string(eps_name)
    # Check if the name matches any of our known contributive systems
    return any(name in norm_eps or norm_eps in name for name in VALID_CONTRIBUTIVE_EPS)

def evaluate_qualification(state: InsuranceState) -> InsuranceState:
    """
    Evaluates qualification based on collected data and mutates the state dict.
    Returns the updated state.
    """
    age = state.get("candidate_age")
    has_eps = state.get("candidate_has_eps")
    eps = state.get("candidate_eps")
    
    # Unqualified if no EPS or age is 70 or older
    if has_eps is False or (age is not None and age >= 78):
        state["is_qualified"] = False
        state["qualification_reason"] = "El candidato no cuenta con EPS contributiva o es mayor de 78 años."
        state["matched_product"] = None
        state["stage"] = "unqualified"
        return state
        
    # Check if EPS is valid contributive and age is under 78
    if age is not None and eps is not None:
        is_contributive = is_eps_valid_contributive(eps)
        if is_contributive and age < 78:
            state["is_qualified"] = True
            state["is_qualified"] = True
            # Product matching
            norm_eps = normalize_string(eps)
            if age >= 60:
                state["matched_product"] = "Plan de Salud 60+ Sura"
                state["qualification_reason"] = "Candidato de 60 años o más con EPS contributiva activa."
            elif "sura" in norm_eps and age < 60:
                state["matched_product"] = "Plan Salud Para Todos Integral (PSI)"
                state["qualification_reason"] = "Candidato menor de 60 años afiliado a EPS Sura."
            else:
                state["matched_product"] = "Seguro de Salud Sura (Plan Clásico / Global / Personalizado)"
                state["qualification_reason"] = "Candidato menor de 60 años con otra EPS contributiva válida."
            
            # Switch stage to product matching page only if currently prequalifying
            if state.get("stage") in ("greeting", "prequalification", None):
                state["stage"] = "product_matching"
        else:
            state["is_qualified"] = False
            state["qualification_reason"] = f"La EPS '{eps}' no se encuentra en el sistema contributivo aceptado o el candidato no cumple el rango de edad."
            state["matched_product"] = None
            state["stage"] = "unqualified"
            
    return state
