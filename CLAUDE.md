# CLAUDE.md — ops-agent AI 编码宪法

> **读者**：Claude Code 与人类开发者。
> **用途**：指导 AI 理解项目全貌、遵循纪律、高质量编码。
> **前置**：本文件基于 `AGENTS.md`（Cursor 入口）与完整 `docs/` 展开，AGENTS.md 仍有效。

---

## 1. 项目定位与架构

**ops-agent** 是一个拟真电商 SaaS 运维诊断与自动修复 Agent，基于 **LangGraph + FastAPI**。

**核心能力**：接收故障工单 → 自动采集遥测 → RAG 检索 runbook → LLM 诊断根因 → 决策 → 执行写工具 → 验收 → 总结。知识库缺口时走 HITL 写回 runbook。

### 1.1 Monorepo 结构

```
ops-agent/                          # Git monorepo 根
├── agent/                          # 🐍 Python 3.12 主工程 (LangGraph + FastAPI)
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口，7 个端点
│   │   ├── config.py               # pydantic-settings，所有配置项
│   │   ├── schemas.py              # Pydantic 请求/响应模型
│   │   ├── graph/                  # LangGraph 图定义 ★核心★
│   │   │   ├── builder.py          # StateGraph 构建 + 6 条条件边路由
│   │   │   ├── runner.py           # 运行入口：invoke / stream / resume
│   │   │   ├── state.py            # AgentState TypedDict（40+ 字段）
│   │   │   ├── collection.py       # 遥测采集聚合 + symptom_query 构造
│   │   │   ├── nodes/              # 12 个图节点
│   │   │   │   ├── triage.py       # 服务识别
│   │   │   │   ├── retrieve_runbooks.py  # RAG 检索（纯检索，无 LLM）
│   │   │   │   ├── diagnose.py     # 诊断三阶段：coverage → RCA → confidence
│   │   │   │   ├── decide.py       # 决策：actionable / uncertain / out_of_scope
│   │   │   │   ├── approve.py      # HITL 审批闸门
│   │   │   │   ├── verify_remediation.py  # 写后验收
│   │   │   │   ├── summarize.py    # 总结生成
│   │   │   │   ├── request_runbook_notes.py / draft_runbook.py / review_runbook.py / ingest_runbook.py  # KB 写回链
│   │   │   ├── runbook_coverage.py # LLM rubric + golden oracle
│   │   │   ├── diagnose_spec.py    # mock 诊断规格
│   │   │   ├── decide_spec.py      # mock 决策规格 + DecideOutcome 枚举
│   │   │   ├── runbook_eval_policy.py  # finalize_runbook_coverage 代码裁决
│   │   │   ├── categorical_rubric.py   # CoT PASS/PARTIAL/FAIL 范畴化评估
│   │   │   ├── eval_schemas.py     # RunbookCandidate, RunbookEvalLLMOutput, coerce
│   │   │   ├── runbook_excerpt.py  # runbook 摘要
│   │   │   ├── remediation_context.py  # DECIDE_RETRY_GUIDANCE / RCA_RETRY_GUIDANCE
│   │   │   ├── rag_observability.py    # rag_snapshot_from_state
│   │   │   ├── extensions/         # 扩展位（investigation 子图，未默认挂载）
│   │   ├── rag/                    # RAG 检索层 ★独立于 LLM★
│   │   │   ├── retrieval.py        # 端到端：hybrid → rerank → parent → top-K
│   │   │   ├── hybrid.py           # Chroma 向量 + BM25, RRF 融合
│   │   │   ├── bm25_index.py       # BM25 索引（按 service 缓存）
│   │   │   ├── rerank.py           # 融合分 + BM25 + 词重叠重排
│   │   │   ├── tokenize.py         # 中英文分词
│   │   │   ├── parent.py           # chunk id → parent stem → 磁盘全文
│   │   │   ├── store.py            # Chroma collection, embedding, search
│   │   │   ├── ingest.py           # markdown 切分, ensure_indexed / reindex
│   │   │   └── eval_harness.py     # evaluate_retrieval_golden / coverage_golden
│   │   ├── llm/
│   │   │   └── provider.py         # ChatOpenAI + MockChatModel + invoke_structured()
│   │   ├── memory/
│   │   │   └── short_term.py       # LangGraph checkpointer (sqlite/memory/redis)
│   │   ├── adapters/
│   │   │   ├── backend_client.py   # mock/real HTTP 分支
│   │   │   ├── mock_data.py        # 离线遥测数据
│   │   │   └── mock_remediation.py # mock 写后状态
│   │   ├── tools/                  # LangChain Tool 定义
│   │   │   ├── __init__.py         # READ_TOOLS (7) + WRITE_TOOLS (10)
│   │   │   ├── policy.py           # TOOL_RISK 风险表 + compute_needs_approval
│   │   │   ├── ops_tools.py        # 10 个写工具
│   │   │   ├── log_tools.py, metric_tools.py, status_tools.py, runbook_tools.py
│   │   ├── observability/
│   │   │   ├── metrics.py          # Prometheus RUN_LATENCY histogram
│   │   │   └── tracing.py          # LangSmith 初始化
│   │   └── audit/                  # 审计日志
│   ├── data/
│   │   ├── runbooks/               # 55 篇 runbook markdown（RAG 索引源）
│   │   └── incidents/              # 可选 incident 文档
│   ├── tests/                      # pytest 测试
│   │   ├── graph_paths/            # 图路径契约测试（mock LLM, 6 文件）
│   │   ├── rag_eval/               # Golden RAG 评测（4 文件, 46 条 golden）
│   │   └── test_*.py               # 单元/集成测试（30+ 文件）
│   ├── eval/
│   │   ├── dataset.jsonl           # 15 场景 LLM 评测数据集
│   │   ├── judges.py               # 启发式评委
│   │   └── run_eval.py             # 评测脚本
│   ├── scripts/                    # 命令行脚本
│   │   ├── demo.py                 # 三场景离线演示
│   │   ├── run_demo.py             # real LLM 交互式 / batch 演示
│   │   ├── run_scenarios.py        # 场景表征（步进 JSON + rag 观测）
│   │   ├── rag_eval.py             # RAG golden 指标报告
│   │   ├── generate_rag_corpus.py  # runbook 语料生成
│   │   ├── rag_corpus_specs.py     # 语料规格源
│   │   ├── scenario_runtime.py     # SimulatorSession + lab helpers
│   │   └── demo_presenter/         # 交互式演示子模块（9 文件）
│   ├── pyproject.toml              # Python 工程配置 + pytest markers
│   ├── Dockerfile
│   └── .env.example
├── ops-backend-simulator/          # 🧪 有状态 HTTP 后端替身
│   ├── simulator/
│   │   ├── app.py                  # FastAPI + admin 端点
│   │   ├── session.py              # 场景会话管理
│   │   ├── schemas.py              # 场景状态数据结构
│   │   └── scenarios/              # 13 个故障场景模块
│   └── tests/                      # 场景状态机单测
├── ops-backend/                    # ☕ Java Spring Boot 契约参考
│   ├── pom.xml
│   └── src/main/java/.../         # 3 个 Controller, 6 个 Model, 3 个 Service
├── deploy/                         # 🚀 部署清单
│   ├── docker-compose.yml
│   └── k8s/                        # 10 个 K8s 清单文件
├── docs/                           # 📚 文档 ★改代码前必读★
│   ├── README.md                   # 文档总索引
│   ├── workflow/
│   │   └── change-workflow.md      # 七步 SOP（人与 Agent 共用）
│   └── agent/
│       ├── architecture.md         # 项目总览（地图 + 入口）
│       ├── graph-agent-architecture.md        # 图编排 + HITL + react
│       ├── rag-architecture-and-tests.md      # RAG 架构 + 双轨测试 + 改动同步
│       ├── decide-remediation-architecture.md # 决策 + 工具 + 审批 + 验收
│       ├── backend-adapters-architecture.md   # mock/real 后端适配
│       ├── kb-lifecycle-architecture.md       # KB 写回链
│       ├── api-runtime-architecture.md        # HTTP API + config + LLM + checkpoint
│       ├── test-scenario-trajectories.md      # 场景矩阵（16 个测试 ID）
│       ├── rag-eval-corpus.md                 # RAG 语料与 golden 运维
│       ├── demo-presenter.md                  # 交互式演示说明
│       ├── demo-scenarios.md                  # Batch profile + 幕次矩阵
│       ├── open-issues.md                     # 已知遗留问题
│       └── archive/                           # 已实现的设计草案归档
├── tooling/
│   ├── change_impact.py            # Git diff → 建议文档 + 测试命令
│   └── migrate_paths.py            # 路径迁移工具
├── .cursor/rules/ops-change-workflow.mdc  # Cursor 规则（与 AGENTS.md 互补）
├── .githooks/pre-commit            # 按路径自动跑测试
├── AGENTS.md                       # Cursor Agent 入口
├── Makefile                        # 统一命令入口
└── README.md                       # 项目 README
```

