# 文档索引

本目录为 monorepo **唯一文档根**。仓库根 [`README.md`](../README.md) 保留快速开始；架构与测试细节在此展开。

| 子目录 | 内容 |
|--------|------|
| [`agent/`](agent/) | LangGraph Agent 架构、场景矩阵、RAG 评测、E2E 演示 |
| [`deploy/`](deploy/) | 部署清单说明（文件在仓库根 `deploy/`） |

项目约束与规范文件在仓库根 [`CLAUDE.md`](../CLAUDE.md) 和 [`specs/ops-agent/`](../specs/ops-agent/)（requirements / design；tasks 在具体 feature 开发时创建）。

---

## 怎么读

| 你想… | 从这里开始 |
|--------|------------|
| **了解项目约束与改代码纪律** | [`CLAUDE.md`](../CLAUDE.md)（仓库根） |
| **项目需求与验收标准** | [`specs/ops-agent/requirements.md`](../specs/ops-agent/requirements.md) |
| **高层架构总览** | [`specs/ops-agent/design.md`](../specs/ops-agent/design.md) |
| 了解全貌、组件边界、测试分层 | [`agent/architecture.md`](agent/architecture.md) |
| 改某一模块前的同步清单 | 对应 **组件文档** §「Agent 改动同步指南」 |
| 对照场景 ID 与预期轨迹 | [`agent/test-scenario-trajectories.md`](agent/test-scenario-trajectories.md) |
| 起 simulator、验 write→read | [`agent/backend-adapters-architecture.md`](agent/backend-adapters-architecture.md) §5 |
| 扩 runbook 语料 / golden | [`agent/rag-eval-corpus.md`](agent/rag-eval-corpus.md) |

**分工原则**（避免重复维护）：

- **总览**（`agent/architecture.md`）— 地图与入口，不展开实现
- **组件文档**（`agent/*-architecture.md`）— 各管「这块怎么工作、怎么测」
- **场景目录**（`agent/test-scenario-trajectories.md`）— 只列「测什么、轨迹是什么」
- **Simulator 实现** — 只在 [`ops-backend-simulator/README.md`](../ops-backend-simulator/README.md)
- **Python 工程薄 README** — [`agent/README.md`](../agent/README.md)（venv、启动命令）
- **项目约束与开发纪律** — [`CLAUDE.md`](../CLAUDE.md) + [`specs/ops-agent/`](../specs/ops-agent/)

---

## 文档列表

### 总览

| 文档 | 说明 |
|------|------|
| [**agent/architecture.md**](agent/architecture.md) | 项目定位、组件地图、主流程、环境/脚本入口、测试分层 |

### 组件（架构 + 测试 + 改动同步）

| 文档 | 代码主路径 | 说明 |
|------|------------|------|
| [**graph-agent-architecture.md**](agent/graph-agent-architecture.md) | `agent/app/graph/` | LangGraph 主图、HITL 恢复、react 环 |
| [**rag-architecture-and-tests.md**](agent/rag-architecture-and-tests.md) | `agent/app/rag/`, retrieve / coverage | 混合检索、覆盖裁决、golden 评测 |
| [**decide-remediation-architecture.md**](agent/decide-remediation-architecture.md) | decide / tools / verify | 决策三分支、审批、写工具、验收 |
| [**backend-adapters-architecture.md**](agent/backend-adapters-architecture.md) | `agent/app/adapters/` | mock/real 遥测与写路径；Simulator 联调 |
| [**kb-lifecycle-architecture.md**](agent/kb-lifecycle-architecture.md) | KB 写回链 | 无 runbook 覆盖时的 HITL 写回 |
| [**api-runtime-architecture.md**](agent/api-runtime-architecture.md) | `agent/app/main.py`, config, llm | HTTP API、配置、checkpoint、观测 |

### 专题

| 文档 | 说明 |
|------|------|
| [**rag-eval-corpus.md**](agent/rag-eval-corpus.md) | RAG 语料生成、golden 集运维 |
| [**test-scenario-trajectories.md**](agent/test-scenario-trajectories.md) | REM / HITL / LOOP / DEC / KB / RAG 场景矩阵 |
| [**demo-presenter.md**](agent/demo-presenter.md) | 交互式 real LLM 演示（`make demo-real`） |
| [**demo-scenarios.md**](agent/demo-scenarios.md) | batch profile 与幕次矩阵 |
| [**open-issues.md**](agent/open-issues.md) | 已知问题与 workaround |
| [**archive/**](agent/archive/) | 已实现的设计草案归档 |

---

## 按任务速查

| 任务 | 文档 |
|------|------|
| 新增图节点或改路由 | `agent/graph-agent-architecture.md` |
| 调 RAG 阈值 / 检索链 | `agent/rag-architecture-and-tests.md` |
| 新增写工具 | `agent/decide-remediation-architecture.md` + `backend-adapters-architecture.md` |
| 新增 Simulator 场景 | simulator README → `agent/backend-adapters-architecture.md` §5 |
| real LLM E2E 演示 | `agent/demo-presenter.md` + `agent/scripts/run_demo.py` |

---

## 常用命令

```bash
# 在 agent/ 目录（或 monorepo 根 make test-*）
cd agent
.venv/bin/pytest tests/ -q
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios REM-01 --mock-llm
```

更多入口见 [`agent/architecture.md`](agent/architecture.md) §4–§5。

## 变更记录

### 2026-08-11 · 约束文件重构为 AI-Native Bootstrap 格式

- `AGENTS.md`、`docs/workflow/change-workflow.md`、`.cursor/rules/ops-change-workflow.mdc` 合并入 `CLAUDE.md` + `specs/ops-agent/`。
- 新增 `specs/ops-agent/requirements.md`、`design.md`、`tasks.md`。
- `CLAUDE.md` 按 AI-Native Bootstrap 模板重写（精简 ~150 行）。

### 2026-07-08 · 文档目录重组（方案 A）

- 统一文档根：`docs/workflow/` + `docs/agent/` + `docs/deploy/`。
- Python 工程目录 `ops-agent/` 重命名为 `agent/`；monorepo 工具 `scripts/` → `tooling/`。
- 已实现设计 `design-diagnose-runbook-split.md` 移入 `docs/agent/archive/`。
