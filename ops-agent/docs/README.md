# ops-agent 文档索引

本目录是 **ops-agent** 的架构与测试文档入口。仓库根 [`README.md`](../README.md) 保留快速开始；细节在此展开。

---

## 怎么读

| 你想… | 从这里开始 |
|--------|------------|
| **改代码前的七步 SOP** | [`../docs/change-workflow.md`](../docs/change-workflow.md)（monorepo 根） |
| 了解全貌、组件边界、测试分层 | [`architecture.md`](architecture.md) |
| 改某一模块前的同步清单 | 对应 **组件文档** §「Agent 改动同步指南」 |
| 对照场景 ID 与预期轨迹 | [`test-scenario-trajectories.md`](test-scenario-trajectories.md) |
| 起 simulator、验 write→read | [`backend-adapters-architecture.md`](backend-adapters-architecture.md) §5 |
| 扩 runbook 语料 / golden | [`rag-eval-corpus.md`](rag-eval-corpus.md) |

**分工原则**（避免重复维护）：

- **总览**（`architecture.md`）— 地图与入口，不展开实现
- **组件文档**（`*-architecture.md`）— 各管「这块怎么工作、怎么测」
- **场景目录**（`test-scenario-trajectories.md`）— 只列「测什么、轨迹是什么」
- **Simulator 实现** — 只在 [`ops-backend-simulator/README.md`](../../ops-backend-simulator/README.md)

**修改后文档**：每次合入功能/行为变更，须在对应组件文档的 **§「Agent 改动同步指南」** 所要求的 **版本注记 / 变更记录** 中追加一条修改摘要（日期 + 范围 + 关键变化）。跨模块改动在涉及各文档各记一条，或交叉引用主文档 §9。

---

## 文档列表

### 总览

| 文档 | 说明 |
|------|------|
| [**architecture.md**](architecture.md) | 项目定位、组件地图、主流程、环境/脚本入口、测试分层、Agent 导航 |

### 组件（架构 + 测试 + 改动同步）

| 文档 | 代码主路径 | 说明 |
|------|------------|------|
| [**graph-agent-architecture.md**](graph-agent-architecture.md) | `app/graph/builder.py`, `runner.py`, `collection.py` | LangGraph 主图、HITL 恢复、react 环 |
| [**rag-architecture-and-tests.md**](rag-architecture-and-tests.md) | `app/rag/`, `retrieve_runbooks`, `runbook_coverage`, `runbook_eval_policy` | 混合检索、覆盖裁决、golden 评测 |
| [**decide-remediation-architecture.md**](decide-remediation-architecture.md) | `decide*`, `tools/`, `verify_remediation` | 决策三分支、审批、写工具、验收 |
| [**backend-adapters-architecture.md**](backend-adapters-architecture.md) | `app/adapters/` | mock/real 遥测与写路径；Simulator 联调 |
| [**kb-lifecycle-architecture.md**](kb-lifecycle-architecture.md) | notes → draft → review → `ingest_runbook` | novel 场景 KB 写回（与 RAG 读路径分离） |
| [**api-runtime-architecture.md**](api-runtime-architecture.md) | `app/main.py`, `config.py`, `llm/`, `memory/` | HTTP API、配置、checkpoint、观测 |

### 专题 / 目录

| 文档 | 说明 |
|------|------|
| [**rag-eval-corpus.md**](rag-eval-corpus.md) | RAG 语料生成、golden 集运维（补充 RAG 主文档） |
| [**test-scenario-trajectories.md**](test-scenario-trajectories.md) | REM / HITL / LOOP / DEC / KB / RAG 场景矩阵与预期轨迹 |

### 外部仓库

| 文档 | 说明 |
|------|------|
| [**ops-backend-simulator/README.md**](../../ops-backend-simulator/README.md) | 场景状态机、`apply_ops`、Admin API、新增 scenario 清单 |
| **ops-backend**（Java） | 生产契约参考；联调时 `BACKEND_BASE_URL` 指向 Java 服务 |

---

## 按任务速查

| 任务 | 文档 |
|------|------|
| 新增图节点或改路由 | `graph-agent-architecture.md` |
| 调 RAG 阈值 / 检索链 | `rag-architecture-and-tests.md` |
| 新增写工具 | `decide-remediation-architecture.md` + `backend-adapters-architecture.md` |
| 新增 Simulator 场景 | simulator README → `backend-adapters-architecture.md` §5 |
| 新增 KB / novel 场景 | `kb-lifecycle-architecture.md` + `test-scenario-trajectories.md` |
| 新增 HTTP 端点或 env | `api-runtime-architecture.md` |
| 新增 REM/LOOP 等测试 ID | `test-scenario-trajectories.md` |
| 跑 RAG 指标 | `rag-architecture-and-tests.md` + `scripts/rag_eval.py` |

---

## 常用命令

```bash
# 全量测试
.venv/bin/pytest tests/ -q

# 图路径（mock LLM）
.venv/bin/pytest tests/graph_paths/ -q

# RAG（monorepo 根目录）
make test-rag-retrieval   # Track A
make test-rag-coverage    # Track B
make test-rag             # 双轨合并

# 场景表征
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios REM-01 --mock-llm
```

更多入口见 [`architecture.md`](architecture.md) §4–§5。