---

## 2. 技术栈

| 层 | 技术 | 备注 |
|---|------|------|
| **Agent 框架** | LangGraph (`StateGraph`) | 12 节点 + 6 条件边 + 3 HITL interrupt |
| **Web 框架** | FastAPI | 7 个端点，`lifespan` 初始化 LangSmith |
| **LLM** | ChatOpenAI (DeepSeek V4 推荐) | `invoke_structured()` 供应商分流 |
| **Embedding** | Qwen `text-embedding-v3` (推荐) | 与 chat 可拆供应商 |
| **向量存储** | ChromaDB | `local-hash` 模式免 API |
| **检索** | hybrid (向量 + BM25 RRF) + lexical rerank | 纯 Python，无外部检索服务 |
| **Checkpoint** | LangGraph sqlite / memory / redis | `JsonPlusSerializer` 自定义序列化 |
| **可观测** | Prometheus + LangSmith | `RUN_LATENCY` histogram |
| **后端替身** | Python FastAPI (simulator) | 13 个有状态故障场景 |
| **后端参考** | Java Spring Boot | 仅作生产契约参考，不参与 CI |
| **Python** | 3.12 | `pyproject.toml`, hatchling |
| **测试** | pytest | 4 层金字塔 + 双轨 RAG |
| **部署** | Docker Compose + K8s | |

