import hashlib
from pathlib import Path

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.config import get_settings

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# One collection per embedding provider so that switching providers
# does not mix vectors of different dimensions/semantics.
_COLLECTION_NAMES: dict[str, str] = {
    "local-hash": "ops_knowledge_local_hash",
    "openai": "ops_knowledge_openai",
    "qwen": "ops_knowledge_qwen",
    "bge": "ops_knowledge_bge",
}
RELEVANCE_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Embedding implementations
# ---------------------------------------------------------------------------

class LocalHashEmbedding(EmbeddingFunction):
    """Deterministic offline embeddings for mock-first demos.

    WARNING: These are hash-based vectors with no semantic meaning.
    Cosine similarity scores are essentially random.
    Use EMBEDDINGS_PROVIDER=openai for real semantic retrieval.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def name(self) -> str:
        return "local-hash"

    def __call__(self, input: Documents) -> Embeddings:
        vectors: Embeddings = []
        for text in input:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(digest[i % len(digest)] / 255.0) * 2 - 1 for i in range(self.dim)]
            vectors.append(vec)
        return vectors


class OpenAIChromaEmbedding(EmbeddingFunction):
    """Semantic embeddings via OpenAI text-embedding-3-small (1536 dims)."""

    def __init__(self, api_key: str, base_url: str, model: str = "text-embedding-3-small") -> None:
        from langchain_openai import OpenAIEmbeddings
        self._model = model
        self._embedder = OpenAIEmbeddings(
            api_key=api_key,
            model=model,
            base_url=base_url,
            # Disable tiktoken pre-tokenization: some providers (e.g. Aliyun DashScope)
            # only accept raw strings, not integer token ID arrays.
            check_embedding_ctx_length=False,
        )

    def name(self) -> str:
        return f"openai:{self._model}"

    def __call__(self, input: Documents) -> Embeddings:
        return self._embedder.embed_documents(list(input))


# ---------------------------------------------------------------------------
# Collection helpers
# ---------------------------------------------------------------------------

def _chroma_client() -> chromadb.ClientAPI:
    persist = DATA_DIR / "chroma"
    persist.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist))


def _make_embedding_function(settings=None) -> EmbeddingFunction:
    if settings is None:
        settings = get_settings()
    provider = settings.embeddings_provider

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("EMBEDDINGS_PROVIDER=openai requires OPENAI_API_KEY to be set")
        return OpenAIChromaEmbedding(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.embeddings_model,
        )

    if provider == "qwen":
        # Aliyun DashScope exposes an OpenAI-compatible /v1/embeddings endpoint.
        # text-embedding-v4 outputs 1024-dimensional vectors.
        if not settings.qwen_api_key:
            raise ValueError("EMBEDDINGS_PROVIDER=qwen requires QWEN_API_KEY to be set")
        return OpenAIChromaEmbedding(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            model=settings.embeddings_model,
        )

    # "local-hash" and "bge" (fallback) both use hash embedding for the demo
    return LocalHashEmbedding()


def get_collection(settings=None):
    if settings is None:
        settings = get_settings()
    client = _chroma_client()
    name = _COLLECTION_NAMES.get(settings.embeddings_provider, "ops_knowledge_local_hash")
    ef = _make_embedding_function(settings)
    kwargs: dict = {"name": name, "embedding_function": ef}
    if settings.embeddings_provider not in ("local-hash", "bge"):
        kwargs["metadata"] = {"hnsw:space": "cosine"}
    return client.get_or_create_collection(**kwargs)


def collection_name_for(provider: str) -> str:
    return _COLLECTION_NAMES.get(provider, "ops_knowledge_local_hash")


# ---------------------------------------------------------------------------
# Public search API
# ---------------------------------------------------------------------------

def search_documents(
    query: str,
    top_k: int = 3,
    where: dict | None = None,
) -> list[dict]:
    """Retrieve the most relevant runbook chunks for the given query.

    Args:
        query:  Symptom-rich natural language query (built from collected evidence).
        top_k:  Maximum number of chunks to return before relevance filtering.
        where:  Optional ChromaDB metadata filter, e.g. ``{"service": "ecomm-manager"}``.
                Only meaningful with a semantic embedding provider.

    Returns:
        List of chunk dicts with keys: doc_id, title, content, score.
        Caller should apply :func:`filter_by_relevance` before passing to the LLM.
    """
    from app.rag.ingest import ensure_indexed

    settings = get_settings()
    ensure_indexed()
    collection = get_collection(settings)
    total = collection.count()
    if total == 0:
        return []

    query_kwargs: dict = {"query_texts": [query]}
    if where:
        # Count matching docs first so n_results never exceeds the filtered subset.
        matching_ids = collection.get(where=where, include=[])["ids"]
        n_matching = len(matching_ids)
        if n_matching == 0:
            return []
        query_kwargs["n_results"] = min(top_k, n_matching)
        query_kwargs["where"] = where
    else:
        query_kwargs["n_results"] = min(top_k, total)

    result = collection.query(**query_kwargs)

    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    chunks = []
    for doc, meta, dist in zip(docs, metas, dists):
        chunks.append({
            "doc_id": meta.get("doc_id", ""),
            "title": meta.get("title", ""),
            "service": meta.get("service", ""),
            "chunk_type": meta.get("chunk_type", ""),
            "content": doc,
            "score": round(1.0 - float(dist), 4) if dist is not None else 1.0,
        })
    return chunks


def filter_by_relevance(chunks: list[dict], threshold: float = RELEVANCE_THRESHOLD) -> list[dict]:
    """Discard chunks below the relevance threshold.

    With ``local-hash`` embeddings the scores are random; callers should pass
    ``threshold=0.0`` to skip filtering in mock mode.
    """
    return [c for c in chunks if c.get("score", 0.0) >= threshold]
