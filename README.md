# Ops Agent Demo — Git Monorepo

本项目是一个**拟真电商 SaaS 运维 Agent 演示**（LangGraph + FastAPI + RAG）：接收故障工单后，自动采集遥测、检索 runbook、诊断根因，并在风险可控时执行修复（高危走人审）；配套有状态后端替身、Java 契约参考与部署清单。默认 **mock-first**，无需 API Key 即可离线跑通；也可切换 real LLM 做 E2E walkthrough。


| 目录                                                                     | 说明                                         |
| ---------------------------------------------------------------------- | ------------------------------------------ |
| `[agent/](agent/)`                                                     | LangGraph + FastAPI 主工程（架构见 `docs/agent/`） |
| `[ops-backend-simulator/](ops-backend-simulator/)`                     | 有状态 HTTP 后端替身                              |
| `[ops-backend/](ops-backend/)`                                         | Spring Boot 契约参考                           |
| `[deploy/](deploy/)`                                                   | docker-compose + K8s                       |
| `[docs/README.md](docs/README.md)`                                     | **文档总索引**                                  |
| `[CLAUDE.md](CLAUDE.md)`                                               | 项目宪法：约束、命令、编码规范                        |
| `[specs/ops-agent/](specs/ops-agent/)`                                 | 需求、设计、开发任务（AI-Native Bootstrap）           |


## 快速开始

```bash
# 0. 首次：安装依赖（在 agent/ 下）
cd agent
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip && .venv/bin/python -m pip install -e ".[dev]"
cp -n .env.example .env    # 默认 mock-first；real LLM 再改 .env

# 1. 启动 API（mock 模式，无需 API Key；在 monorepo 根目录）
cd agent && BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. 离线演示（mock；make 会覆盖 .env 中的 real 配置）
make demo

# 3. Real LLM 场景演出（需 agent/.env 配置 OPENAI_* 等；自动起 simulator）
make demo-real              # 交互式 walkthrough（单幕 + 目录；详见 demo-presenter.md）
make demo-real-auto         # 标准五幕连跑（~3 min，DEMO-02 处 Enter 批准 HITL）

# 4. 测试（在 monorepo 根目录）
make test-rag-retrieval     # RAG Track A：检索 + golden L1
make test-rag-coverage      # RAG Track B：coverage rubric + golden L2
make test-rag               # RAG 双轨（合入前推荐）
make test-graph             # LangGraph 路径：REM / HITL / LOOP / DEC / KB
make test-api               # HTTP API、eval、tracing、health
make test-simulator         # 后端替身状态机
make test                   # agent/ 全量 pytest（合入前最终门禁）
```

Real LLM 演示见 [`docs/agent/demo-presenter.md`](docs/agent/demo-presenter.md)（交互）与 [`docs/agent/demo-scenarios.md`](docs/agent/demo-scenarios.md)（batch profile）。

## 改代码前

### 新功能开发

按 spec-driven 流程，在 `specs/{feature}/` 下依次创建：

1. `requirements.md` — 用户故事 + EARS 验收标准
2. `design.md` — 架构、组件、数据模型
3. `tasks.md` — 原子任务清单（精确文件路径，需求追溯）

Agent 按 `tasks.md` 从上到下逐项实现，每完成一项标记 `- [x]`。详见 [`CLAUDE.md`](CLAUDE.md) §Spec-Driven Workflow。

### 小改动 / Bug 修复

1. 读 [`CLAUDE.md`](CLAUDE.md) — 约束、LLM 规则、常见踩坑
2. `make impact` — 查看 diff 涉及的文档与测试
3. 让 Agent 先输出同步计划（必改/不必改代码、测试、文档、验证命令），确认后再改
4. 改后跑 `make test-*`，在对应组件文档追加变更记录

### 一次性设置

```bash
make install-hooks   # commit 时按变更路径自动跑对应测试
```