---

## 3. 核心架构概念

### 3.1 图主流程（12 节点）

```
START → triage → retrieve_runbooks → diagnose
  ├─ confidence < threshold → summarize
  └─ else → decide
       ├─ out_of_scope | uncertain | skipped → summarize
       ├─ actionable + needs_approval → approve [HITL] → write_tools
       └─ actionable → write_tools
  → verify_remediation
       ├─ resolved → summarize
       └─ not resolved & attempt < max → retrieve_runbooks (react 环)
  → summarize
       └─ runbook_available=false → request_runbook_notes → draft_runbook → review_runbook → ingest_runbook (KB 写回链)
```

**关键路由函数**（`builder.py` 6 个 `_route_after_*`）：
- `_route_after_diagnose`: `confidence_sufficient` false → summarize, else → decide
- `_route_after_decide`: `out_of_scope|uncertain` → summarize, `needs_approval` → approve, else → write_tools
- `_route_after_approve`: approved → write_tools, else → summarize
- `_route_after_verify_remediation`: resolved → summarize, attempt < max → retrieve_runbooks
- `_route_after_summarize`: `runbook_available=false` → request_runbook_notes, else → END
- `_route_after_review`: approved → ingest_runbook, else → END

### 3.2 关键概念区分（容易混淆）

| 概念 | 含义 | 设置方 |
|------|------|--------|
| `runbook_available` | KB 是否有可用 runbook | diagnose coverage stage |
| `decide_outcome` | 决策结果: `actionable` / `uncertain` / `out_of_scope` / `skipped_low_confidence` | decide node |
| `confidence_sufficient` | 诊断置信度是否足够 | diagnose confidence stage |
| `needs_approval` | 是否需要 HITL 审批 | `compute_needs_approval` (policy.py) |
| `incident_resolved` | 修复后验收是否通过 | verify_remediation node |

**注意**：`runbook_available=false` ≠ `confidence_sufficient=false`。前者是 RAG 覆盖问题，后者是诊断质量问题。`runbook_available=false` 时所有写操作必走 approve。

### 3.3 HITL 中断点（3 个）

