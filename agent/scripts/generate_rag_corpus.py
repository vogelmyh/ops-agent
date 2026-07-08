#!/usr/bin/env python3
"""Generate RAG eval runbooks from scripts/rag_corpus_specs.py into data/runbooks/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.rag_corpus_specs import RUNBOOK_SPECS, render_markdown

OUT = ROOT / "data" / "runbooks"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    for spec in RUNBOOK_SPECS:
        path = OUT / f"{spec.stem}.md"
        if path.exists():
            # Skip if already present from a prior manual edit (idempotent for new only)
            pass
        content = render_markdown(spec)
        path.write_text(content, encoding="utf-8")
        written += 1
        print(f"wrote {path.name}")
    print(f"done: {written} runbooks in {OUT}")


if __name__ == "__main__":
    main()
