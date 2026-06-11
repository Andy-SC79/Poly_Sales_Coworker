"""
agent_sales/agents.py
Proxy to the real core agent implementations.
"""
from core.brain.agents import (
    profile_extractor,
    greeting_agent,
    discovery_agent,
    presentation_agent,
    objection_agent,
    closing_agent,
    post_sale_agent,
    complaint_agent,
    admin_agent,
    escalation_agent,
    silence_agent,
)

__all__ = [
    "profile_extractor",
    "greeting_agent",
    "discovery_agent",
    "presentation_agent",
    "objection_agent",
    "closing_agent",
    "post_sale_agent",
    "complaint_agent",
    "admin_agent",
    "escalation_agent",
    "silence_agent",
]
