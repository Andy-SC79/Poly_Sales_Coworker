from __future__ import annotations

from typing import Protocol
from .brain.state import CoreState, WorkflowState
from .interfaces import PromptProvider, ToolProvider, RBACProvider, MemoryProvider, DatabaseProvider, ChannelProvider


class WorkflowDefinition(Protocol):
    """Minimal workflow contract for a single active workflow."""

    workflow_id: str

    def initial_state(self) -> WorkflowState:
        ...

    async def route(self, core_state: CoreState, workflow_state: WorkflowState) -> str:
        ...

    async def run_node(self, stage: str, core_state: CoreState, workflow_state: WorkflowState) -> dict:
        ...


class AgentConfig:
    """Agent-specific configuration."""

    def __init__(self, values: dict[str, object] | None = None):
        self.values = values or {}

    def get(self, name: str, default: object | None = None) -> object | None:
        return self.values.get(name, default)


class AgentDefinition(Protocol):
    """A complete agent contract for agent-core execution."""

    workflow: WorkflowDefinition
    prompt_provider: PromptProvider
    tool_provider: ToolProvider
    rbac_provider: RBACProvider
    memory_provider: MemoryProvider
    config: AgentConfig
    database_provider: DatabaseProvider | None
    channel_provider: ChannelProvider | None
