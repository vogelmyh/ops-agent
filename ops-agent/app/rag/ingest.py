from pathlib import Path

from app.rag.store import DATA_DIR, get_collection

# ---------------------------------------------------------------------------
# Chunking thresholds
# ---------------------------------------------------------------------------

WHOLE_DOC_THRESHOLD = 800   # chars — below this the entire file is one chunk
SECTION_MAX_CHARS = 1200    # chars — a single ## section above this is re-split


# ---------------------------------------------------------------------------
# Pure helper functions (easily unit-tested without ChromaDB)
# ---------------------------------------------------------------------------

def parse_service(stem: str) -> str:
    """Extract the service name from a runbook filename stem.

    Convention: ``<service>-<scenario>.md`` where service may be two tokens
    joined by a hyphen (e.g. ``ecomm-manager``, ``ecomm-order``).

    Examples::
        ecomm-manager-rate-limit    → ecomm-manager
        ecomm-order-crashloop       → ecomm-order
        ecomm-order-stream-paused   → ecomm-order
    """
    known_two_token = (
        "ecomm-manager",
        "ecomm-order",
        "ecomm-catalog",
        "ecomm-search",
        "ecomm-cache",
        "ecomm-payment",
        "ecomm-gateway",
        "ecomm-auth",
        "ecomm-inventory",
        "ecomm-notification",
    )
    for prefix in known_two_token:
        if stem.startswith(prefix):
            return prefix
    # Generic fallback: first two hyphen-separated tokens
    parts = stem.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else stem


def extract_h1(text: str) -> str:
    """Return the first ``# …`` heading line, or empty string."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line.rstrip()
    return ""


def split_by_h2(text: str) -> list[tuple[str, str]]:
    """Split markdown text at ``## …`` headings.

    Returns a list of ``(heading_line, body)`` tuples.
    Any content before the first ``##`` (excluding the h1 title) is prepended
    to the first section's body.
    """
    sections: list[tuple[str, str]] = []
    preamble: list[str] = []
    current_heading = ""
    current_body: list[str] = []
    in_section = False

    for line in text.splitlines():
        if line.startswith("# "):
            continue  # skip h1; it will be added as prefix in the caller
        if line.startswith("## "):
            if in_section:
                sections.append((current_heading, "\n".join(current_body).strip()))
                current_body = []
            else:
                # Attach preamble content to first section
                current_body = [l for l in preamble if l.strip()]
                in_section = True
            current_heading = line.rstrip()
        elif in_section:
            current_body.append(line)
        else:
            preamble.append(line)

    if current_heading:
        sections.append((current_heading, "\n".join(current_body).strip()))

    return sections


def _paragraph_split(text: str, max_chars: int = SECTION_MAX_CHARS) -> list[str]:
    """Recursively split on blank lines until each piece is within max_chars."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        candidate = f"{buf}\n\n{p}".strip() if buf else p
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks or [text[:max_chars]]


# ---------------------------------------------------------------------------
# Core ingest function
# ---------------------------------------------------------------------------

def ingest_document(path: Path, collection, source: str) -> None:
    """Chunk a single markdown document and add it to the vector collection.

    Chunking strategy (two-level):
      1. If ``len(text) <= WHOLE_DOC_THRESHOLD`` → whole file is one chunk.
      2. Else split by ``##`` heading sections; each section is prefixed with
         the h1 title so every chunk is self-contained.
      3. If a section itself exceeds ``SECTION_MAX_CHARS`` → paragraph-level
         recursive split with the same h1 + section heading prefix.
    """
    text = path.read_text(encoding="utf-8")
    stem = path.stem
    title_line = extract_h1(text)
    service = parse_service(stem) if source == "runbooks" else ""

    base_meta: dict = {"title": title_line, "source": source}
    if service:
        base_meta["service"] = service

    def _add(chunk_id: str, document: str, extra_meta: dict) -> None:
        collection.add(
            ids=[chunk_id],
            documents=[document],
            metadatas=[{**base_meta, "doc_id": chunk_id, **extra_meta}],
        )

    if len(text) <= WHOLE_DOC_THRESHOLD:
        # Short document: single chunk, full context preserved
        _add(f"{stem}-0", text, {"chunk_type": "whole"})
        return

    # Long document: section-based split
    sections = split_by_h2(text)
    if not sections:
        # No ## headings — fall back to paragraph split of the whole document
        for i, chunk in enumerate(_paragraph_split(text)):
            _add(f"{stem}-{i}", chunk, {"chunk_type": "paragraph"})
        return

    chunk_idx = 0
    for section_heading, section_body in sections:
        prefix = f"{title_line}\n\n{section_heading}\n" if title_line else f"{section_heading}\n"
        section_text = f"{prefix}{section_body}".strip()

        if len(section_text) <= SECTION_MAX_CHARS:
            _add(f"{stem}-{chunk_idx}", section_text,
                 {"chunk_type": "section", "section": section_heading})
            chunk_idx += 1
        else:
            # Section too long: paragraph-level sub-split, each sub-chunk keeps prefix
            for sub in _paragraph_split(section_body):
                sub_text = f"{prefix}{sub}".strip()
                _add(f"{stem}-{chunk_idx}", sub_text,
                     {"chunk_type": "section_part", "section": section_heading})
                chunk_idx += 1


# ---------------------------------------------------------------------------
# Indexed-flag helpers (one flag per embedding provider)
# ---------------------------------------------------------------------------

def _indexed_flag(provider: str) -> Path:
    """Return the path of the sentinel file for the given embedding provider."""
    return DATA_DIR / f".rag_indexed_{provider}"


def ensure_indexed() -> None:
    """Index all runbook and incident documents if not already done.

    Safe to call repeatedly — exits immediately when the flag file exists.
    To force re-indexing (e.g. after changing chunking strategy or runbook
    content), delete the flag file:  ``data/.rag_indexed_<provider>``
    """
    from app.config import get_settings
    settings = get_settings()
    flag = _indexed_flag(settings.embeddings_provider)
    if flag.exists():
        return

    collection = get_collection(settings)
    for sub in ("runbooks", "incidents"):
        folder = DATA_DIR / sub
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.md")):
            ingest_document(path, collection, source=sub)

    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.touch()


def reindex() -> None:
    """Delete the index flag, wipe the vector collection, and re-ingest all documents.

    Wiping the collection avoids stale chunks when runbook files are removed or renamed.
    """
    from app.config import get_settings
    from app.rag.bm25_index import invalidate_bm25_cache
    from app.rag.store import _chroma_client, collection_name_for

    settings = get_settings()
    flag = _indexed_flag(settings.embeddings_provider)
    if flag.exists():
        flag.unlink()

    invalidate_bm25_cache()

    client = _chroma_client()
    name = collection_name_for(settings.embeddings_provider)
    try:
        client.delete_collection(name)
    except Exception:
        pass

    ensure_indexed()
