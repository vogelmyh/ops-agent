# LangGraph 诊断主图 — 架构与测试

> **读者**：开发者 + Cursor Agent。  
> **总览**：[`architecture.md`](architecture.md)  
> **场景目录**：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)

---

## 1. 职责

编排从 **incident 输入** 到 **总结 / KB 写回** 的完整诊断图：

- 服务识别（`triage`）
- 与 RAG 节点衔接（`eval_runbook` — 细节见 [RAG 文档](rag-architecture-and-tests.md)）
- LLM 诊断与诊断评估（`diagnose`, `eval_diagnosis`）
- 路由到决策、修复、总结子图（`decide`, `write_tools`, `eval_remediation`, `summarize`）
- HITL 中断与 checkpoint 恢复（`approve`, KB 节点）

**不负责**：RAG 检索实现、写工具 HTTP 调用、LLM provider 初始化（见对应组件文档）。

---

## 2. 流程

### 2.1 节点与边（`app/graph/builder.py`）

```text
triage
  → eval_runbook
  → diagnose
  → eval_diagnosis
  → decide
       ├─ route_after_decide: uncertain | out_of_scope → summarize
       ├─ route_after_decide: actionable + needs_approval → approve → write_tools
       └─ route_after_decide: actionable → write_tools
  → eval_remediation
       ├─ route_after_eval_remediation: resolved → summarize
       └─ not resolved & attempt < max → eval_runbook（react）
  → summarize
       └─ route_after_summarize: novel_scenario → request_runbook_notes → … → ingest_runbook
```

### 2.2 采集子流程（`collection.collect`）

`eval_runbook` 与 `diagnose` 前均会调用 `app/graph/collection.py`：

- 按 `service` 拉取 logs / metrics / status / k8s_events 等
- 结果写入 `state.collected_data`，供症状抽取与诊断 prompt 使用

### 2.3 Runner 与 API 映射（`app/graph/runner.py`）

| 函数 | 用途 |
|------|------|
| `start_diagnosis` | 新 thread，`graph.invoke` 初始 state |
| `resume_graph` | `Command(resume=payload)` 恢复中断 |
| `resume_approval` / `resume_runbook_notes` / `resume_runbook_review` | 封装常见 HITL payload |

`DiagnoseResponse.status` 由 pending interrupt 节点映射（`awaiting_approval` 等）。

### 2.4 扩展位（未默认挂载）

`app/graph/extensions/investigation/` 含 `escalate` / `investigate_human` 等节点；`builder.py` 中注释为 `INVESTIGATE_EXTENSION`。挂载时需同步 `runner._status_from_pending` 与路由测试。

---

## 3. 代码映射

| 模块 | 路径 |
|------|------|
| 图构建 | `app/graph/builder.py` |
| 状态 | `app/graph/state.py` (`AgentState`) |
| 运行入口 | `app/graph/runner.py` |
| 采集 | `app/graph/collection.py` |
| triage | `app/graph/nodes/triage.py` |
| diagnose | `app/graph/nodes/diagnose.py` |
| eval_diagnosis | `app/graph/nodes/eval_diagnosis.py` |
| eval_runbook | `app/graph/nodes/eval_runbook.py` |
| summarize | `app/graph/nodes/summarize.py` |
| KB 节点 | `request_runbook_notes`, `draft_runbook`, `review_runbook`, `ingest_runbook` |
| 决策/修复 | 见 [decide-remediation-architecture.md](decide-remediation-architecture.md) |

---

## 4. 配置与 State

### 4.1 关键 State 字段（节选）

| 字段 | 设置方 | 用途 |
|------|--------|------|
| `incident`, `service` | triage | 输入 |
| `collected_data` | collection | 遥测 |
| `symptom_query`, `novel_scenario`, `novel_reason`, `relevant_runbook`, `selected_runbook_id`, `runbook_eval_reasoning` | eval_runbook | RAG（细节见 RAG 文档） |
| `root_cause`, `evidence`, `summary` | diagnose / summarize | 输出 |
| `needs_human_review` | eval_diagnosis | 审批策略输入 |
| `decision_class`, `decide_outcome` | decide | 路由 |
| `remediation_attempt`, `incident_resolved` | eval_remediation | react 环 |

完整定义：`app/graph/state.py`。

### 4.2 相关配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `MAX_REMEDIATION_ATTEMPTS` | 3 | react 环上限 |
| `CHECKPOINTER` | sqlite | 线程持久化 |

---

## 5. 测试

### 5.1 本组件测什么

- **路由契约**：给定 mock LLM 固定输出，图是否走到预期节点与 `status`
- **HITL 恢复**：approve / notes / review 后 state 与 response 字段
- **react 环**：未解决时是否回到 `eval_runbook` 且 `remediation_attempt` 递增

**不测**：RAG recall 数值（见 RAG 文档）、真实 LLM 措辞。

### 5.2 测试文件

| 文件 | 覆盖 |
|------|------|
| `tests/graph_paths/conftest.py` | mock LLM、checkpoint、scenario fixtures |
| `tests/graph_paths/test_rem.py` | REM-* 修复路径 |
| `tests/graph_paths/test_hitl.py` | HITL / 审批 |
| `tests/graph_paths/test_kb.py` | KB-* novel 写回 |
| `tests/graph_paths/test_loop.py` | LOOP-* react |
| `tests/graph_paths/test_dec.py` | DEC-* decide 分支 |
| `tests/test_run_scenarios.py` | `run_scenarios.py` CLI 冒烟 |

场景 ID 与轨迹说明：**仅**见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md)。

### 5.3 表征脚本

```bash
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py \
  --scenarios REM-01 --mock-llm --step-json
```

---

## 6. Agent 改动同步指南

**通用要求**：每次合入修改后，在本文 **§9 版本注记** 追加一条修改摘要（日期 + 改动范围 + 关键行为变化）。

| 改动类型 | 必做 |
|----------|------|
| **新增/删除节点** | 改 `builder.py` 边与 conditional edges；更新 `state.py` 字段；补 `graph_paths` 或集成测试 |
| **改路由函数** | 检查 `route_after_decide` / `route_after_eval_remediation` / `route_after_summarize` 全分支 |
| **新 HITL 中断** | `interrupt_before` 列表、`runner._status_from_pending`、`main.py` 新 resume 端点 |
| **改 collection 字段** | 同步 `diagnose` / `eval_runbook` prompt 与 `mock_data` 投影 |
| **改 eval_runbook / RAG 裁决** | 见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §5，非本组件 |
| **挂载 investigation 扩展** | 取消 `INVESTIGATE_EXTENSION` 注释块；补 LOOP/DEC 场景与 runner status |

**不要**在本文件重复维护 RAG 阈值或工具风险表 — 链到对应组件文档。

---

## 7. 验证命令

```bash
.venv/bin/pytest tests/graph_paths/ -q
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios REM-01,KB-01 --mock-llm
```

---

## 8. 交叉引用

- 总览：[`architecture.md`](architecture.md)
- RAG 节点：[`rag-architecture-and-tests.md`](rag-architecture-and-tests.md)
- 决策与工具：[`decide-remediation-architecture.md`](decide-remediation-architecture.md)
- KB 写回子链：[`kb-lifecycle-architecture.md`](kb-lifecycle-architecture.md)
- 场景目录：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)

---

## 9. 版本注记

- **2026-06-30**：eval/decide 节点的 structured output 调用统一改为 `invoke_structured()`，兼容 qwen3.7-plus（DashScope）JSON 模式约束。
