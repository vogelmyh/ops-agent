# RAG 评测语料与金标准

> 完整 RAG 架构、测试分层与 **Agent 改动同步指南** 见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md)。  
> **文档维护**：语料/golden/评测流程变更后，须在本文 **§变更记录** 追加修改摘要。

本文档描述 RAG offline eval 的 runbook 扩充与 golden set，与 `docs/test-scenario-trajectories.md` 中的全链路场景互补。

## 语料规模

| 类别 | 数量 |
|------|------|
| 原有生产 runbook | 17 |
| 新增扩充 runbook | 38 |
| **合计** | **55** |

新增 runbook 与原有混放在 `data/runbooks/`，统一 `reindex()` 入库。

生成命令：

```bash
.venv/bin/python scripts/generate_rag_corpus.py
CHECKPOINTER=memory EMBEDDINGS_PROVIDER=local-hash .venv/bin/python -c "from app.rag.ingest import reindex; reindex()"
```

## 关系矩阵（考验维度）

| 维度 | 新增篇数 | 金标准 challenge_type |
|------|----------|------------------------|
| 同服务消歧 | ~18 | `same_service_disambiguation` |
| 跨服务陷阱 | ~4 | `cross_service_trap` |
| 易匹配 | ~10 | `easy_match` |
| 词面陷阱 | ~3 | `lexical_trap` |
| 负向约束 | ~2 | `negative_constraint` |
| Novel | ~4 | `novel` |

## 金标准集

- 定义：`tests/rag_eval/golden.py`（`GOLDEN_CASES`，≥40 条）
- 每条含：`service`、`incident_description`、`telemetry` fixture、`expected_doc_id` / `expected_novel`、`must_not_select`

## 运行评测

```bash
# 检索层 golden eval（CI 友好）
.venv/bin/pytest tests/rag_eval/test_retrieval_golden.py -v

# 端到端 coverage（检索 + oracle rubric + finalize）
.venv/bin/pytest tests/rag_eval/test_coverage_golden.py -v

# 全部 RAG eval
.venv/bin/pytest tests/rag_eval/ -v

# 报告 JSON（retrieval + coverage）
.venv/bin/python scripts/rag_eval.py --reindex --stage all

# 真实 embedding（需 API key）
EMBEDDINGS_PROVIDER=qwen .venv/bin/python scripts/rag_eval.py --reindex --stage all
```

### 评测阶段

| 阶段 | 测什么 | Mock LLM |
|------|--------|----------|
| `retrieval` | hybrid → rerank → top-3 | 不涉及 |
| `coverage` | 上述 + per-doc rubric + `finalize_runbook_eval` | golden **oracle**（为 top-3 每篇打完美/低分 rubric，隔离检索与真实 LLM） |

**Coverage oracle 行为**（`eval_runbook._mock_llm_output_oracle`）：

- LLM 结构化输出仅为 `RunbookEvalLLMOutput.rubrics`（`RunbookPerDocRubric` 列表，含 Stage A+B）
- `expected_novel=true`：所有候选打低分 rubric → finalize 判 `low_relevance` / `low_coverage`
- 有 `expected_doc_id`：期望篇高分、其余低分 → finalize 按 relevance 选 top1 并过阈值
- 选篇与 `runbook_eval_reasoning` 均由 `finalize_runbook_eval` / `build_eval_reasoning` 生成，**不由 LLM 输出**

真实 LLM rubric 评测：设 `LLM_MODE=real` 并单独跑子集（不默认进 CI）。

```bash
# 10 条 hard smoke（需 OPENAI_API_KEY）
RAG_EVAL_REAL_LLM=1 .venv/bin/pytest tests/rag_eval/test_real_llm_smoke.py -v

# CLI：real LLM rubric 报告
EMBEDDINGS_PROVIDER=qwen LLM_MODE=real \
  .venv/bin/python scripts/rag_eval.py --stage real-llm --smoke --reindex

# 指定 case + limit
.venv/bin/python scripts/rag_eval.py --stage real-llm --llm real \
  --ids disambig-pool-vs-rds-01,lexical-restart-not-crashloop-01
```

## 指标

| 指标 | 含义 |
|------|------|
| `recall_at_3` | 期望 doc 在 top-3 parent 内 |
| `mrr_at_1` | 期望 doc 排名第一的倒数排名均值 |
| `wrong_top1_rate` | top1 不是期望 doc |
| `must_not_violation_rate` | 禁止 doc 出现在 top1 |

按 `challenge_type` 分层见 `report.by_challenge`。

### Coverage 阶段（`test_coverage_golden.py`）

| 指标 | 含义 |
|------|------|
| `end_to_end_accuracy` | 期望 doc 选中 / 期望 novel 均满足 |
| `selection_accuracy` | 有标注 doc 时 `selected_runbook_id` 正确 |
| `novel_accuracy` | `expected_novel` 时 `novel_scenario=true`（由低分 rubric + finalize 阈值触发，非 LLM `suggested_novel`） |

## 迭代顺序

1. 跑 baseline → 看 `failed_cases`
2. 优先修 **must_not violation**（误选比漏选危险）
3. 调 query 判别特征 / ingest metadata / rerank
4. 用 `qwen` 复测并对比 `local-hash` 与语义 embedding 差距

## 变更记录

### 2026-06-30 · DeepSeek chat + Qwen embedding

- 推荐 real LLM 评测组合：`OPENAI_*` → DeepSeek V4 chat；`EMBEDDINGS_PROVIDER=qwen` + `QWEN_*` → `text-embedding-v3`（chat 与 embedding 凭证分离，无需 reindex）
- L3 smoke：`RAG_EVAL_REAL_LLM=1 pytest tests/rag_eval/test_real_llm_smoke.py`；provider 细节见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9

### 2026-06-30 · RAG eval 重构

- Coverage oracle：为 top-3 每篇输出 `RunbookPerDocRubric`；`expected_novel` 时全候选低分 rubric
- 选篇与 `runbook_eval_reasoning` 不在 LLM/oracle 输出中，由 finalize 代码完成
- Golden 语料（`golden.py`）与检索门槛测试无需改动；详见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9
