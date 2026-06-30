#!/usr/bin/env python3
"""Demo for three fault scenarios.

Priority (highest to lowest):
  shell export  >  .env file  >  script defaults below
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 1. Load .env first (override=False means shell exports still win)
try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(_env, override=False)
except ImportError:
    pass

# 2. Script-level defaults (only applied when neither shell nor .env set a value)
os.environ.setdefault("BACKEND_MODE", "mock")
os.environ.setdefault("LLM_MODE", "mock")       # overridden by .env LLM_MODE=real
os.environ.setdefault("CHECKPOINTER", "memory")  # memory is safer for one-shot demos

from app.adapters.mock_data import reset_mock_scenarios, set_mock_scenario
from app.config import get_settings
from app.graph.runner import resume_approval, start_diagnosis
from app.schemas import IncidentInput

SCENARIOS = [
    ("ecomm-manager", "rate-limit", "【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟，操作超时增多"),
    ("ecomm-order", "crashloop", "下单服务 0/3 Ready"),
    ("ecomm-order", "stream-paused", "订单事件流无数据"),
]


def main() -> None:
    cfg = get_settings()
    print(f"[demo] backend={cfg.backend_mode}  llm={cfg.llm_mode}  checkpointer={cfg.checkpointer}\n")

    for service, scenario, desc in SCENARIOS:
        reset_mock_scenarios()
        set_mock_scenario(service, scenario)
        print(f"=== {service} ({scenario}) ===")
        _, resp, meta = start_diagnosis(IncidentInput(service=service, description=desc))
        print("根因:", resp.root_cause)
        print("证据:", [e.ref for e in resp.evidence])
        if meta.get("pending_interrupt"):
            print("等待审批，自动批准演示...")
            resp = resume_approval(resp.thread_id, approved=True)
        print("摘要:", resp.summary)
        print()


if __name__ == "__main__":
    main()
