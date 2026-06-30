"""Lexical rerank over hybrid candidates (no extra model — CI-friendly)."""

from __future__ import annotations

from app.rag.tokenize import tokenize


def _normalize_batch(values: list[float]) -> list[float]:
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi <= lo:
        return [1.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def lexical_overlap_score(query: str, document: str) -> float:
    """Weighted token overlap between query and document."""
    q_tokens = tokenize(query)
    if not q_tokens:
        return 0.0
    q_set = set(q_tokens)
    d_tokens = tokenize(document)
    if not d_tokens:
        return 0.0
    hits = sum(1 for token in d_tokens if token in q_set)
    return hits / ((len(q_set) * len(d_tokens)) ** 0.5 + 1e-9)


def rerank_chunks(
    query: str,
    chunks: list[dict],
    *,
    top_k: int,
) -> list[dict]:
    """Rerank hybrid chunks; writes ``rerank_score`` and updates ``score``."""
    if not chunks:
        return []

    fusion_vals = [float(c.get("fusion_score") or c.get("score") or 0.0) for c in chunks]
    bm25_vals = [float(c.get("bm25_score") or 0.0) for c in chunks]
    lex_vals = [lexical_overlap_score(query, c.get("content", "")) for c in chunks]

    norm_fusion = _normalize_batch(fusion_vals)
    norm_bm25 = _normalize_batch(bm25_vals)
    norm_lex = _normalize_batch(lex_vals)

    scored: list[dict] = []
    for idx, chunk in enumerate(chunks):
        rerank_score = round(
            0.40 * norm_fusion[idx] + 0.35 * norm_bm25[idx] + 0.25 * norm_lex[idx],
            6,
        )
        row = dict(chunk)
        row["rerank_score"] = rerank_score
        row["score"] = rerank_score
        scored.append(row)

    scored.sort(key=lambda item: item["rerank_score"], reverse=True)
    return scored[:top_k]
