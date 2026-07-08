"""Phase A: bootstrap — print agent configuration."""

from __future__ import annotations

import os

from app.config import get_settings

from demo_presenter import console


def print_bootstrap(*, port: int) -> None:
    cfg = get_settings()
    console.heading("Bootstrap (A)")
    print(f"  LLM_MODE          : {cfg.llm_mode}")
    print(f"  EMBEDDINGS        : {cfg.embeddings_provider}")
    print(f"  BACKEND_MODE      : {cfg.backend_mode}")
    print(f"  BACKEND_BASE_URL  : {cfg.backend_base_url or os.environ.get('BACKEND_BASE_URL', '(default)')}")
    print(f"  CHECKPOINTER      : {os.environ.get('CHECKPOINTER', 'memory')}")
    print(f"  Simulator         : http://127.0.0.1:{port}")
    console.pause_enter("配置已展示，按 Enter 进入 Simulator 实验室…")