| 中断节点 | API 恢复端点 | response status |
|----------|-------------|-----------------|
| `approve` | `POST /approve` | `awaiting_approval` |
| `request_runbook_notes` | `POST /runbooks/notes` | `awaiting_runbook_notes` |
| `review_runbook` | `POST /runbooks/review` | `awaiting_runbook_review` |

### 3.4 RAG 两阶段分离

**阶段 1 — `retrieve_runbooks`（纯检索，无 LLM）**：
incident + telemetry → `extract_symptoms()` → hybrid top-20 (Chroma + BM25 RRF) → rerank top-10 → parent expand → top-3 `RunbookCandidate`

**阶段 2 — `diagnose` coverage（LLM rubric + 代码裁决）**：
top-3 candidates → LLM 四维 CoT (PASS/PARTIAL/FAIL) → `finalize_runbook_coverage()` 代码选 top1 → 加载全文

**裁决阈值**（`app/config.py`）：
- `runbook_match_max_partial=1`：每候选 PARTIAL 维数上限
- `runbook_match_min_pass_count=2`：至少 2 维 PASS 才算 selectable
- `diagnosis_confidence_max_partial=1`：confidence 可靠判定 PARTIAL 上限

### 3.5 写工具风险分级（`app/tools/policy.py`）

| 风险 | 工具 | 审批规则 |
|------|------|---------|
| **HIGH** | `rollback_deployment`, `scale_deployment`, `drain_node` | 必审批 |
| **MEDIUM** | `restart_deployment`, `delete_pod`, `cordon_node`, `enable_circuit_breaker`, `flush_cache` | 策略触发时审批 |
| **LOW** | `patch_config`, `toggle_feature_flag` | 策略触发时审批 |

`compute_needs_approval` 三条件（任一满足即审批）：
1. 含 HIGH 风险工具
2. `remediation_attempt >= 1` 且仍未恢复
3. `runbook_available=false`（KB 无覆盖）

---

## 4. 配置与环境变量

核心配置集中在 `agent/app/config.py` → `Settings` (pydantic-settings)。环境变量优先级：shell > `.env` > 默认值。

### 4.1 运行模式

| 变量 | 默认 | 可选值 | 说明 |
|------|------|--------|------|
| `BACKEND_MODE` | `mock` | `mock`, `real` | 遥测来源 |
| `LLM_MODE` | `mock` | `mock`, `real` | 是否调用真实 LLM |
| `EMBEDDINGS_PROVIDER` | `local-hash` | `local-hash`, `openai`, `qwen`, `bge` | 向量化提供方 |
| `CHECKPOINTER` | `sqlite` | `sqlite`, `memory`, `redis` | 图状态持久化 |

### 4.2 推荐组合

| 场景 | 环境变量 |
|------|---------|
| **CI / 离线开发** | `BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash CHECKPOINTER=memory` |
| **Real LLM 表征** | `LLM_MODE=real OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.deepseek.com OPENAI_MODEL=deepseek-v4-flash OPENAI_MODEL_STRONG=deepseek-v4-pro` |
| **Simulator 联调** | `BACKEND_MODE=real BACKEND_BASE_URL=http://127.0.0.1:8081` |
| **语义 RAG 评测** | `EMBEDDINGS_PROVIDER=qwen QWEN_API_KEY=sk-...` |

### 4.3 RAG 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `retrieval_hybrid_top_k` | 20 | hybrid 召回 chunk 数 |
| `retrieval_rerank_chunk_top_k` | 10 | rerank 后保留数 |
| `retrieval_final_top_k` | 3 | 送入 coverage rubric 的候选数 |
| `retrieval_rrf_k` | 60 | RRF 融合参数 |
| `retrieval_rerank_min_score` | 0.15 | 分数过滤（`local-hash` 时自动为 0） |
| `max_remediation_attempts` | 3 | react 环上限 |

---

## 5. LLM 供应商适配（`app/llm/provider.py`）

`invoke_structured()` 是项目中**唯一的** LLM 结构化输出入口。所有需要结构化输出的节点（diagnose、decide、verify_remediation、runbook_coverage）必须经此调用。

### 5.1 供应商分流逻辑

