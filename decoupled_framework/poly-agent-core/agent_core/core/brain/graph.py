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
import json
import structlog
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import ToolMessage
from .state import PolyState
from .router import route
from . import agents

log = structlog.get_logger()

def sync_state_from_tools(state: PolyState):
    """Extrae datos importantes (como el order_id) de las respuestas de las herramientas."""
    if not state.get("messages"):
        return {}
    
    last_msg = state["messages"][-1]
    
    # Solo nos interesan mensajes de herramientas que respondieron con éxito
    if isinstance(last_msg, ToolMessage):
        try:
            raw_content = last_msg.content
            if isinstance(raw_content, str):
                data = json.loads(raw_content)
            else:
                data = raw_content

            updates = {}
            if isinstance(data, dict):
                if data.get("id"):
                    updates["current_order_id"] = data["id"]
                if data.get("event") == "escalation":
                    updates["stage"] = data.get("stage", "escalation")
                    updates["escalation_pending"] = bool(data.get("escalation_pending", True))
                if data.get("stage") and data.get("event") != "escalation":
                    updates["stage"] = data.get("stage")
                if data.get("escalation_pending") is not None:
                    updates["escalation_pending"] = bool(data.get("escalation_pending"))
                return updates
        except Exception:
            pass
    return {}


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
    graph.add_node("silence",      agents.silence_agent)
    graph.add_node("profiler",     agents.profile_extractor)
    graph.add_node("sync_state",   sync_state_from_tools)
    
    # ── Tools Node ────────────────────────────────────────────────────────────
    from langgraph.prebuilt import ToolNode
    from .model_selector import get_admin_tools

    tools_node = ToolNode(get_admin_tools(), handle_tool_errors=True)
    graph.add_node("tools", tools_node)

    # ── Flow: START → profiler → router → agents ─────────────────────────────
    # El profiler extrae datos básicos antes de cualquier decisión.
    graph.add_edge(START, "profiler")

    # Después de perfilar, el enrutador decide a qué agente ir
    graph.add_conditional_edges(
        "profiler",
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
            "silence":      "silence"
        },
    )

    # ── Tool calling logic: If an agent node outputs tool calls, go to tools ──
    from langgraph.prebuilt import tools_condition
    
    for node in ["greeting", "discovery", "presentation", "objection",
                 "closing", "post_sale", "complaint", "admin"]:
        graph.add_conditional_edges(node, tools_condition)
        
    # Las herramientas siempre pasan por el sincronizador antes de volver
    # Insert a small post-tools node to ensure user-visible feedback if the model
    # returned only a tool call (avoids empty assistant messages while tools run).
    def ensure_visible_after_tools(state: PolyState):
        from langchain_core.messages import AIMessage
        if not state.get("messages"):
            return {}
        last = state["messages"][-1]
        # If last is a ToolMessage or an AIMessage with empty content, append a notice
        try:
            from langchain_core.messages import ToolMessage
            is_tool = isinstance(last, ToolMessage)
        except Exception:
            is_tool = False
        is_empty_ai = False
        try:
            if hasattr(last, 'content') and (not getattr(last, 'content')):
                is_empty_ai = True
        except Exception:
            is_empty_ai = False

        # If last is a ToolMessage and it contains a result, include it as a short AIMessage
        if is_tool:
            try:
                raw = getattr(last, 'content', None)
                if isinstance(raw, (str, int, float)) and str(raw).strip():
                    # Keep summary short
                    short = str(raw)
                    if len(short) > 1000:
                        short = short[:1000] + '...'
                    note = AIMessage(content=f"🔧 Resultado de la herramienta: {short}")
                else:
                    note = AIMessage(content="🔎 Consultando herramienta... un momento por favor.")
            except Exception:
                note = AIMessage(content="🔎 Consultando herramienta... un momento por favor.")
            return {"messages": state["messages"] + [note]}

        if is_empty_ai:
            note = AIMessage(content="🔎 Consultando herramienta... un momento por favor.")
            return {"messages": state["messages"] + [note]}
        return {}

    graph.add_node("post_tools", ensure_visible_after_tools)
    graph.add_edge("tools", "post_tools")
    graph.add_edge("post_tools", "sync_state")
    
    # (Se eliminaron las rutas incondicionales a END porque sobreescribían a tools_condition y route_after_tools)

    def route_after_tools(state: PolyState):
        # If a tool was executed as part of this turn, end the turn instead of
        # immediately re-entering the same agent and risking loops.
        if any(isinstance(msg, ToolMessage) for msg in state.get("messages", [])):
            return END
        return state.get("stage", "greeting")

    graph.add_conditional_edges("sync_state", route_after_tools, {
        "greeting": "greeting",
        "discovery": "discovery",
        "presentation": "presentation",
        "objection": "objection",
        "closing": "closing",
        "post_sale": "post_sale",
        "complaint": "complaint",
        "admin": "admin",
        "escalation": "escalation",
        "__end__": END,
    })

    # Escalation siempre termina el turno
    graph.add_edge("escalation", END)

    if checkpointer is None:
        checkpointer = await _get_checkpointer()
    
    compiled = graph.compile(checkpointer=checkpointer)
    log.info("graph.compiled", checkpointer=type(checkpointer).__name__)
    return compiled


async def _get_checkpointer():
    """
    Use an in-memory checkpoint when persistent storage is not available.
    This avoids runtime dependency on a local database during startup.
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


# Legacy fallback removed to prevent monolithic imports.
poly_graph = None
