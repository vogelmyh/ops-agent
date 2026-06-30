# API 与运行时 — 架构与测试

> **读者**：开发者 + Cursor Agent。  
> **总览**：[`architecture.md`](architecture.md)

---

## 1. 职责

对外 **HTTP 服务** 与进程级横切能力：

- FastAPI 路由（诊断启动、HITL 恢复、运行快照）
- 配置（`pydantic-settings`）
- LLM / Embeddings provider 选择与 mock
- LangGraph checkpointer（sqlite / memory / redis）
- 可观测性：Prometheus metrics、LangSmith tracing、审计钩子

图业务逻辑在 `app/graph/`，本文不展开节点细节。

---

## 2. 流程

### 2.1 请求生命周期

```text
HTTP Request
  → FastAPI route (main.py)
  → graph.runner (start_diagnosis / resume_*)
  → build_graph() + checkpointer
  → DiagnoseResponse JSON (+ meta.pending_interrupt)
```

`lifespan` 启动时：`init_langsmith(settings)`，日志打印 `backend_mode` / `llm_mode`。

### 2.2 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 存活 |
| GET | `/readyz` | 就绪 + 模式摘要 |
| GET | `/metrics` | Prometheus |
| POST | `/diagnose` | `DiagnoseRequest` → 启动图 |
| POST | `/approve` | 恢复 `approve` 中断 |
| POST | `/runbooks/notes` | 恢复 runbook notes |
| POST | `/runbooks/review` | 恢复 runbook 审核 |
| GET | `/runs/{thread_id}` | checkpoint 状态调试 |

`POST /diagnose` 记录 `RUN_LATENCY` histogram。

---

## 3. 代码映射

| 模块 | 路径 |
|------|------|
| FastAPI | `app/main.py` |
| 配置 | `app/config.py`, `get_settings()` |
| 请求/响应 schema | `app/schemas.py` |
| Runner | `app/graph/runner.py` |
| LLM | `app/llm/provider.py` |
| Checkpointer | `app/memory/checkpointer.py` |
| Metrics | `app/observability/metrics.py` |
| Tracing | `app/observability/tracing.py` |
| Audit | `app/observability/audit.py`（如有） |

---

## 4. 配置（环境变量索引）

完整列表以 `app/config.py` 为准；常用项：

| 变量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_MODE` | mock | 见 [backend-adapters](backend-adapters-architecture.md) |
| `BACKEND_BASE_URL` | http://localhost:8080 | |
| `LLM_MODE` | mock | mock \| real |
| `OPENAI_API_KEY` | — | real LLM |
| `OPENAI_MODEL` | gpt-4o-mini | |
| `OPENAI_MODEL_STRONG` | gpt-4o | 强模型节点 |
| `EMBEDDINGS_PROVIDER` | local-hash | RAG 向量 |
| `CHECKPOINTER` | sqlite | memory 适合测试 |
| `CHECKPOINTER_SQLITE_PATH` | ./data/checkpoints.db | |
| `LANGSMITH_TRACING` | false | 或 `LANGCHAIN_TRACING_V2` |
| `LANGSMITH_API_KEY` | — | |
| `LANGSMITH_PROJECT` | ops-agent | |

RAG 检索阈值等见 [rag-architecture-and-tests.md](rag-architecture-and-tests.md) § 配置。

`.env.example` 为模板；勿提交真实密钥。

---

## 5. LLM 与 Checkpointer

### 5.1 LLM_MODE

- **mock**：节点使用 `*_spec.py` 或 fixture 结构化输出（`graph_paths`、CI）
- **real**：`ChatOpenAI`（可配置 `openai_base_url`）

### 5.2 Checkpointer

- **sqlite**：默认持久化 thread
- **memory**：pytest / `run_scenarios` 常用，无磁盘副作用
- **redis**：多实例部署可选

`thread_id` 来自 `IncidentInput.thread_id` 或 UUID。

---

## 6. 测试

### 6.1 本组件测什么

- 路由可达性与 schema 序列化
- LangSmith 初始化与 env 别名（不污染其他测试）
- metrics 端点格式
- runner 与 API 集成的 smoke（`test_eval.py` 等）

### 6.2 测试文件

| 文件 | 说明 |
|------|------|
| `tests/test_tracing.py` | LangSmith / env cache |
| `tests/test_eval.py` | API 级 eval smoke |
| `tests/test_run_scenarios.py` | CLI + checkpoint 清理 |

图业务断言在 `tests/graph_paths/`，不在此重复。

---

## 7. Agent 改动同步指南

**通用要求**：每次合入修改后，在本文 **§10 版本注记** 追加一条修改摘要（日期 + 改动范围 + 关键行为变化）。

| 改动 | 必做 |
|------|------|
| **新 HTTP 端点** | `main.py` + `schemas.py` + `runner` 封装 + 测试 |
| **新 env 变量** | `config.py` + `.env.example` + 本文 §4 表 |
| **改 checkpointer** | `memory/checkpointer.py` + CI 文档（`CHECKPOINTER=memory`） |
| **改 tracing** | `tracing.py` + `test_tracing.py`（注意 `get_env_var` cache） |
| **改 DiagnoseResponse 字段** | `schemas.py` + `runner._to_response` + 下游 OpenAPI 消费者 |

---

## 8. 验证命令

```bash
uvicorn app.main:app --port 8000
curl -s localhost:8000/readyz | jq .

.venv/bin/pytest tests/test_tracing.py tests/test_eval.py -q
```

---

## 9. 交叉引用

- 图与 HITL：[`graph-agent-architecture.md`](graph-agent-architecture.md)
- 配置相关的 RAG：[`rag-architecture-and-tests.md`](rag-architecture-and-tests.md)
- 总览：[`architecture.md`](architecture.md)

---

## 10. 版本注记

- **2026-06-30**：`app/llm/provider.py` 新增 `invoke_structured()` 与 `ensure_json_in_messages()`，适配 DashScope qwen3.x 在 `json_object` 模式下要求 messages 含 `json` 字样的 API 规则。
