from __future__ import annotations

from .agent_definition import AgentDefinition
from .brain.state import CoreState, WorkflowState
from .interfaces import PromptProvider, ToolProvider, MemoryProvider, RBACProvider, DatabaseProvider, ChannelProvider
from .brain.graph import build_graph


class EngineConfig:
    def __init__(
        self,
        prompt_provider: PromptProvider,
        tool_provider: ToolProvider,
        memory_provider: MemoryProvider,
        rbac_provider: RBACProvider,
        database_provider: DatabaseProvider | None = None,
        channel_provider: ChannelProvider | None = None,
        settings: dict | None = None,
    ):
        self.prompt_provider = prompt_provider
        self.tool_provider = tool_provider
        self.memory_provider = memory_provider
        self.rbac_provider = rbac_provider
        self.database_provider = database_provider
        self.channel_provider = channel_provider
        self.settings = settings or {}


class AgentCoreEngine:
    """Core execution engine for a single agent workflow."""

    def __init__(self, config: EngineConfig):
        self.config = config
        self._graph = None

    async def boot(self) -> None:
        """Initialize the engine; load any required framework state."""
        self._graph = None

    async def run(self, agent_definition: AgentDefinition, core_state: CoreState, workflow_state: WorkflowState) -> tuple[CoreState, WorkflowState]:
        """Execute one turn of the agent workflow."""
        if self._graph is None:
            self._graph = await build_graph()

        # This is an engine placeholder; actual integration with the workflow and providers
        # will be implemented in later phases.
        return core_state, workflow_state

    def shutdown(self) -> None:
        """Release resources if needed."""
        self._graph = None
