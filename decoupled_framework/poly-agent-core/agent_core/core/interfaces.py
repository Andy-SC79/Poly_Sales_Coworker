from __future__ import annotations

from typing import Protocol
from langchain_core.messages import BaseMessage


class PromptProvider(Protocol):
    def load_system_prompt(self, stage: str) -> str:
        ...

    def load_stage_prompt(self, stage: str) -> str:
        ...


class ToolProvider(Protocol):
    def list_tools(self) -> list[str]:
        ...

    async def invoke_tool(self, tool_name: str, params: dict) -> dict:
        ...


class MemoryProvider(Protocol):
    async def load_long_term(self, customer_id: str) -> dict | None:
        ...

    async def save_long_term(self, customer_id: str, data: dict) -> None:
        ...

    async def index_episodic(self, customer_id: str, text: str) -> None:
        ...

    async def search_episodic(self, customer_id: str, query: str, k: int) -> list[dict]:
        ...


class RBACProvider(Protocol):
    def get_role(self, user_id: str) -> str:
        ...

    def has_permission(self, user_id: str, action: str) -> bool:
        ...


class DatabaseProvider(Protocol):
    async def execute(self, query: str, params: dict | None = None) -> object:
        ...

    async def fetch_one(self, query: str, params: dict | None = None) -> dict | None:
        ...

    async def fetch_all(self, query: str, params: dict | None = None) -> list[dict]:
        ...


class ChannelProvider(Protocol):
    async def send_text(self, channel: str, to: str, text: str, metadata: dict | None = None) -> dict:
        ...

    async def receive(self, raw_payload: dict) -> dict:
        ...
