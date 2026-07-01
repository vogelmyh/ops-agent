# ops-agent 项目架构总览

> **读者**：开发者 + Cursor Agent。  
> **用途**：理解项目全貌、组件边界、运行与测试入口；细节见各组件文档。  
> **场景目录**（测什么）：[`test-scenario-trajectories.md`](test-scenario-trajectories.md) — 本文不重复场景 ID 表。

---

## 1. 项目定位

**ops-agent** 是基于 **LangGraph + FastAPI** 的电商 SaaS 运维诊断与修复 Agent：

- 输入：故障工单（`service` + `description`）
- 采集遥测 → 诊断 → 决策 →（可选审批）→ 执行写工具 → 验收 → 总结
- 知识库缺口时：HITL 写回 runbook 并入库

默认 **mock-first**：无 API Key、无 Java 后端亦可离线运行。

**相关仓库**

| 仓库 | 角色 |
|------|------|
| **ops-agent**（本仓库） | Agent、RAG、图编排、API |
| **ops-backend** | Java 生产型后端契约（可选联调） |
| **ops-backend-simulator** | 有状态 HTTP 后端替身（write→read 闭环、混沌场景） |

---

## 2. 组件地图

```text
                    ┌─────────────────────────────────────┐
                    │  API & Runtime                      │
                    │  main.py, config, llm, checkpoint   │
                    └──────────────┬──────────────────────┘
                                   │ POST /diagnose …
                    ┌──────────────▼──────────────────────┐
                    │  LangGraph 诊断主图                  │
                    │  triage → retrieve_runbooks → diagnose …  │
                    └─┬────────┬──────────┬───────────┬───┘
                      │        │          │           │
         ┌────────────▼──┐ ┌───▼────┐ ┌───▼────┐ ┌───▼──────────┐
         │ RAG           │ │ Decide │ │ Backend│ │ KB Lifecycle │
         │ 检索+覆盖裁决  │ │ +工具  │ │ Adapters│ │ HITL写回     │
         └───────────────┘ └────────┘ └────────┘ └──────────────┘
```

| 组件 | 文档 | 代码主路径 |
|------|------|------------|
| **API 与运行时** | [`api-runtime-architecture.md`](api-runtime-architecture.md) | `app/main.py`, `config.py`, `llm/`, `memory/` |
| **LangGraph 诊断主图** | [`graph-agent-architecture.md`](graph-agent-architecture.md) | `app/graph/builder.py`, `runner.py`, `nodes/triage|diagnose|…` |
| **RAG** | [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) | `app/rag/`, `retrieve_runbooks`, `diagnose_runbook_step`, `runbook_eval_policy` |
| **决策与修复** | [`decide-remediation-architecture.md`](decide-remediation-architecture.md) | `decide*`, `tools/`, `eval_remediation`, `approve` |
| **后端适配** | [`backend-adapters-architecture.md`](backend-adapters-architecture.md) | `app/adapters/`, `schemas` 遥测模型 |
| **KB 知识闭环** | [`kb-lifecycle-architecture.md`](kb-lifecycle-architecture.md) | `summarize` → notes → draft → review → `ingest_runbook` |
| **场景测试目录** | [`test-scenario-trajectories.md`](test-scenario-trajectories.md) | REM/HITL/LOOP/DEC/KB/RAG 场景 ID |

RAG 语料运维补充：[`rag-eval-corpus.md`](rag-eval-corpus.md)。

---

## 3. 总体流程

### 3.1 主路径（默认图）

```text
START
  → triage                    # 解析 incident，定 service
  → retrieve_runbooks         # 检索 top-K runbook
  → diagnose                  # Step1 rubric + RCA + 置信度
       ├─ confidence 不足 → summarize
       └─ else → decide
       ├─ uncertain（tool_select 降级）/ out_of_scope → summarize → [novel? → KB HITL] → END
       ├─ actionable + needs_approval → approve → write_tools
       └─ actionable → write_tools
  → eval_remediation          # 写后验收
       ├─ resolved → summarize → …
       └─ not resolved & attempt < max → retrieve_runbooks（react 环）
```

