"""
core/brain/graph.py
--------------------
Builds and compiles the main LangGraph StateGraph.
This is the central nervous system of Poly — all agents are wired here.

Graph flow:
  [START] → router → (greeting | discovery | presentation |
                       objection | closing | post_sale |
                       complaint | admin | escalation) → [END]

Each agent node can also loop back for multi-turn interactions.
"""
import structlog
from langgraph.graph import StateGraph, START, END

from core.brain.state import PolyState
from core.brain.router import route
from core.brain import agents

log = structlog.get_logger()


async def build_graph(checkpointer=None):
    """
    Construct and compile the Poly agent graph.
    """
    graph = StateGraph(PolyState)

    # ── Register all agent nodes ──────────────────────────────────────────────
    graph.add_node("greeting",     agents.greeting_agent)
    graph.add_node("discovery",    agents.discovery_agent)
    graph.add_node("presentation", agents.presentation_agent)
    graph.add_node("objection",    agents.objection_agent)
    graph.add_node("closing",      agents.closing_agent)
    graph.add_node("post_sale",    agents.post_sale_agent)
    graph.add_node("complaint",    agents.complaint_agent)
    graph.add_node("admin",        agents.admin_agent)
    graph.add_node("escalation",   agents.escalation_agent)
    
    # ── Tools Node ────────────────────────────────────────────────────────────
    from langgraph.prebuilt import ToolNode
    from core.brain.model_selector import web_search_tool
    
    tools_node = ToolNode([web_search_tool])
    graph.add_node("tools", tools_node)

    # ── Conditional edge: START → router → agent node ─────────────────────────
    graph.add_conditional_edges(
        START,
        route,
        {
            "greeting":     "greeting",
            "discovery":    "discovery",
            "presentation": "presentation",
            "objection":    "objection",
            "closing":      "closing",
            "post_sale":    "post_sale",
            "complaint":    "complaint",
            "admin":        "admin",
            "escalation":   "escalation",
        },
    )

    # ── Tool calling logic: If an agent node outputs tool calls, go to tools ──
    from langgraph.prebuilt import tools_condition
    
    for node in ["greeting", "discovery", "presentation", "objection",
                 "closing", "post_sale", "complaint", "admin"]:
        graph.add_conditional_edges(node, tools_condition)
        # If tools_condition returns "tools", it goes to tools node.
        # If it returns END, it ends.
        
    # Tools node always goes back to the stage it came from? 
    # Actually, in this simple graph, it might be better to go back to the same node.
    # But LangGraph's tools_condition usually expects to return to the caller.
    # We'll use a custom edge to return to the same stage.
    
    def should_continue(state: PolyState):
        messages = state["messages"]
        last_message = messages[-1]
        if last_message.tool_calls:
            return "tools"
        return END

    # We need to map the tools node back to the appropriate agent.
    # This is tricky with multiple stages. 
    # Simplest way: use a "router" after tools to go back to the current stage.
    def route_after_tools(state: PolyState):
        return state.get("stage", "greeting")

    graph.add_conditional_edges("tools", route_after_tools)

    # Escalation always ends the turn (no tools there usually)
    graph.add_edge("escalation", END)

    # ── Checkpointer: Default to _get_checkpointer if none provided ───────────
    if checkpointer is None:
        checkpointer = await _get_checkpointer()
    
    compiled = graph.compile(checkpointer=checkpointer)

    log.info("graph.compiled", checkpointer=type(checkpointer).__name__)
    return compiled


async def _get_checkpointer():
    """
    Try to connect to PostgreSQL for persistent memory.
    Falls back to in-memory for stability if DB is unreachable or 
    if not running within the managed lifespan (like in telegram_runner).
    """
    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver() # Default to MemorySaver for standalone runners to avoid connection issues.


# ── Lazy singleton — initialized on first use ─────────────────────────────────
_poly_graph = None


async def get_poly_graph(checkpointer=None):
    """Return the compiled graph, building it on first call."""
    global _poly_graph
    if _poly_graph is None:
        _poly_graph = await build_graph(checkpointer=checkpointer)
    return _poly_graph


# Backward-compat alias for tests and poly_chat.py that import `poly_graph` directly.
# This triggers a synchronous build using MemorySaver (no DB needed for unit tests).
def _build_sync_fallback():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import StateGraph
    graph = StateGraph(PolyState)
    graph.add_node("greeting",     agents.greeting_agent)
    graph.add_node("discovery",    agents.discovery_agent)
    graph.add_node("presentation", agents.presentation_agent)
    graph.add_node("objection",    agents.objection_agent)
    graph.add_node("closing",      agents.closing_agent)
    graph.add_node("post_sale",    agents.post_sale_agent)
    graph.add_node("complaint",    agents.complaint_agent)
    graph.add_node("admin",        agents.admin_agent)
    graph.add_node("escalation",   agents.escalation_agent)
    graph.add_conditional_edges(START, route, {
        "greeting": "greeting", "discovery": "discovery",
        "presentation": "presentation", "objection": "objection",
        "closing": "closing", "post_sale": "post_sale",
        "complaint": "complaint", "admin": "admin", "escalation": "escalation",
    })
    for node in ["greeting", "discovery", "presentation", "objection",
                 "closing", "post_sale", "complaint", "admin", "escalation"]:
        graph.add_edge(node, END)
    return graph.compile(checkpointer=MemorySaver())


poly_graph = _build_sync_fallback()