```
invoke_structured(llm, schema, messages)
  ├─ DashScope/Qwen → ensure_json_in_messages + _invoke_dashscope_structured
  │   (with_structured_output + include_raw, ValidationError → plain JSON fallback)
  ├─ DeepSeek → ensure_json_in_messages + _invoke_deepseek_structured
  │   (json_mode 非 json_schema, thinking: disabled)
  └─ 其他 → 标准 with_structured_output
```

### 5.2 关键规则

- **DeepSeek**：`get_chat_model()` 默认 `thinking: disabled`；`invoke_structured()` 走 `json_mode`（API 不支持 `json_schema`）
- **DashScope/Qwen**：`invoke_structured()` 走 `include_raw` + fallback
- **新增供应商**：必须同时改 `get_chat_model()` 和 `invoke_structured()` 分流逻辑
- **Mock 模式**：`MockChatModel` 返回固定文本，用于 graph_paths 测试

### 5.3 Schema Coerce 规则

LLM 结构化输出不可靠时，以下 schema 有 coerce 函数做形状防御：

| Schema | Coerce 函数 | 典型问题 |
|--------|------------|---------|
| `RunbookEvalLLMOutput` | `coerce_runbook_eval_llm_output()` | 裸数组 `[...]` → `{rubrics: [...]}` |
| `RunbookPerDocRubric` | `coerce_runbook_per_doc_rubric()` | 嵌套 `relevance`/`coverage` 展平 |
| `DecideAssessment` | `coerce_decide_assessment()` | `classification`→`outcome`, 缺省 `reasoning` |
| `RemediationEvalAssessment` | `coerce_remediation_eval_assessment()` | 缺省 `reasoning`, 别名归一化 |
| `RootCauseDraft` | `coerce_root_cause_draft()` | source 自然语言 → EvidenceSource 枚举 |
| `DiagnosisConfidenceAssessment` | `coerce_confidence_assessment()` | 字段别名 |

**规则**：新增 LLM 输出的 Pydantic schema 时，必须同时加 coerce 函数 + 单测。

---

## 6. 测试体系

### 6.1 测试金字塔

```
Layer 4  场景表征          scripts/run_scenarios.py, eval/run_eval.py
Layer 3  Golden / 集成     tests/rag_eval/, tests/test_rag_integration.py
Layer 2  图路径契约        tests/graph_paths/ (mock LLM, 固定路由)
Layer 1  单元 / 策略       tests/test_rag.py, test_*_policy.py, ...
Layer 0  Simulator 状态机  ops-backend-simulator/tests/
```

### 6.2 双轨 RAG 测试

| 轨道 | Marker | Make 目标 | 测什么 |
|------|--------|-----------|--------|
| **Track A (retrieval)** | `rag_only` | `make test-rag-retrieval` | hybrid / rerank / ingest / retrieve_runbooks 节点 |
| **Track B (coverage)** | `rag_coverage` | `make test-rag-coverage` | rubric + finalize_runbook_coverage / golden oracle |
| **合并** | — | `make test-rag` | 先 A 后 B |

### 6.3 Golden 三层评测

| 层级 | 命令 | 指标 |
|------|------|------|
| L1 检索 | `make test-rag-retrieval` | `recall_at_3`, `mrr_at_1`, `must_not_violation_rate` |
| L2 Coverage | `make test-rag-coverage` | `end_to_end_accuracy`, `selection_accuracy`, `runbook_unavailable_accuracy` |
| L3 Real LLM | `RAG_EVAL_REAL_LLM=1 pytest tests/rag_eval/test_real_llm_smoke.py` | 同上（真实 LLM rubric） |

### 6.4 场景矩阵（16 个测试 ID）

