"""
agent_insurance/router.py
Stage router for Sura prequalification workflow.
Determines the next logic node based on the state.
"""
import structlog
from typing import Dict, Any

log = structlog.get_logger()

def route(state: Dict[str, Any]) -> str:
    """
    Returns the stage identifier representing the current stage of the conversation.
    """
    current_stage = state.get("stage", "greeting")
    
    # 1. Admin/Escalation/Silence hooks (mimicking Poly core rules if required)
    if state.get("is_admin"):
        return "admin"
    if state.get("is_paused"):
        return "silence"
        
    # 2. Main workflow stages
    # greeting -> prequalification -> product_matching -> contact_info -> scheduling -> completed
    # Or unqualified / other_products
    log.info("insurance_router.route", current_stage=current_stage, customer=state.get("customer_id"))
    return current_stage
