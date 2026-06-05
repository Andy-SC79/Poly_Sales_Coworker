from functools import lru_cache
from pathlib import Path

import yaml

_SCHEMA_PATH = Path("config/db_schema.yaml")


def _load_schema() -> dict:
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {_SCHEMA_PATH}")
    return yaml.safe_load(_SCHEMA_PATH.read_text(encoding="utf-8")) or {}


@lru_cache
def get_db_schema() -> dict:
    return _load_schema()


def table(name: str) -> str:
    return get_db_schema().get("database", {}).get("tables", {}).get(name, name)


def rpc(name: str) -> str:
    return get_db_schema().get("database", {}).get("rpc", {}).get(name, name)


def field(entity: str, key: str) -> str:
    return get_db_schema().get("fields", {}).get(entity, {}).get(key, key)