| ID | 能力域 | 路径 | 后端 | 是否测 real LLM |
|----|--------|------|------|----------------|
| REM-01 | 修复 | P1 直达 | mock | ✅ eval |
| REM-02 | 修复+审批 | P2 | mock | ✅ eval |
| HITL-01 | 审批拒绝 | P2 | mock | ❌ |
| HITL-02 | Review 拒绝 | P5 | mock | ❌ |
| LOOP-01 | 重试耗尽 | P4 | mock | ❌ 仅 mock 图契约 |
| LOOP-02 | Morph 可恢复 | P4 | simulator | ✅ |
| LOOP-03 | 分层耗尽 | P4 | simulator | ✅ |
| DEC-01 | 静态 OOS | P3 | simulator | ✅ |
| DEC-02 | Morph OOS | P3/P4 | simulator | ✅ |
| KB-01 | 写回 (低置信) | P5 | mock | ❌ 固定 mock smoke |
| KB-02 | 写回 (高置信) | P2+P5 | mock | ❌ 固定 mock smoke |
| RAG-01 | 漏匹配 | — | — | ❌ |
| RAG-02 | 误匹配 | — | — | ❌ |
| EXEC-01 | 执行失败 | P4 | simulator | 待补 |
| EXEC-02 | 成功未恢复 | P4 | mock/exhaust | ❌ |

**重要**：KB 场景在 `run_scenarios.py` 内**强制 mock**，不受 `LLM_MODE=real` 影响。

---

## 7. 开发纪律（强制流程）

### 7.1 改代码七步 SOP（不可跳过）

1. **`git status / git diff`** — 确认影响范围
2. **读 `docs/workflow/change-workflow.md`** + 对应组件文档的 §「Agent 改动同步指南」
3. **先输出「同步计划」**，列出必改/不必改的代码、测试、文档、验证命令 — **用户确认后再写代码**
4. **实现改动** — 小步、可回滚；顺序：逻辑 + 单测 → 集成测试 → 文档
5. **跑验证** — `make test-rag` / `make test-graph` / `make test-api` / `make test`
6. **更新版本注记** — 在涉及组件文档的 §变更记录追加日期 + 1~3 句说明
7. **自检勾选清单** — 对照 `change-workflow.md` §6

### 7.2 改动分类 → 文档映射

| 改动触及 | 主文档 |
|----------|--------|
| `app/rag/`, `retrieve_runbooks`, `runbook_coverage`, `runbook_eval_policy` | `rag-architecture-and-tests.md` §5 |
| `builder.py`, `nodes/` (非 RAG), `runner.py` | `graph-agent-architecture.md` §6 |
| `decide`, `tools/`, `verify_remediation`, `approve` | `decide-remediation-architecture.md` §7 |
| `app/adapters/`, simulator 联调 | `backend-adapters-architecture.md` §7 |
| KB 写回链 | `kb-lifecycle-architecture.md` §6 |
| `main.py`, `config.py`, LLM/checkpoint | `api-runtime-architecture.md` §7 |
| 场景 ID / 预期轨迹 | `test-scenario-trajectories.md` |

### 7.3 同步计划模板

```markdown
## 同步计划
- **分类**：（如 RAG §5.6）
- **必改代码**：...
- **必改测试**：...
- **必改文档**：...（版本注记）
- **不必改**：...
- **验证命令**：make test-rag / make test-graph / make test
```

---

## 8. 编码规范与约定

### 8.1 通用原则

- **Mock-first**：默认 `BACKEND_MODE=mock LLM_MODE=mock`，无需 API Key 即可跑通 CI
- **单一事实来源**：场景 ID 只看 `test-scenario-trajectories.md`；simulator 实现只看 `ops-backend-simulator/README.md`；不跨文档复制细节
- **组件边界**：RAG 检索层不碰 LLM；LLM rubric 不选篇（由代码 policy 选）；coverage 在 diagnose 中而非 retrieve_runbooks 中
- **Schema 稳健**：所有 LLM JSON 输出必须经 coerce 函数做形状防御
- **路由显式**：图路由修改后必须检查所有 `_route_after_*` 分支 + 对应 graph_paths 测试

### 8.2 新增代码清单

#### 新增图节点
1. `app/graph/nodes/<name>.py` — 节点函数（签名: state → dict）
2. `builder.py` — `add_node` + 边/条件边
3. `state.py` — 新字段（TypedDict key）
4. `tests/graph_paths/` — 路由契约测试
5. 若 HITL: `runner._status_from_pending` + `main.py` 新端点

#### 新增写工具
1. `app/tools/ops_tools.py` — `@tool` 函数
2. `app/tools/__init__.py` — 加入 `WRITE_TOOLS`
3. `app/tools/policy.py` — `TOOL_RISK` 风险级别
4. `app/adapters/mock_remediation.py` — mock 写后状态
5. 若需 stateful E2E: simulator 新 scenario + `mock_data` 投影
6. `data/runbooks/` — 对应 runbook（7 段模板）

