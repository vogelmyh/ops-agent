#!/usr/bin/env python3
"""Run RAG golden-set eval: retrieval, oracle coverage, or real-LLM rubric."""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("CHECKPOINTER", "memory")

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"), override=True)

from app.config import get_settings
from app.rag.eval_harness import (
    evaluate_coverage_golden,
    evaluate_real_llm_golden,
    evaluate_retrieval_golden,
)
from app.rag.ingest import reindex
from tests.rag_eval.golden import select_golden_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG golden-set evaluation")
    parser.add_argument(
        "--stage",
        choices=["retrieval", "coverage", "real-llm", "all"],
        default="all",
        help="retrieval | coverage (oracle) | real-llm rubric | all (no real-llm)",
    )
    parser.add_argument(
        "--llm",
        choices=["mock", "real"],
        default=None,
        help="Override LLM_MODE for coverage/real-llm stages",
    )
    parser.add_argument(
        "--embeddings",
        choices=["local-hash", "qwen", "openai", "bge"],
        default=os.environ.get("EMBEDDINGS_PROVIDER", "local-hash"),
    )
    parser.add_argument("--reindex", action="store_true", help="Force reindex before eval")
    parser.add_argument("--challenge", default=None, help="Filter by challenge_type")
    parser.add_argument("--difficulty", default=None, help="Filter by difficulty")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to run")
    parser.add_argument("--smoke", action="store_true", help="Use REAL_LLM_SMOKE_IDS subset")
    parser.add_argument("--ids", default=None, help="Comma-separated case ids")
    args = parser.parse_args()

    os.environ["EMBEDDINGS_PROVIDER"] = args.embeddings
    if args.llm:
        os.environ["LLM_MODE"] = args.llm
    if args.stage == "real-llm" and not args.llm:
        os.environ["LLM_MODE"] = "real"

    get_settings.cache_clear()
    if args.reindex:
        reindex()
    else:
        from app.rag.ingest import ensure_indexed

        ensure_indexed()

    ids = [s.strip() for s in args.ids.split(",")] if args.ids else None
    cases = select_golden_cases(
        ids=ids,
        challenge_type=args.challenge,
        difficulty=args.difficulty,
        limit=args.limit,
        smoke_only=args.smoke,
    )
    settings = get_settings()
    payload: dict = {
        "embeddings": args.embeddings,
        "llm_mode": settings.llm_mode,
        "cases_total": len(cases),
        "case_ids": [c.id for c in cases],
    }

    if args.stage in ("retrieval", "all"):
        report = evaluate_retrieval_golden(cases, settings=settings)
        payload["retrieval"] = report.to_dict()

    if args.stage in ("coverage", "all"):
        if settings.llm_mode != "mock":
            os.environ["LLM_MODE"] = "mock"
            get_settings.cache_clear()
        cov = evaluate_coverage_golden(cases, settings=get_settings())
        payload["coverage_oracle"] = cov.to_dict()
        payload["coverage_oracle"]["rubric"] = "golden_oracle"

    if args.stage == "real-llm":
        if settings.llm_mode != "real":
            print("error: real-llm stage requires LLM_MODE=real or --llm real", file=sys.stderr)
            sys.exit(2)
        if not settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
            print("error: real-llm requires OPENAI_API_KEY", file=sys.stderr)
            sys.exit(2)
        real = evaluate_real_llm_golden(cases, settings=settings)
        payload["real_llm"] = real.to_dict()
        payload["real_llm"]["rubric"] = "llm"

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
