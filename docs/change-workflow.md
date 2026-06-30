# 代码修改流程（SOP）

> 人与 Agent 共用。文档 §5 告诉你**同步什么**；本文告诉你**按什么顺序做**。

---

## 七步流程

### 0. 开分支

```bash
git checkout -b feat/<简短描述>   # 或 fix/…
```

一句话写清意图，例如：`调整 RAG 消歧阈值，LOOP 场景更早 honest novel`。

### 1. 看 diff

```bash
git status
git diff
# 或对比 main：git diff main...HEAD --name-only
```

可选：运行影响提示（见文末 `change_impact.py`）。

### 2. 分类 → 打开组件文档

| 改动触及 | 主文档（`ops-agent/docs/`） |
|----------|----------------------------|
| `app/rag/`, `eval_runbook`, `runbook_eval_policy` | `rag-architecture-and-tests.md` §5 |
| `builder.py`, `nodes/`（非 RAG）, `runner.py` | `graph-agent-architecture.md` |
| `decide`, `tools/`, `eval_remediation` | `decide-remediation-architecture.md` |
| `app/adapters/`, simulator 联调 | `backend-adapters-architecture.md` + `ops-backend-simulator/README.md` |
| KB 写回链 | `kb-lifecycle-architecture.md` |
| `main.py`, `config.py`, LLM/checkpoint | `api-runtime-architecture.md` |
| 场景 ID / 预期轨迹 | `test-scenario-trajectories.md`（仅场景表） |

跨组件：主文档 + 次文档各读 §「Agent 改动同步指南」。

### 3. 输出「同步计划」（改代码前，待批准）

```markdown
## 同步计划
- **分类**：（如 RAG §5.6）
- **必改代码**：…
- **必改测试**：…
- **必改文档**：…（版本注记 / 变更记录）
- **不必改**：…
- **验证命令**：make test-rag / make test-graph / …
```

对照组件文档 §5「必须同步」表逐项核对。**未输出计划不得动手。**

### 4. 实现

顺序建议：逻辑 + 单测 → 集成测试 → 文档。

涉及 `data/runbooks/` 或 ingest：记得 `reindex()`。  
涉及 simulator 场景：同步 `ops-backend-simulator` 模块与 `mock_data`。

### 5. 分层验证

在 **monorepo 根目录**执行：

| 改动类型 | 命令 |
|----------|------|
| RAG | `make test-rag` |
| 图路由 / HITL | `make test-graph` |
| decide / 工具 | `make test-graph` + 相关单测 |
| API / tracing | `cd ops-agent && .venv/bin/pytest tests/test_eval.py tests/test_tracing.py -q` |
| 合入前 | `make test` |

### 6. 文档与勾选清单

- [ ] 代码与测试已更新
- [ ] 组件文档 §5 所列文件均已检查
- [ ] **版本注记 / 变更记录**已追加（日期 + 1～3 句）
- [ ] 若动 runbook / ingest：已 `reindex()`
- [ ] 若动 simulator 场景：simulator tests 已跑
- [ ] 验证命令已跑且通过

### 7. 提交

```bash
git add -A
git commit -m "简短说明（why，非 what 罗列）"
```

---

## Agent Prompt 模板

```text
我要做如下改动：<一句话目标>

请严格按本仓库 docs/change-workflow.md 与 AGENTS.md 执行：
1. git status / git diff
2. 读对应组件文档「Agent 改动同步指南」
3. 先输出「同步计划」，我确认后再改代码
4. 改后跑计划中的 make test-* 并贴结果
5. 更新版本注记

不要跳过同步计划与验证步骤。
```

---

## 影响提示脚本（可选）

```bash
python scripts/change_impact.py          # 基于 git diff --name-only
python scripts/change_impact.py --staged
```

根据变更路径打印建议阅读的文档章节与 `make test-*` 命令。

---

## 相关文档

- [`AGENTS.md`](../AGENTS.md) — Agent 总入口
- [`ops-agent/docs/README.md`](../ops-agent/docs/README.md) — 文档索引
- [`ops-agent/docs/architecture.md`](../ops-agent/docs/architecture.md) — 项目总览
