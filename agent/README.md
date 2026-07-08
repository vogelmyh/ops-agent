# Agent 服务（ops-agent）

拟真运维诊断与操作 Agent（Python 3.12 + LangGraph + FastAPI）。默认 **mock-first**，无需 API Key、后端或 Docker 即可离线运行。

## 快速开始

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip && .venv/bin/python -m pip install -e ".[dev]"
cp -n .env.example .env
BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
curl http://localhost:8000/healthz
```

```bash
# 离线三场景（或在 monorepo 根目录 make demo）
CHECKPOINTER=memory BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash \
  .venv/bin/python scripts/demo.py
CHECKPOINTER=memory LLM_MODE=real BACKEND_MODE=real python scripts/run_demo.py --profile standard  # real LLM E2E 演示
CHECKPOINTER=memory python eval/run_eval.py # 15 场景评测
python -m pytest tests/ -q
```

## API

| 路径 | 说明 |
|------|------|
| `GET /healthz` | 存活探针 |
| `GET /readyz` | 就绪（含 backend/llm 模式） |
| `GET /metrics` | Prometheus 指标 |
| `POST /diagnose` | 启动诊断（可能停在 HITL） |
| `POST /approve` | 审批后恢复执行 |
| `GET /runs/{thread_id}` | 查询运行状态 |

## 电商故障场景（示例）

| 服务 | 现象 | 根因（mock/real 一致） |
|------|------|------------------------|
| ecomm-manager | 管理 API QPS 骤降 | 限流阈值误配 max-qps |
| ecomm-order | 0/3 Ready | 坏镜像 CrashLoop |
| ecomm-order | 订单事件无流入 | order-events 流被暂停 |

完整 10 个 Type A 场景见 `data/runbooks/ecomm-*.md`。

## 文档

- **修改流程（改代码前必读）**：[../docs/workflow/change-workflow.md](../docs/workflow/change-workflow.md)
- **索引**：[../docs/README.md](../docs/README.md)
- **总览**：[../docs/agent/architecture.md](../docs/agent/architecture.md)
- **场景目录**（测什么）：[../docs/agent/test-scenario-trajectories.md](../docs/agent/test-scenario-trajectories.md)
- **E2E 演示**（real LLM）：[../docs/agent/demo-scenarios.md](../docs/agent/demo-scenarios.md)
- **组件**：`../docs/agent/*-architecture.md`
- **Simulator 联调**：[../docs/agent/backend-adapters-architecture.md](../docs/agent/backend-adapters-architecture.md) §5；实现细节见 [ops-backend-simulator/README.md](../ops-backend-simulator/README.md)

## 环境变量

见 `.env.example`。常用：`BACKEND_MODE=mock|real`、`LLM_MODE=mock|real`、`EMBEDDINGS_PROVIDER=local-hash`、`CHECKPOINTER=sqlite|memory`。推荐 real 组合：DeepSeek chat（`OPENAI_*`）+ Qwen embedding（`EMBEDDINGS_PROVIDER=qwen`，`text-embedding-v3`）。

## 与后端联调

- **Java ops-backend** 或 **ops-backend-simulator**：`BACKEND_MODE=real` + `BACKEND_BASE_URL=…`  
  步骤见 [../docs/agent/backend-adapters-architecture.md](../docs/agent/backend-adapters-architecture.md)。

## 工程亮点

- **幻觉抑制**：RAG runbook + 结构化诊断节点 + 强制 evidence 引用
- **工具不稳**：Pydantic 工具 schema + mock/real 同一契约
- **安全**：只读/写工具隔离；`RiskLevel.HIGH` 走 LangGraph `interrupt` HITL
- **评测**：`eval/dataset.jsonl` 15 场景，当前离线准确率 100%（heuristic judge）
