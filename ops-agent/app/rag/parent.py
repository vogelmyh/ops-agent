"""Resolve retrieved chunks to full parent runbook documents."""

from __future__ import annotations

import re
from pathlib import Path

from app.rag.ingest import extract_h1
from app.rag.store import DATA_DIR

_CHUNK_INDEX_SUFFIX = re.compile(r"-\d+$")


def parent_stem_from_chunk_id(doc_id: str) -> str:
    """Strip trailing chunk index from ingest ids like ``ecomm-order-crashloop-2``."""
    return _CHUNK_INDEX_SUFFIX.sub("", doc_id or "")


def load_runbook_by_stem(stem: str) -> str | None:
    """Load full markdown for a document stem from runbooks or incidents."""
    for sub in ("runbooks", "incidents"):
        path = DATA_DIR / sub / f"{stem}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
    return None


def _chunk_rank_score(chunk: dict) -> float:
    for key in ("rerank_score", "fusion_score", "score"):
        val = chunk.get(key)
        if val is not None:
            return float(val)
    return 0.0


def expand_chunks_to_parent_runbooks(chunks: list[dict]) -> list[dict]:
    """Map chunk hits to deduplicated parent documents (best retrieval score wins)."""
    if not chunks:
        return []

    by_stem: dict[str, dict] = {}
    for chunk in chunks:
        stem = parent_stem_from_chunk_id(chunk.get("doc_id", ""))
        if not stem:
            continue
        rank_score = _chunk_rank_score(chunk)
        existing = by_stem.get(stem)
        if existing is not None and rank_score <= _chunk_rank_score(existing):
            continue
        full_text = load_runbook_by_stem(stem) or chunk.get("content", "")
        by_stem[stem] = {
            "doc_id": stem,
            "title": extract_h1(full_text) or chunk.get("title", stem),
            "service": chunk.get("service", ""),
            "chunk_type": "parent",
            "content": full_text,
            "score": rank_score,
            "vector_score": chunk.get("vector_score"),
            "bm25_score": chunk.get("bm25_score"),
            "fusion_score": chunk.get("fusion_score"),
            "rerank_score": rank_score,
        }
    return sorted(by_stem.values(), key=lambda item: _chunk_rank_score(item), reverse=True)