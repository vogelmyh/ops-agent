"""Lightweight tokenizer for BM25 / lexical rerank (CN + EN ops text)."""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")


def tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English ops text for lexical scoring."""
    if not text:
        return []
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        tokens.append(match.group(0))
    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            tokens.append(char)
    return tokens
