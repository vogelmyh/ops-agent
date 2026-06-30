"""In-memory BM25 index over Chroma chunk corpus."""

from __future__ import annotations

from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.rag.ingest import _indexed_flag, ensure_indexed
from app.rag.store import collection_name_for, get_collection
from app.rag.tokenize import tokenize

_CACHE: dict[str, tuple[float, "Bm25ChunkIndex"]] = {}


@dataclass
class Bm25ChunkIndex:
    chunks: list[dict] = field(default_factory=list)
    _bm25: BM25Okapi | None = field(default=None, repr=False)
    _corpus_tokens: list[list[str]] = field(default_factory=list, repr=False)

    def _ensure_bm25(self) -> BM25Okapi:
        if self._bm25 is None:
            self._corpus_tokens = [tokenize(c.get("content", "")) for c in self.chunks]
            self._bm25 = BM25Okapi(self._corpus_tokens)
        return self._bm25

    def search(self, query: str, top_k: int) -> list[dict]:
        if not self.chunks:
            return []
        bm25 = self._ensure_bm25()
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        scores = bm25.get_scores(query_tokens)
        ranked = sorted(
            zip(self.chunks, scores),
            key=lambda pair: pair[1],
            reverse=True,
        )[:top_k]
        results: list[dict] = []
        for chunk, score in ranked:
            if score <= 0:
                continue
            row = dict(chunk)
            row["bm25_score"] = round(float(score), 4)
            results.append(row)
        return results


def invalidate_bm25_cache() -> None:
    _CACHE.clear()


def _cache_key(service: str | None) -> str:
    settings = get_settings()
    return f"{collection_name_for(settings.embeddings_provider)}:{service or '*'}"


def _flag_mtime() -> float:
    settings = get_settings()
    flag = _indexed_flag(settings.embeddings_provider)
    return flag.stat().st_mtime if flag.exists() else 0.0


def _load_chunks(service: str | None) -> list[dict]:
    ensure_indexed()
    collection = get_collection()
    where = {"service": service} if service else None
    kwargs: dict = {"include": ["documents", "metadatas"]}
    if where:
        kwargs["where"] = where
    raw = collection.get(**kwargs)
    ids = raw.get("ids") or []
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    chunks: list[dict] = []
    for doc_id, doc, meta in zip(ids, docs, metas):
        meta = meta or {}
        chunks.append({
            "doc_id": meta.get("doc_id", doc_id),
            "title": meta.get("title", ""),
            "service": meta.get("service", ""),
            "chunk_type": meta.get("chunk_type", ""),
            "content": doc or "",
        })
    return chunks


def get_bm25_index(service: str | None = None) -> Bm25ChunkIndex:
    """Return a cached BM25 index for the current collection and optional service filter."""
    key = _cache_key(service)
    mtime = _flag_mtime()
    cached = _CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    index = Bm25ChunkIndex(chunks=_load_chunks(service))
    _CACHE[key] = (mtime, index)
    return index
