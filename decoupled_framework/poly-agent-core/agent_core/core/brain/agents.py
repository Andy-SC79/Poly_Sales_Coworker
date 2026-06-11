from __future__ import annotations

from .state import PolyState


async def greeting_agent(state: PolyState) -> dict:
    return {}


async def discovery_agent(state: PolyState) -> dict:
    return {}


async def presentation_agent(state: PolyState) -> dict:
    return {}


async def objection_agent(state: PolyState) -> dict:
    return {}


async def closing_agent(state: PolyState) -> dict:
    return {}


async def post_sale_agent(state: PolyState) -> dict:
    return {}


async def complaint_agent(state: PolyState) -> dict:
    return {}


async def admin_agent(state: PolyState) -> dict:
    return {}


async def escalation_agent(state: PolyState) -> dict:
    return {}


async def silence_agent(state: PolyState) -> dict:
    return {}


async def profile_extractor(state: PolyState) -> dict:
    return {}
