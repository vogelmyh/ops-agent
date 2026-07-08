# 归档设计：runbook / 探索路径二分（diagnose + decide）

> **状态**：**已实现**（2026-07-01），归档备查。  
> **分支**：`refactor/rag-diagnose-decide-pipeline`

---

## 背景问题

real LLM 场景表征（DEC-01 / LOOP-02 / LOOP-03 / DEC-02）常在 `diagnose` 阶段因 **confidence rubric**（尤其 `alternative_excluded=FAIL`）得到 `skipped_low_confidence`，未进入 `decide`。  
根因之一：coverage 已判定 runbook 可用，但 `_run_confidence` 仅看 LLM 生成的 `root_cause` + `evidence`，**不看 runbook 评估结果**。

次要问题：`decide` 在 `runbook_available=false` 时仍向 LLM 传入 `Relevant runbook: (none)`，未做到「无 runbook 则后续流程不使用 runbook」的严格二分。

---

## 核心原则

1. **不拆三态**：沿用现有 coverage finalize 判决（`runbook_available` / `relevant_runbook`），不引入「严格有 / 模糊有 / 无」第三条路径。
2. **状态机清晰**：全局二分 = **runbook 路径** vs **探索路径**；开关统一为 `runbook_available`（与 `relevant_runbook` 绑定）。
3. **runbook 是 coverage 通过后的运维知识锚点**；通过后应信任 coverage，不再用独立 confidence LLM 二审。
4. **严格可见性**：`runbook_available=false` → 自 `decide` 起 **不向 LLM 暴露 runbook 正文**；`runbook_available=true` → `decide` 可引用 validated runbook。
5. **react / 重试**：本轮**不改**；每轮仍 `retrieve_runbooks → diagnose(coverage 重算)`；decide 侧重试不重复同一工具，暂够用。

---

## `runbook_available` 与 `relevant_runbook` 绑定（代码契约）

`finalize_runbook_match`（`runbook_match_policy.py`）：

| `runbook_available` | `relevant_runbook` | `selected_runbook_id` |
|---------------------|--------------------|------------------------|
| `true` | 非空全文 | 非空 |
| `false` | `None` | 通常无（INVALID 时或有 id 无正文） |

**路由开关**：

```text
runbook_available == true  ⇔  有可用 runbook  ⇔  runbook 路径
runbook_available == false   ⇔  无可用 runbook  ⇔  探索路径
```

---

## 全链路二分（目标状态）

```text
retrieve_runbooks（两路径相同：产生 runbook_candidates）
  ↓
diagnose.coverage（两路径相同：finalize → runbook_available / relevant_runbook）
  ↓
diagnose.rca + confidence（分叉，见下）
  ↓
decide（分叉，见下）
  ↓
write_tools → verify_remediation → …（两路径相同；verify/summarize 不用 runbook 正文）
  ↓
summarize → [runbook_available=false ? KB 写回链 : END]
```

---

## diagnose 分流（已实现）

```text
coverage（现有 rubric + policy + finalize，不改）
  ├─ runbook_available == true  →  runbook 路径
  │     _run_rca_runbook：专用 prompt，输出 schema 仍为 RootCauseDraft
  │     任务：声明症状已有 validated runbook；证据引用 runbook 条款 + telemetry ref
  │     跳过 _run_confidence LLM
  │     confidence_sufficient = true（代码设置 confidence_gate_reason）
  └─ runbook_available == false   →  探索路径
        _run_rca_explore：探索 prompt（运维通识 + telemetry；可微调）
        _run_confidence：现有 LLM + diagnosis_confidence_policy
```

**实现要点**：

- 不删除 `root_cause` / `evidence` state 槽位；runbook 路径用 **格式化采纳** 替代自由推断 RCA。
- mock：`runbook 路径` 须绕过 `mock_confidence_assessment(service)` 对 ecomm-search 等的故意 FAIL（KB 仍为 novel，走探索路径，不受影响）。

**涉及文件**：`diagnose.py`、`diagnose_spec.py`（`RCA_RUNBOOK_*` / `RCA_EXPLORE_*` prompt）。

---

## decide 分流（已实现，与 diagnose 同批）

**原则**：与 diagnose 共用同一 `runbook_available` 开关；**探索路径下 decide 不得看到或使用 runbook**（含 assessment 与 tool_select）。

