# LangGraph 诊断主图 — 架构与测试

> **读者**：开发者 + Cursor Agent。  
> **总览**：[`architecture.md`](architecture.md)  
> **场景目录**：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)

---

## 1. 职责

编排从 **incident 输入** 到 **总结 / KB 写回** 的完整诊断图：

- 服务识别（`triage`）
- 与 RAG 节点衔接（`retrieve_runbooks` — 细节见 [RAG 文档](rag-architecture-and-tests.md)）
- LLM 诊断三步（`diagnose`：runbook rubric → RCA → 置信度）
- 路由到决策、修复、总结子图（`decide`, `write_tools`, `verify_remediation`, `summarize`）
- HITL 中断与 checkpoint 恢复（`approve`, KB 节点）

**不负责**：RAG 检索实现、写工具 HTTP 调用、LLM provider 初始化（见对应组件文档）。

---

## 2. 流程

### 2.1 节点与边（`app/graph/builder.py`）

```text
triage
  → retrieve_runbooks
  → diagnose
       ├─ confidence < threshold → summarize
       └─ else → decide
       ├─ route_after_decide: out_of_scope | uncertain | skipped → summarize
       ├─ route_after_decide: actionable + needs_approval → approve → write_tools
       └─ route_after_decide: actionable → write_tools
  → verify_remediation
       ├─ route_after_verify_remediation: resolved → summarize
       └─ not resolved & attempt < max → retrieve_runbooks（react）
  → summarize
       └─ route_after_summarize: runbook_available=false → request_runbook_notes → … → ingest_runbook
```

### 2.2 采集子流程（`collection.collect`）

`retrieve_runbooks` 前均会调用 `app/graph/collection.py`：

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
| retrieve_runbooks | `app/graph/nodes/retrieve_runbooks.py` |
| diagnose | `app/graph/nodes/diagnose.py`, `runbook_coverage.py`, `diagnose_spec.py` |
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
| `symptom_query`, `runbook_candidates` | retrieve_runbooks | 检索 |
| `runbook_available`, `runbook_unavailable_reason`, `relevant_runbook`, `selected_runbook_id`, `match_gate_reason` | diagnose coverage | KB 覆盖 |
| `root_cause`, `evidence`, `confidence_rubric`, `confidence_gate_reason`, `confidence_sufficient` | diagnose | 诊断 |
| `decision_class`, `decide_outcome` | decide | 路由 |
| `remediation_attempt`, `incident_resolved` | verify_remediation | react 环 |

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
- **react 环**：未解决时是否回到 `retrieve_runbooks` 且 `remediation_attempt` 递增

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
| **改 run_scenarios 场景断言** | `scripts/run_scenarios.py` + `tests/test_run_scenarios.py` + [`test-scenario-trajectories.md`](test-scenario-trajectories.md) |
| **改 LLM 供应商 / structured output 路由** | `app/llm/provider.py` + [`api-runtime-architecture.md`](api-runtime-architecture.md) §4/§5/§10；eval/decide 节点经 `invoke_structured()` 自动继承 |
| **改 DecideAssessment coerce** | `decide_spec.py` + [`decide-remediation-architecture.md`](decide-remediation-architecture.md) §7/§10 |
| **改 RemediationEvalAssessment coerce** | `eval_schemas.py` + [`decide-remediation-architecture.md`](decide-remediation-architecture.md) §7/§10 |
| **新增/删除节点** | 改 `builder.py` 边与 conditional edges；更新 `state.py` 字段；补 `graph_paths` 或集成测试 |
| **改路由函数** | 检查 `route_after_decide` / `route_after_verify_remediation` / `route_after_summarize` 全分支 |
| **新 HITL 中断** | `interrupt_before` 列表、`runner._status_from_pending`、`main.py` 新 resume 端点 |
| **改 collection 字段** | 同步 `diagnose` / `retrieve_runbooks` prompt 与 `mock_data` 投影 |
| **改 retrieve / coverage / RAG 裁决** | 见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §5，非本组件 |
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

- **2026-07-01**：`novel_scenario` / `novel_reason` 重命名为 `runbook_available` / `runbook_unavailable_reason`（布尔语义取反：true = 有可用 runbook）。diagnose runbook 路径跳过 confidence LLM；decide 拆 runbook/explore 双 prompt（探索路径不传 runbook）。详见 [`archive/design-diagnose-runbook-split.md`](archive/design-diagnose-runbook-split.md)。
- **2026-07-07**：LOOP-03 绑定 `cascade-exhaust`；`verify_remediation` 按 metric 层验收；chaos runbook 已从 KB 移除。`run_scenarios` 默认 stdout 紧凑摘要 + `data/scenario_runs/` 报告文件（`--full-json` 恢复旧行为）。
- **2026-07-03**：文档明确 KB-01/KB-02 在 `run_scenarios` 为固定 **mock smoke**（非 real LLM 表征）；real LLM 表征仅 DEC/LOOP。见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md) §KB、`run_scenarios.py --help`。
- **2026-07-03**：`RootCauseDraft` 增加 `coerce_root_cause_draft` / `normalize_evidence_source`，将 LLM 自然语言 source（如 `Application Logs`）映射为 `EvidenceSource` 枚举；`RCA_SYSTEM_PROMPT` 补充机器标签示例 JSON，修复 real LLM 场景表征在 `diagnose` RCA 阶段的 schema 校验失败。`run_scenarios` KB runner 使用 `_isolated_mock_backend_env()`，避免 mock env 污染后续 real LLM 场景。
- **2026-07-02**：remediation 重入时 RCA 注入 `RCA_RETRY_GUIDANCE`；删除纯观测字段 `needs_human_review`、`diagnosis_reasoning`、`runbook_eval_reasoning`（统一 `match_gate_reason`）。
- **2026-07-01**：命名清理：`eval_remediation` → `verify_remediation`；diagnose coverage / rca / confidence；双轨 RAG 测试见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §4。
- **2026-07-01**：主图重构：`eval_runbook` → `retrieve_runbooks`（纯检索）；`eval_diagnosis` 并入 `diagnose` 三阶段（coverage runbook rubric + finalize、rca、confidence rubric）；`confidence < diagnosis_confidence_threshold` 时 `decide_outcome=skipped_low_confidence` 直进 summarize。同步指南与 react 环文档已对齐。
- **2026-06-30**：`RemediationEvalAssessment` coerce（`eval_schemas.coerce_remediation_eval_assessment`）见 decide-remediation §10。
- **2026-06-30**：DEC-01 `check_dec_01_passed` 对齐 `runbook_available` 写回 HITL 路径；见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md) §DEC-01。
- **2026-06-30**：`invoke_structured()` fallback 绑定 `json_object` + markdown 围栏剥离；`DecideAssessment` coerce 见 decide-remediation §10。
- **2026-06-30**：`invoke_structured()` 按供应商分流：DashScope/Qwen chat → JSON 提示 + fallback；DeepSeek → `json_mode` + JSON 提示；其他 → 默认 `with_structured_output`。
- **2026-06-30**：eval/decide 节点的 structured output 调用统一改为 `invoke_structured()`，兼容 qwen3.7-plus（DashScope）JSON 模式约束。
