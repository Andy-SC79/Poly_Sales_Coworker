from __future__ import annotations

from .state import PolyState


async def route(state: PolyState) -> str:
    """Minimal router fallback for the agent_core package."""
    return state.get("stage", "greeting")
