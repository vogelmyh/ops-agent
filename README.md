# Ops Agent Demo — Git Monorepo

本项目是一个**拟真电商 SaaS 运维 Agent 演示**（LangGraph + FastAPI + RAG）：接收故障工单后，自动采集遥测、检索 runbook、诊断根因，并在风险可控时执行修复（高危走人审）；配套有状态后端替身、Java 契约参考与部署清单。默认 **mock-first**，无需 API Key 即可离线跑通；也可切换 real LLM 做 E2E walkthrough。


| 目录                                                                     | 说明                                         |
| ---------------------------------------------------------------------- | ------------------------------------------ |
| `[agent/](agent/)`                                                     | LangGraph + FastAPI 主工程（架构见 `docs/agent/`） |
| `[ops-backend-simulator/](ops-backend-simulator/)`                     | 有状态 HTTP 后端替身                              |
| `[ops-backend/](ops-backend/)`                                         | Spring Boot 契约参考                           |
| `[deploy/](deploy/)`                                                   | docker-compose + K8s                       |
| `[docs/README.md](docs/README.md)`                                     | **文档总索引**                                  |
| `[docs/workflow/change-workflow.md](docs/workflow/change-workflow.md)` | 每次改代码的七步 SOP                               |
| `[AGENTS.md](AGENTS.md)`                                               | Cursor Agent 入口                            |


## 快速开始

```bash
# 0. 首次：安装依赖（在 agent/ 下）
cd agent
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip && .venv/bin/python -m pip install -e ".[dev]"
cp -n .env.example .env    # 默认 mock-first；real LLM 再改 .env

# 1. 启动 API（mock 模式，无需 API Key；在 monorepo 根目录）
cd agent && BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. 离线演示（mock；make 会覆盖 .env 中的 real 配置）
make demo

# 3. Real LLM 场景演出（需 agent/.env 配置 OPENAI_* 等；自动起 simulator）
make demo-real              # 交互式 walkthrough（单幕 + 目录；详见 demo-presenter.md）
make demo-real-auto         # 标准五幕连跑（~3 min，DEMO-02 处 Enter 批准 HITL）

# 4. 测试（在 monorepo 根目录）
make test-rag-retrieval     # RAG Track A：检索 + golden L1
make test-rag-coverage      # RAG Track B：coverage rubric + golden L2
make test-rag               # RAG 双轨（合入前推荐）
make test-graph             # LangGraph 路径：REM / HITL / LOOP / DEC / KB
make test-api               # HTTP API、eval、tracing、health
make test-simulator         # 后端替身状态机
make test                   # agent/ 全量 pytest（合入前最终门禁）
```

Real LLM 演示见 [`docs/agent/demo-presenter.md`](docs/agent/demo-presenter.md)（交互）与 [`docs/agent/demo-scenarios.md`](docs/agent/demo-scenarios.md)（batch profile）。

## 改代码前

1. 读 [`docs/workflow/change-workflow.md`](docs/workflow/change-workflow.md)
2. `make install-hooks`（首次）→ 之后 commit 自动跑路径相关测试
3. `make impact` 查看建议文档与测试命令
4. 让 Agent 先输出「同步计划」，确认后再改
