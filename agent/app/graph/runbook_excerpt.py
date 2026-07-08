"""Extract fixed runbook sections for diagnose prompts (plan C — sliced excerpts)."""

from __future__ import annotations

import re

_SECTION_HEADINGS = (
    "适用范围",
    "症状",
    "诊断",
    "根因",
    "处置",
    "勿用手段",
)

_SECTION_RE = re.compile(
    r"^##\s+(" + "|".join(re.escape(h) for h in _SECTION_HEADINGS) + r")\s*$",
    re.MULTILINE,
)

_DEFAULT_CHARS_PER_DOC = 1200


def excerpt_runbook(content: str, *, max_chars: int = _DEFAULT_CHARS_PER_DOC) -> str:
    """Return concatenated key sections from a parent runbook markdown body."""
    if not content.strip():
        return ""

    matches = list(_SECTION_RE.finditer(content))
    if not matches:
        return content[:max_chars]

    parts: list[str] = []
    for idx, match in enumerate(matches):
        title = match.group(1)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        if body:
            parts.append(f"## {title}\n{body}")

    text = "\n\n".join(parts)
    return text[:max_chars]
