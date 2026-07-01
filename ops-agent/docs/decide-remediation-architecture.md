# 决策与修复 — 架构与测试

> **读者**：开发者 + Cursor Agent。  
> **总览**：[`architecture.md`](architecture.md)  
> **场景目录**：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)（REM / DEC / LOOP）

---

## 1. 职责

在诊断之后决定 **能否执行写操作**，并驱动 **工具调用 → 写后验收 → react 环**：

- **decide**：`actionable` | `uncertain` | `out_of_scope` + `recommendations` / `knowledge_gaps`
- **approve**：高风险或策略触发的 HITL 闸门
- **write_tools**：LangGraph `ToolNode` 执行写工具
- **eval_remediation**：对比写前后遥测，判定 `incident_resolved`

---

## 2. 流程

```text
diagnose
       ├─ confidence 不足 → summarize
       └─ else → decide
            ├─ out_of_scope → summarize（无写工具）
            └─ actionable
                 ├─ needs_approval → approve [interrupt] → write_tools
                 └─ else → write_tools
  → eval_remediation
       ├─ incident_resolved → summarize
       └─ else & attempt < max → retrieve_runbooks（重新检索 + 可能再次 decide）
```

### 2.1 decide 输入输出

- **输入**：`root_cause`, `evidence`, `relevant_runbook`, `novel_scenario`, `collected_data`（信任上游 diagnose，不重复校验诊断置信）
- **输出**：`decision_class`, `decide_outcome`, `escalation_hint`, `recommendations`, `knowledge_gaps`
- **实现**：`app/graph/nodes/decide.py` + `app/graph/decide_spec.py`（mock LLM 结构化输出）

### 2.2 审批策略（`app/tools/policy.py`）

`compute_needs_approval` 在 **写工具执行前** 判定：

- 任一 **HIGH** 风险工具（如 `rollback_deployment`）
- `remediation_attempt >= 1` 且仍未 `incident_resolved`
- `novel_scenario` 为真（KB 无覆盖时所有写操作需人审）

`needs_human_review` 仅表示诊断置信不足（观测）；**不**再参与 approve。

### 2.3 write_tools

- 工具定义：`app/tools/write_tools.py`
- 经 `backend_client` 调用 mock 或 real 后端（见 [backend-adapters](backend-adapters-architecture.md)）
- 结果以 `ToolMessage` 进入 `messages`，API 通过 `execution_results` 暴露

### 2.4 eval_remediation

- 再次 `collection.collect` 获取写后遥测
- LLM（或 mock）对比前后状态 → `incident_resolved`, `remediation_eval_reasoning`
- 递增 `remediation_attempt`，追加 `remediation_history`

---

## 3. 代码映射

| 模块 | 路径 |
|------|------|
| decide 节点 | `app/graph/nodes/decide.py` |
| decide mock 规格 | `app/graph/decide_spec.py` |
| eval_remediation | `app/graph/nodes/eval_remediation.py` |
| approve | `app/graph/nodes/approve.py` |
| 写工具 | `app/tools/write_tools.py` |
| 风险策略 | `app/tools/policy.py` |
| 图边 | `app/graph/builder.py` (`route_after_decide`, `route_after_eval_remediation`) |
| 离线 eval | `eval/run_eval.py`, `eval/dataset.jsonl` |

---

## 4. 配置与 State

| 变量 / 字段 | 说明 |
|-------------|------|
| `MAX_REMEDIATION_ATTEMPTS` | react 上限（默认 3） |
| `decide_outcome` | 路由主开关 |
| `needs_approval` | 是否中断在 approve |
| `incident_resolved` | eval_remediation 输出 |
| `remediation_attempt` | 当前尝试次数 |
| `messages` | 含 tool_calls / ToolMessage |

---

## 5. 数据契约（写工具）

写工具统一 POST 形态（real 后端 / simulator）：

`POST /api/v1/ops/{action}` → `OperationResult`（`SUCCEEDED` / `FAILED` + message）

工具名与 action 映射见 `write_tools.py` 与 simulator README。

---

## 6. 测试

### 6.1 本组件测什么

- **decide 三分支**：mock LLM 固定 `decide_outcome` 后是否进入 summarize / approve / write_tools
- **审批**：HIGH 风险工具、`novel_scenario`、二次修复未恢复时是否 `needs_approval`
- **eval_remediation**：mock 写后遥测下 `incident_resolved` 与 react 回边
- **LOOP**：混沌 / 不可恢复场景下诚实终止（常与 simulator 或 `mock_remediation` 配合）

