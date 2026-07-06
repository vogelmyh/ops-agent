# KB 知识闭环 — 架构与测试

> **读者**：开发者 + Cursor Agent。  
> **总览**：[`architecture.md`](architecture.md)  
> **RAG 读路径**（检索 / 覆盖裁决）：[`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) — 本文只讲 **写回与入库**

---

## 1. 职责

当 `novel_scenario=true`（KB 未覆盖）且主路径进入总结后，驱动 **人机协作** 将现场经验固化为 runbook 并 **写入 `data/runbooks/` + 触发 reindex**：

```text
summarize → request_runbook_notes → draft_runbook → review_runbook → ingest_runbook
```

与 RAG **读路径** 分离：读路径在 `retrieve_runbooks` + `diagnose` coverage；写路径在本子链。

---

## 2. 流程

### 2.1 触发条件

`route_after_summarize`（`builder.py`）在 `novel_scenario` 为真时进入 KB 子链，否则直接 `END`。

### 2.2 节点说明

| 节点 | 行为 | 中断 |
|------|------|------|
| `summarize` | 生成 `summary` / `root_cause` 等 | 否 |
| `request_runbook_notes` | 等待运维补充上下文 | **是** → `POST /runbooks/notes` |
| `draft_runbook` | LLM 根据 notes + 诊断生成 `runbook_draft` | 否 |
| `review_runbook` | 等待审核 | **是** → `POST /runbooks/review` |
| `ingest_runbook` | 审核通过后写盘 + `reindex()` | 否 |

### 2.3 ingest 规则（`ingest_runbook.py`）

- 仅当 `runbook_approved=true` 且 `runbook_draft` 非空
- 从 draft 首行 `# title` 生成 slug：`{service}-{slug}.md`
- 写入 `data/runbooks/`，调用 `app/rag/ingest.reindex()`
- 设置 `runbook_saved_path`

**同一索引**：新 runbook 进入与线上一致的 RAG 索引（无独立 eval index）。

---

## 3. 代码映射

| 模块 | 路径 |
|------|------|
| summarize | `app/graph/nodes/summarize.py` |
| request_runbook_notes | `app/graph/nodes/request_runbook_notes.py` |
| draft_runbook | `app/graph/nodes/draft_runbook.py` |
| review_runbook | `app/graph/nodes/review_runbook.py` |
| ingest_runbook | `app/graph/nodes/ingest_runbook.py` |
| 路由 | `app/graph/builder.py` (`route_after_summarize`) |
| 索引 | `app/rag/ingest.py`, `app/rag/store.py` |

---

## 4. 配置与 State

| 字段 | 说明 |
|------|------|
| `novel_scenario`, `novel_reason` | 来自 diagnose coverage（runbook rubric + finalize），决定是否进入 KB 链 |
| `runbook_notes` | HITL 输入 |
| `runbook_draft` | LLM 草稿 |
| `runbook_approved` | 审核结果 |
| `runbook_saved_path` | ingest 输出路径 |

API 恢复：`runner.resume_runbook_notes` / `resume_runbook_review`（见 [api-runtime](api-runtime-architecture.md)）。

---

## 5. 测试

### 5.1 本组件测什么

- `novel_scenario` 为真时是否进入 notes → draft → review → ingest
- 中断与 resume 后 `status` 与 state 字段
- ingest 后文件存在且 `reindex` 可被后续 RAG 检索（可选集成断言）

### 5.2 测试文件

| 文件 | 场景 |
|------|------|
| `tests/graph_paths/test_kb.py` | KB-* |
| `tests/graph_paths/test_hitl.py` | 与审批交织的 HITL |

场景定义：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)（KB 节）。

### 5.3 表征

**KB 在 `run_scenarios` 中仅为 mock smoke**（runner 内固定 `mock` LLM + `mock` backend），不用于 real LLM 表征。图路由契约见 `graph_paths/test_kb.py`；novel / coverage 质量见 RAG golden。

```bash
# KB mock smoke（会写 data/runbooks/，跑后 git status）
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios KB-01 KB-02
```

---

## 6. Agent 改动同步指南

**通用要求**：每次合入修改后，在本文 **§9 版本注记** 追加一条修改摘要（日期 + 改动范围 + 关键行为变化）。

| 改动 | 必做 |
|------|------|
| **改 KB 链路由** | `builder.py` + `test_kb.py` |
| **改 draft prompt / 格式** | `draft_runbook.py`；确保 ingest slug 规则仍适用 |
| **改 ingest 路径或 reindex** | `ingest_runbook.py` + RAG ingest 文档 |
| **新 KB 场景** | `test-scenario-trajectories.md` KB 表 + graph_paths fixture |
| **novel 判定逻辑** | 改 **RAG** `runbook_coverage` / `runbook_eval_policy`，非本链 |

---

## 7. 验证命令

```bash
.venv/bin/pytest tests/graph_paths/test_kb.py -q
```

---

## 8. 交叉引用

- RAG 读路径与覆盖：[`rag-architecture-and-tests.md`](rag-architecture-and-tests.md)
- 主图：[`graph-agent-architecture.md`](graph-agent-architecture.md)
- API：[`api-runtime-architecture.md`](api-runtime-architecture.md)
- 语料生成（批量 runbook，非 HITL）：[`rag-eval-corpus.md`](rag-eval-corpus.md)
- 场景目录：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)

---

## 9. 版本注记

### 2026-07-03 · KB run_scenarios 定位文档化

- 明确 KB-01/KB-02 在 `run_scenarios.py` 为 **mock smoke**，非 real LLM 表征；见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md) §KB。

### 2026-07-01 · 命名清理（coverage 来源表述）

- 读路径表述统一为 `retrieve_runbooks` + diagnose **coverage**；与 RAG 文档 §2 对齐。

- `novel_scenario` 改由 diagnose coverage 写入（非图节点 `eval_runbook`）。
- KB-01：低置信 `skipped_low_confidence` 仍进入 summarize → KB 写回链。
- KB-02：novel + actionable 需先 `approve` 再 write，修复后同样进入写回链。
