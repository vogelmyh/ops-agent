"""End-to-end chunk retrieval: hybrid top-20 → rerank → parent expand → top-3."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.rag.hybrid import hybrid_search_chunks
from app.rag.parent import expand_chunks_to_parent_runbooks
from app.rag.rerank import rerank_chunks
from app.rag.store import filter_by_relevance


def retrieve_ranked_parent_chunks(
    query: str,
    *,
    service: str | None = None,
    settings: Settings | None = None,
) -> list[dict]:
    """Hybrid retrieve, rerank chunks, expand to parent runbooks, return top parents."""
    settings = settings or get_settings()

    hybrid = hybrid_search_chunks(query, service=service, settings=settings)
    reranked = rerank_chunks(
        query,
        hybrid,
        top_k=settings.retrieval_rerank_chunk_top_k,
    )

    threshold = (
        0.0
        if settings.embeddings_provider == "local-hash"
        else settings.retrieval_rerank_min_score
    )
    filtered = filter_by_relevance(reranked, threshold=threshold)

    parents = expand_chunks_to_parent_runbooks(filtered)
    return parents[: settings.retrieval_final_top_k]