### runbook 路径（`runbook_available == true`）

```text
_run_assessment：传入 relevant_runbook excerpt（现有 [:800] 或 excerpt 工具）
_run_tool_select：同上；工具选择可参考 runbook 处置步骤 + write_tools catalog
```

- system prompt：强调已有 **validated runbook**；handleability 与 catalog 工具对齐 runbook 建议步骤。
- **不**重新评判 coverage / novel（与现 ASSESSMENT_SYSTEM_PROMPT 一致）。

### 探索路径（`runbook_available == false`）

```text
_run_assessment：仅 service、root_cause、evidence、remediation_context、write_tools_catalog
_run_tool_select：仅 service、root_cause、assessment_reasoning、evidence、remediation_context
```

- **移除** `Relevant runbook:` 段（不传 `(none)` 占位）。
- system prompt 增补：*无 validated runbook；不得引用、推断或假设 runbook 处置步骤；仅依据 root_cause、evidence 与 catalog 判断。*
- `runbook_available` 字段可保留在 human 消息中作路由说明，或仅依赖代码分叉（实现时二选一，推荐代码分叉、探索 template 不提 runbook）。

### mock 路径

- `mock_row_for_state` 逻辑不变（按 service/scenario key，不读 runbook 正文）。

### 已符合二分、本轮不改

| 模块 | 行为 |
|------|------|
| `compute_needs_approval` | `runbook_available=false` → 强制 approve（保留） |
| `summarize` / `verify_remediation` | 不使用 `relevant_runbook` |
| `draft_runbook`（KB 链） | 用 `match_gate_reason`、root_cause、evidence；不用 `relevant_runbook` 全文 |
| `builder._route_after_summarize` | `runbook_available=false` → KB 写回链 |

### state 说明

- `runbook_candidates`：novel 时仍可在 state / 观测 JSON 中保留（retrieve 产物）；**不得**传入 decide LLM prompt（当前已满足，保持）。
- `relevant_runbook`：novel 时保持 `None`（finalize 已保证）。

**涉及文件**：`decide.py`、`decide_spec.py`（`ASSESSMENT_*` / `TOOL_SELECT_*` 拆为 runbook / explore 两套 template + prompt）。

---

## 改前审计（2026-07-06）

| 节点 | 问题 |
|------|------|
| `diagnose._run_confidence` | 不看 runbook；runbook 路径仍调用 → 误杀 LOOP-02 等 |
| `decide` assessment / tool_select | novel 时仍传 `Relevant runbook: (none)` |
| 其余下游 | 已基本不依赖 runbook 正文 |

---

## 实现清单（确认后执行）

| 优先级 | 项 | 文件 |
|--------|-----|------|
| P0 | diagnose 双路径 RCA + runbook 路径 skip confidence | `diagnose.py`, `diagnose_spec.py` |
| P0 | decide 双 template（探索路径无 runbook 段） | `decide.py`, `decide_spec.py` |
| P1 | unit：`novel=false` 不调 confidence LLM；`novel=true` decide prompt 无 runbook | `tests/test_diagnose_*.py`, `tests/test_decide_*.py` 或扩展现有 |
| P1 | `make test-graph` | — |
| P2 | 文档版本注记 | `graph-agent-architecture.md`, `decide-remediation-architecture.md` |
| P2 | `open-issues.md` #1 进展 | — |
| 人工 | `run_scenarios` DEC/LOOP real LLM | — |

**明确不改**：react 环路由、`verify_remediation` 逻辑、`runbook_match_policy` 三态、coverage rubric 门槛。

---

## 验证范围

- `make test-graph`
- `tests/test_diagnose_spec.py`、decide 相关单测
- `tests/test_run_scenarios.py`（mock）
- 人工：`CHECKPOINTER=memory LLM_MODE=real BACKEND_MODE=real python scripts/run_scenarios.py --scenarios DEC-01 LOOP-02 LOOP-03 DEC-02`

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-06 | 初版：diagnose 二分 + skip confidence；三态不拆；react 暂不改 |
| 2026-07-06 | 审计 decide 下游 runbook 暴露 |
| 2026-07-06 | **定案并入**：decide 严格二分（探索路径无 runbook 段）；与 diagnose 同批实现 |