默认 `max_remediation_attempts=3`（`app/config.py`）。

### 3.2 HITL 中断点

| 中断节点 | API 恢复 | Response status |
|----------|----------|-----------------|
| `approve` | `POST /approve` | `awaiting_approval` |
| `request_runbook_notes` | `POST /runbooks/notes` | `awaiting_runbook_notes` |
| `review_runbook` | `POST /runbooks/review` | `awaiting_runbook_review` |

Checkpoint 线程 ID：`thread_id`（`app/graph/runner.py`）。

### 3.3 关键概念区分

| 概念 | 含义 |
|------|------|
| `novel_scenario` | KB 是否覆盖（diagnose Step1 裁决） |
| `decide_outcome` | 是否可执行写工具（`actionable` / `skipped_low_confidence` / `uncertain` / `out_of_scope`） |
| `needs_approval` | 高风险、novel 或二次修复未恢复等策略，不等于不可执行 |

---

## 4. 使用说明

### 4.1 快速开始

```bash
cd ops-agent
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4.2 常用模式

| 目的 | 环境 |
|------|------|
| 离线开发 / CI | `BACKEND_MODE=mock` `LLM_MODE=mock` `CHECKPOINTER=memory` |
| 真实 LLM 表征 | `LLM_MODE=real` + `OPENAI_API_KEY`（推荐 DeepSeek V4 chat） |
| Simulator 联调 | `BACKEND_MODE=real` `BACKEND_BASE_URL=http://127.0.0.1:8081` — 见 [backend-adapters](backend-adapters-architecture.md) |
| 语义 RAG 评测 | `EMBEDDINGS_PROVIDER=qwen` + `QWEN_API_KEY` + `scripts/rag_eval.py`（chat 与 embedding 可拆供应商） |

### 4.3 脚本入口

| 脚本 | 用途 |
|------|------|
| `scripts/demo.py` | 三场景离线演示 |
| `scripts/run_scenarios.py` | 场景表征（步进 JSON，`rag` 观测块） |
| `scripts/rag_eval.py` | RAG golden 指标报告 |
| `eval/run_eval.py` | 15 场景 LLM 评测（dataset.jsonl） |

### 4.4 API 摘要

详见 [`api-runtime-architecture.md`](api-runtime-architecture.md)。

| 路径 | 说明 |
|------|------|
| `POST /diagnose` | 启动/继续至下一中断或完成 |
| `POST /approve` | 操作审批 |
| `POST /runbooks/notes` | Runbook 备注 |
| `POST /runbooks/review` | Runbook 审核 |
| `GET /runs/{thread_id}` | 图状态快照 |

---

## 5. 测试说明（总览）

**原则**：场景「测什么」见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md)；各组件「怎么测」见组件文档 §6；本文只给分层索引。

```text
Layer 0  单元 / 策略        tests/test_rag.py, test_runbook_eval_policy.py, …
Layer 1  图路径契约          tests/graph_paths/          (mock LLM, 固定路由)
Layer 2  RAG golden         tests/rag_eval/             (检索 / coverage / real LLM smoke)
Layer 3  集成 / 节点         tests/test_rag_integration.py, test_eval.py
Layer 4  场景表征            scripts/run_scenarios.py, eval/run_eval.py
```

### 5.1 修改后推荐命令

```bash
# 全量
.venv/bin/pytest tests/ -q

# 图路径（不动 RAG golden）
.venv/bin/pytest tests/graph_paths/ -q

# RAG
.venv/bin/pytest tests/rag_eval/ -q

# 场景冒烟（mock LLM）
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios KB-01 --mock-llm
```

### 5.2 各组件测试入口

| 组件 | 主测试 |
|------|--------|
| API / tracing | `tests/test_tracing.py`, `tests/test_eval.py` |
| 诊断主图 | `tests/graph_paths/` |
| RAG | `tests/rag_eval/`, `tests/test_hybrid_retrieval.py`, `tests/test_rag_integration.py` |
| 决策与修复 | `tests/graph_paths/test_rem|dec|loop.py`, `eval/run_eval.py` |
| 后端适配 | 经 graph_paths + integration 间接覆盖；simulator 见 `ops-backend-simulator/tests/` |
| KB 闭环 | `tests/graph_paths/test_kb.py`, `test_hitl.py` |
| 场景目录 | `test-scenario-trajectories.md` + `run_scenarios.py` |