#### 新增 Golden Case
1. `tests/rag_eval/golden.py` — `GOLDEN_CASES` 添加条目
2. `id` 唯一；`service` 与 runbook `适用范围` 一致
3. `telemetry` 足以支撑 `extract_symptoms` 产生判别性 query
4. hard 消歧加 `must_not_select`
5. 跑 `make test-rag` 验证

#### 新增 Simulator 场景
参照 `ops-backend-simulator/README.md` §Adding a new scenario（8 步清单）。

### 8.3 禁止事项

- ❌ 在未读对应组件「Agent 改动同步指南」的情况下跨组件大改
- ❌ 把 simulator 实现细节复制进 `docs/agent/` 文档
- ❌ 提交 `.env`、checkpoint db、审计日志、Chroma 索引标记、`data/scenario_runs/`
- ❌ LLM prompt 中包含 `relevant_runbook` 全文（全文由代码 `resolve_selected_runbook()` 加载）
- ❌ 在 agent 端重复维护 RAG 阈值或工具风险表 — 链到对应组件文档
- ❌ 在 `run_scenarios.py` 中为 KB 场景开启 real LLM（KB 固定 mock）

---

## 9. 常用命令速查

### 9.1 Makefile（monorepo 根执行）

| 命令 | 说明 |
|------|------|
| `make test` | 全量 pytest |
| `make test-rag-retrieval` | Track A：纯检索 |
| `make test-rag-coverage` | Track B：coverage rubric |
| `make test-rag` | 双轨合并 |
| `make test-graph` | 图路径契约（mock LLM） |
| `make test-api` | eval / tracing / health |
| `make test-simulator` | Simulator 状态机 |
| `make demo` | 离线三场景演示 |
| `make demo-real` | 交互式 real LLM 演示 |
| `make demo-real-auto` | 五幕连跑 |
| `make impact` | 工作区 diff → 建议文档 + 测试 |
| `make install-hooks` | 安装 pre-commit（按路径自动跑测试） |
| `make build / up / down` | Docker Compose |

### 9.2 场景表征

```bash
# KB mock smoke（固定 mock LLM + mock backend）
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios KB-01 KB-02

# real LLM 表征（仅 DEC / LOOP；需 simulator 在 :8081）
CHECKPOINTER=memory LLM_MODE=real BACKEND_MODE=real \
  .venv/bin/python scripts/run_scenarios.py --scenarios DEC-01 LOOP-02 LOOP-03 DEC-02

# mock LLM 全量（无 API，含 KB + simulator 场景的 mock LLM）
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --mock-llm --scenarios all

# 单场景步进 JSON
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios REM-01 --mock-llm --step-json
```

### 9.3 RAG 评测

```bash
# Golden 评测（local-hash, 含 reindex）
.venv/bin/python scripts/rag_eval.py --reindex --stage all

# Real LLM smoke (10 条)
EMBEDDINGS_PROVIDER=qwen LLM_MODE=real \
  .venv/bin/python scripts/rag_eval.py --stage real-llm --smoke --reindex
```

### 9.4 启动服务

```bash
# Mock 模式（免 API Key）
cd agent
BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Real LLM + Simulator
# 终端 1: cd ops-backend-simulator && SCENARIO_ID=ecomm-manager-rate-limit uvicorn simulator.app:app --port 8081
# 终端 2: cd agent && BACKEND_MODE=real LLM_MODE=real BACKEND_BASE_URL=http://127.0.0.1:8081 uvicorn app.main:app --port 8000
```

---

## 10. 数据目录说明

| 路径 | 内容 | 维护方式 |
|------|------|---------|
| `agent/data/runbooks/*.md` | 55 篇 runbook 语料 | 7 段模板；变更后 `reindex()` |
| `agent/data/incidents/` | 可选 incident 文档 | 不参与 CI |
| `agent/data/.rag_indexed_*` | 向量索引完成标记 | 自动生成，不提交 |
| `agent/data/scenario_runs/` | 场景运行报告 JSON | 自动生成，已 gitignore |
| `agent/eval/dataset.jsonl` | 15 场景 eval 数据集 | 手动维护 |

