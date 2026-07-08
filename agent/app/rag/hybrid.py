"""Hybrid retrieval: dense (Chroma) + BM25 fused with reciprocal rank fusion."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.rag.bm25_index import get_bm25_index
from app.rag.store import search_documents


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    *,
    rrf_k: int = 60,
) -> dict[str, float]:
    """Fuse ranked doc_id lists into RRF scores."""
    scores: dict[str, float] = {}
    for ranking in ranked_lists:
        for rank, doc_id in enumerate(ranking, start=1):
            if not doc_id:
                continue
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return scores


def _chunk_by_id(chunks: list[dict]) -> dict[str, dict]:
    return {c.get("doc_id", ""): c for c in chunks if c.get("doc_id")}


def hybrid_search_chunks(
    query: str,
    *,
    service: str | None = None,
    settings: Settings | None = None,
) -> list[dict]:
    """Return up to ``retrieval_hybrid_top_k`` chunks with vector, BM25, and fusion scores."""
    settings = settings or get_settings()
    hybrid_top_k = settings.retrieval_hybrid_top_k
    rrf_k = settings.retrieval_rrf_k
    where = {"service": service} if service else None

    vector_hits = search_documents(query, top_k=hybrid_top_k, where=where)
    for row in vector_hits:
        row["vector_score"] = row.pop("score", None)

    bm25_hits = get_bm25_index(service).search(query, top_k=hybrid_top_k)

    vector_ranking = [c["doc_id"] for c in vector_hits if c.get("doc_id")]
    bm25_ranking = [c["doc_id"] for c in bm25_hits if c.get("doc_id")]
    fusion = reciprocal_rank_fusion([vector_ranking, bm25_ranking], rrf_k=rrf_k)

    merged = _chunk_by_id(vector_hits)
    for chunk in bm25_hits:
        doc_id = chunk.get("doc_id", "")
        if doc_id in merged:
            merged[doc_id]["bm25_score"] = chunk.get("bm25_score")
        else:
            merged[doc_id] = chunk

    results: list[dict] = []
    for doc_id, fusion_score in sorted(fusion.items(), key=lambda item: item[1], reverse=True):
        chunk = merged.get(doc_id)
        if not chunk:
            continue
        row = dict(chunk)
        row["fusion_score"] = round(fusion_score, 6)
        row["score"] = row["fusion_score"]
        results.append(row)
        if len(results) >= hybrid_top_k:
            break
    return results
