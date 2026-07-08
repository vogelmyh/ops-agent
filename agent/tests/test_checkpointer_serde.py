"""Checkpointer serde allowlist for AgentState Pydantic types."""

from __future__ import annotations

import os

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.memory.short_term import get_checkpoint_serde, get_checkpointer


def test_checkpoint_serde_allowlists_agent_state_models():
    serde = get_checkpoint_serde()
    allowed = serde._allowed_msgpack_modules
    assert allowed is not True
    assert ("app.schemas", "IncidentInput") in allowed
    assert ("app.schemas", "Evidence") in allowed


def test_memory_checkpointer_uses_custom_serde():
    get_checkpointer.cache_clear()
    saver = get_checkpointer()
    allowed = saver.serde._allowed_msgpack_modules
    assert ("app.schemas", "IncidentInput") in allowed
    assert ("app.schemas", "Evidence") in allowed
