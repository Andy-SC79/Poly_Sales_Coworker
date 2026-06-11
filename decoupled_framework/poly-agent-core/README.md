# agent-core

`agent-core` is a scaffold for the shared workflow engine and provider abstractions.

## Purpose

- Provide a single workflow execution engine
- Define provider interfaces for prompts, tools, memory, RBAC, database, and channel interactions
- Host generic state and graph execution code that can be reused by downstream business packages

## Current contents

- `core/agent_definition.py`
- `core/interfaces.py`
- `core/engine.py`
- `core/brain/*` copied from the monolith to preserve core implementation
- `pyproject.toml` for package metadata