### 6.2 测试文件

| 层 | 路径 |
|----|------|
| 图路径 | `tests/graph_paths/test_rem.py`, `test_dec.py`, `test_loop.py`, `test_hitl.py` |
| 策略单元 | `tests/test_policy.py`（若有）, `decide` / `eval_remediation` 相关 tests |
| LLM eval | `eval/run_eval.py` + `eval/dataset.jsonl`（15 场景，需 `LLM_MODE=real`） |

场景轨迹表：**不重复**，见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md)。

### 6.3 表征

```bash
# mock LLM 图路径
.venv/bin/pytest tests/graph_paths/test_rem.py -q

# 真实 LLM + simulator（LOOP 等）
BACKEND_MODE=real BACKEND_BASE_URL=http://127.0.0.1:8081 \
  .venv/bin/python scripts/run_scenarios.py --scenarios LOOP-01
```

---

## 7. Agent 改动同步指南

**通用要求**：每次合入修改后，在本文 **§10 版本注记** 追加一条修改摘要（日期 + 改动范围 + 关键行为变化）。

| 改动 | 必做 |
|------|------|
| **改 run_scenarios 场景断言** | `scripts/run_scenarios.py` + `tests/test_run_scenarios.py` + [`test-scenario-trajectories.md`](test-scenario-trajectories.md) §变更记录 |
| **改 DecideAssessment schema / coerce** | `decide_spec.py` → `coerce_decide_assessment()` + `tests/test_decide_spec.py`；`invoke_structured` 行为见 [`api-runtime-architecture.md`](api-runtime-architecture.md) |
| **改 RemediationEvalAssessment schema / coerce** | `eval_schemas.py` → `coerce_remediation_eval_assessment()` + `tests/test_eval_schemas.py` |
| **新写工具** | `write_tools.py` + `TOOL_RISK` + mock 后端 / simulator `apply_ops` + runbook 步骤 |
| **改 decide 逻辑** | `decide.py` + `decide_spec.py` mock 矩阵 + `test_dec.py` |
| **改审批规则** | `policy.compute_needs_approval` + `test_hitl.py` |
| **改验收标准** | `eval_remediation.py` + `mock_remediation` / simulator 写后投影 |
| **新 DEC/REM/LOOP 场景** | 更新 `test-scenario-trajectories.md` + graph_paths fixture |

---

## 8. 验证命令

```bash
.venv/bin/pytest tests/graph_paths/test_rem.py tests/graph_paths/test_dec.py tests/graph_paths/test_loop.py -q
LLM_MODE=real .venv/bin/python eval/run_eval.py   # 可选，需 API key
```

---

## 9. 交叉引用

- 主图：[`graph-agent-architecture.md`](graph-agent-architecture.md)
- 后端写路径：[`backend-adapters-architecture.md`](backend-adapters-architecture.md)
- API 审批端点：[`api-runtime-architecture.md`](api-runtime-architecture.md)
- 场景目录：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)

---

## 10. 版本注记

- **2026-07-01**：审批策略：`novel_scenario` 触发 approve；移除 `needs_human_review` 审批项。decide assessment 仅 `actionable | out_of_scope`（`uncertain` 仅 tool_select 代码降级）；decide 输入与 §6.1 测试说明已同步。
- **2026-06-30**：`RemediationEvalAssessment` 增加 `coerce_remediation_eval_assessment()`（缺省 `reasoning`、别名 `resolved`/`residual_symptoms` 归一化），修复 DeepSeek `json_mode` 下 `eval_remediation` 节点字段漂移硬崩。
- **2026-06-30**：`DecideAssessment` 增加 `coerce_decide_assessment()`（`classification`→`outcome`、列表字段与缺省 `reasoning` 归一化），修复 DeepSeek `json_mode` 下 decide 节点字段漂移硬崩。DEC-01 场景断言见 [`test-scenario-trajectories.md`](test-scenario-trajectories.md) §变更记录。
- **2026-06-30**：`invoke_structured()` 对 DeepSeek chat 使用 `json_mode` + thinking 关闭；`decide` / `eval_remediation` / `diagnose` 经此入口自动受益。详见 [`api-runtime-architecture.md`](api-runtime-architecture.md) §5.1、§10。
- **2026-06-30**：`decide.py`、`eval_remediation.py` 的 structured output 调用改为 `invoke_structured()`，与 `app/llm/provider.py` 的 DashScope JSON 提示兼容层对齐。