---

## 11. 关键设计决策（备忘）

### 11.1 检索与覆盖裁决分离
`retrieve_runbooks` 只做纯检索（无 LLM），coverage rubric 在 `diagnose` 节点完成。理由：检索是工程问题（hybrid/rerank/parent），裁决是语义问题（LLM rubric + 代码 policy），解耦后可独立评测和调优。

### 11.2 LLM 不选篇
LLM rubric 只输出每篇的四维 CoT 评分，选篇由 `finalize_runbook_coverage()` 代码完成。理由：LLM 选篇不稳定，代码规则可测、可调试。

### 11.3 diagnose/decide 二分
`runbook_available=true` 时有现成 runbook 可参考，走 runbook 路径（跳过 confidence LLM）；`runbook_available=false` 时走探索路径（decide 双模板，不传 runbook 段）。理由：有/无 KB 覆盖是两种根本不同的诊断模式。

### 11.4 KB 固定 mock smoke
KB-01/KB-02 在 `run_scenarios.py` 内强制 mock LLM + mock backend。理由：real LLM 下的 novel 判定和 draft 文案质量由 RAG golden (`make test-rag-coverage`) 保证；KB 场景只测图路由契约和写回链是否跑通。

### 11.5 推荐 DeepSeek V4 + Qwen embedding
Chat 走 DeepSeek（`OPENAI_BASE_URL=https://api.deepseek.com`），embedding 走 Qwen DashScope（`EMBEDDINGS_PROVIDER=qwen`）。两套凭证互不干扰，`invoke_structured()` 自动分流。

---

## 12. 快速调试指南

| 症状 | 优先排查 |
|------|---------|
| 图路由错误 | `builder.py` 路由函数, `decide_outcome`, `needs_approval` |
| 工具未执行 | `approve` 拒绝? 无 `tool_calls`? `pending_tool_calls()` |
| 假恢复 | `verify_remediation`, real LLM summary |
| novel 判定错误 | `retrieve_runbooks` top-3, `diagnose` coverage, `runbook_unavailable_reason`, `match_gate_reason` |
| 误跳过 decide | `confidence_sufficient`, `diagnose_spec` RCA rubric |
| RAG 召回差 | hybrid/rerank 分数, `extract_symptoms` query, BM25 索引是否过期 |
| Schema 校验崩溃 | coerce 函数, `invoke_structured()` fallback 路径, JSON 围栏 |
| Simulator 状态异常 | `GET /admin/state`, `fault_phase`, `is_recovered` |
| Checkpoint 反序列化警告 | `app/memory/short_term.py` → `allowed_msgpack_modules` |

---

## 13. 文档交叉引用

| 你想做什么 | 看哪个文档 |
|-----------|-----------|
| 了解全貌 | `docs/agent/architecture.md` |
| 改代码前走流程 | `docs/workflow/change-workflow.md` |
| 改图节点/路由 | `docs/agent/graph-agent-architecture.md` |
| 改 RAG 检索/阈值 | `docs/agent/rag-architecture-and-tests.md` §5 |
| 改决策/工具/审批 | `docs/agent/decide-remediation-architecture.md` §7 |
| 改后端适配/simulator 联调 | `docs/agent/backend-adapters-architecture.md` §7 |
| 改 KB 写回链 | `docs/agent/kb-lifecycle-architecture.md` §6 |
| 改 API/配置/LLM | `docs/agent/api-runtime-architecture.md` §7 |
| 查场景预期轨迹 | `docs/agent/test-scenario-trajectories.md` |
| 新增 simulator 场景 | `ops-backend-simulator/README.md` §Adding a new scenario |
| RAG golden/语料运维 | `docs/agent/rag-eval-corpus.md` |
| 已知问题 | `docs/agent/open-issues.md` |

---

## 14. 版本注记

- **2026-08-09**：初始 CLAUDE.md 创建，基于 AGENTS.md + 17 篇 docs 文档 + 完整源代码阅读。覆盖项目定位、monorepo 结构、技术栈、核心架构、配置、LLM 适配、测试体系、开发纪律、编码规范、命令速查、设计决策、调试指南。后续修改请在本节追加记录。