---

## 6. 数据目录

| 路径 | 内容 |
|------|------|
| `data/runbooks/` | Runbook 语料（55 篇，RAG 索引源） |
| `data/incidents/` | 可选 incident 文档（ingest） |
| `data/.rag_indexed_*` | 向量索引完成标记 |
| `eval/dataset.jsonl` | 15 场景 eval 数据集 |

---

## 7. Agent 修改导航

1. 先在本表定位**组件** → 打开对应组件文档的 **「Agent 改动同步指南」** 章节（各文档节号不同，以标题为准）  
2. 若改图路由 / 新节点 → [`graph-agent-architecture.md`](graph-agent-architecture.md)  
3. 若改 RAG → [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md)  
4. 若改工具 / decide → [`decide-remediation-architecture.md`](decide-remediation-architecture.md)  
5. 若改 mock 遥测 / simulator 联调 → [`backend-adapters-architecture.md`](backend-adapters-architecture.md)  
6. 若改 API / 环境变量 → [`api-runtime-architecture.md`](api-runtime-architecture.md)  
7. 若改场景预期 → [`test-scenario-trajectories.md`](test-scenario-trajectories.md)（场景表，非实现）  
8. **合入前**：在涉及组件文档的 **版本注记 / 变更记录** 追加修改摘要（各组件 §「改动同步指南」均有此要求）

---

## 8. 文档索引

完整列表与阅读路径：[`docs/README.md`](README.md)。

| 文档 | 类型 |
|------|------|
| **本文** | 总览 |
| [`graph-agent-architecture.md`](graph-agent-architecture.md) | 组件 |
| [`decide-remediation-architecture.md`](decide-remediation-architecture.md) | 组件 |
| [`backend-adapters-architecture.md`](backend-adapters-architecture.md) | 组件 |
| [`kb-lifecycle-architecture.md`](kb-lifecycle-architecture.md) | 组件 |
| [`api-runtime-architecture.md`](api-runtime-architecture.md) | 组件 |
| [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) | 组件 |
| [`rag-eval-corpus.md`](rag-eval-corpus.md) | RAG 补充 |
| [`test-scenario-trajectories.md`](test-scenario-trajectories.md) | 场景目录 |
| [`../../ops-backend-simulator/README.md`](../../ops-backend-simulator/README.md) | Simulator 实现细节（外部） |

---

## 9. 版本注记

- **2026-07-01**：主图 `retrieve_runbooks` + `diagnose` 三步；KB-01 `skipped_low_confidence`、KB-02 novel approve；组件图与 `decide_outcome` 枚举已同步。
- **2026-06-30**：`RemediationEvalAssessment` coerce（`eval_schemas`）修复 DeepSeek `json_mode` 下 `eval_remediation` 缺 `reasoning` 硬崩；见 [`decide-remediation-architecture.md`](decide-remediation-architecture.md) §10。
- **2026-06-30**：结构化输出 fallback 收紧 + `DecideAssessment` coerce + DEC-01 场景断言对齐 novel 写回链；详见 [`api-runtime-architecture.md`](api-runtime-architecture.md) §10、[`decide-remediation-architecture.md`](decide-remediation-architecture.md) §10、[`test-scenario-trajectories.md`](test-scenario-trajectories.md) §变更记录。
- **2026-06-30**：推荐 **DeepSeek V4 chat + Qwen embedding**；`invoke_structured()` 供应商分流见 [`api-runtime-architecture.md`](api-runtime-architecture.md) §10、[`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9。
- 2026-06-30：文档规范 — 各组件 §「改动同步指南」要求每次修改后追加版本注记/变更记录；RAG eval 重构摘要见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9。
- 2026-06：文档体系初版（总览 + 5 组件文档 + 已有 RAG / 场景目录）。
