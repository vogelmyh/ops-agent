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
| `OPENAI_API_KEY` | — | real LLM（chat；OpenAI-compatible，推荐 DeepSeek） |
| `OPENAI_BASE_URL` | https://api.openai.com/v1 | chat API base（推荐 `https://api.deepseek.com`） |
| `OPENAI_MODEL` | gpt-4o-mini | 默认 chat 模型（推荐 `deepseek-v4-flash`） |
| `OPENAI_MODEL_STRONG` | gpt-4o | 强模型节点（推荐 `deepseek-v4-pro`） |
| `EMBEDDINGS_PROVIDER` | local-hash | RAG 向量（可与 chat 拆供应商） |
| `EMBEDDINGS_MODEL` | text-embedding-v4 | embedding 模型（Qwen 常用 `text-embedding-v3`） |
| `QWEN_API_KEY` | — | `EMBEDDINGS_PROVIDER=qwen` 时必填 |
| `QWEN_BASE_URL` | DashScope compatible `/v1` | embedding endpoint |
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
- **real**：`ChatOpenAI`（可配置 `openai_base_url` / `openai_model`）

**推荐组合**：chat 走 DeepSeek V4（`OPENAI_BASE_URL=https://api.deepseek.com`，`deepseek-v4-flash` / `deepseek-v4-pro`）；embedding 走 Qwen DashScope（`EMBEDDINGS_PROVIDER=qwen`，`QWEN_API_KEY`）。两套凭证互不干扰。DeepSeek chat 在 `get_chat_model()` 默认关闭 thinking；`invoke_structured()` 对 DeepSeek 使用 `json_mode`（API 不支持 `json_schema`），并补 JSON 提示。SDK/`parsing_error` 降级时 fallback 仍绑定 `json_object`，并在解析前去除 markdown JSON 围栏。

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
| `tests/test_llm_provider.py` | LLM 供应商检测、`invoke_structured` 路由、JSON 围栏剥离 |
| `tests/test_decide_spec.py` | `DecideAssessment` LLM JSON coerce |
| `tests/test_run_scenarios.py` | CLI + checkpoint 清理；`check_dec_01_passed` 契约 |

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

- **2026-07-07**：`get_checkpointer()` 使用带 `allowed_msgpack_modules` 的 `JsonPlusSerializer`，显式允许 `IncidentInput` / `Evidence` checkpoint 反序列化，消除 LangGraph 运行警告。
- **2026-07-01**：`DiagnoseResponse` / `AgentState`：`novel_scenario` → **`runbook_available`**（语义取反，true = 有可用 runbook）；`novel_reason` → **`runbook_unavailable_reason`**。`runner._to_response` 与 OpenAPI 字段已同步；无向后兼容别名。
- **2026-07-01**：图节点 `verify_remediation` 替代 `eval_remediation`；state 观测字段 `remediation_verify_reasoning`（`remediation_eval_reasoning` 为兼容别名）。
- **2026-06-30**：`RemediationEvalAssessment` coerce（缺省 `reasoning`、字段别名）见 [`decide-remediation-architecture.md`](decide-remediation-architecture.md) §10；`verify_remediation` 节点经 `invoke_structured()` 继承。
- **2026-06-30**：`invoke_structured()` fallback 收紧：plain 重试仍绑 `json_object`；`strip_json_markdown()` 去围栏；区分 JSON 语法错误与 schema 校验失败。`DecideAssessment` coerce 见 [`decide-remediation-architecture.md`](decide-remediation-architecture.md) §10。
- **2026-06-30**：推荐 **DeepSeek V4 chat + Qwen embedding** 组合：`get_chat_model()` 对 DeepSeek 默认 `thinking: disabled`；`invoke_structured()` 对 DeepSeek 使用 `json_mode` + JSON 提示（不走 DashScope fallback）。见 `.env.example`。
- **2026-06-30**：`invoke_structured()` 在 SDK `ValidationError` 时降级 plain invoke；裸 rubric 数组包装见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9。
- **2026-06-30**：`invoke_structured()` 对 DashScope/Qwen 增加 `include_raw` 与 `AIMessage` 文本 JSON 兜底解析；嵌套 rubric 归一化见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9。
- **2026-06-30**：`app/llm/provider.py` 新增 `invoke_structured()` 与 `ensure_json_in_messages()`，适配 DashScope qwen3.x 在 `json_object` 模式下要求 messages 含 `json` 字样的 API 规则。
