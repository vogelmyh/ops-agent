"""Shared fixtures for rag_eval tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "local-hash")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.config import get_settings
from app.rag.ingest import reindex


@pytest.fixture(scope="package", autouse=True)
def _indexed_corpus():
    get_settings.cache_clear()
    reindex()
    yield
