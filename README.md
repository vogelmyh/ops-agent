# Ops Agent Demo — Git Monorepo

拟真运维诊断 Agent 演示：**Python Agent** + **Simulator** + **Java 后端** + **部署清单**。

| 目录 | 说明 |
|------|------|
| [`ops-agent/`](ops-agent/) | LangGraph + FastAPI 主工程（含 `docs/` 架构与改动同步指南） |
| [`ops-backend-simulator/`](ops-backend-simulator/) | 有状态 HTTP 后端替身 |
| [`ops-backend/`](ops-backend/) | Spring Boot 契约参考 |
| [`deploy/`](deploy/) | docker-compose + K8s |
| [`docs/change-workflow.md`](docs/change-workflow.md) | **每次改代码的七步 SOP** |
| [`AGENTS.md`](AGENTS.md) | Cursor Agent 入口 |

## 快速开始

```bash
# Python Agent（在 ops-agent/ops-agent 下已有 .venv 时）
cd ops-agent && source .venv/bin/activate
uvicorn app.main:app --port 8000

# 测试（monorepo 根目录）
make test-rag-retrieval   # Track A — 纯检索
make test-rag-coverage    # Track B — coverage rubric
make test-rag             # 双轨合并
make test-graph
make test-api
make test
```

## 改代码前

1. 读 [`docs/change-workflow.md`](docs/change-workflow.md)
2. `make install-hooks`（首次）→ 之后 commit 自动跑路径相关测试
3. `make impact` 查看建议文档与测试命令
4. 让 Agent 先输出「同步计划」，确认后再改

## 父目录

参考业务语境的 Java/Go 服务在 monorepo 外独立维护，不在本仓库内。
