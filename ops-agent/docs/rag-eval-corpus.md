# RAG 评测语料与金标准

> 完整 RAG 架构、**双轨测试**与 **Agent 改动同步指南** 见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §4。  
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

## 金标准集

- 定义：`tests/rag_eval/golden.py`（`GOLDEN_CASES`，46 条）
- 筛选：`select_golden_cases()`；smoke 子集 `REAL_LLM_SMOKE_IDS`（10 条）

## 运行评测（双轨）

```bash
# Track A — 纯检索（CI 友好）
make test-rag-retrieval
# 或：pytest tests/rag_eval/test_retrieval_golden.py -v

# Track B — coverage（检索 + oracle rubric + finalize）
make test-rag-coverage
# 或：pytest tests/rag_eval/test_coverage_golden.py -v

# 双轨合并
make test-rag

# JSON 报告（track_a_retrieval / track_b_coverage_oracle）
.venv/bin/python scripts/rag_eval.py --reindex --stage all
```

### Coverage oracle（Track B）

Harness：`run_retrieve_and_coverage()`（`nodes/eval_runbook.py`）。Oracle rubric 在 `runbook_coverage.py`：

- LLM 结构化输出仅为 `RunbookEvalLLMOutput.rubrics`（每篇四维 CoT PASS/PARTIAL/FAIL）
- `expected_novel=true`：所有候选 symptom FAIL 等 → `low_match`
- 有 `expected_doc_id`：期望篇全 PASS、其余弱匹配 → `finalize_runbook_match` 选 top1
- 选篇与 `runbook_eval_reasoning` 由代码生成，**不由 LLM 输出**

真实 LLM rubric（L3，不默认进 CI）：

```bash
RAG_EVAL_REAL_LLM=1 .venv/bin/pytest tests/rag_eval/test_real_llm_smoke.py -v
```

## 指标摘要

| 轨道 | 关键指标 |
|------|----------|
| A | `recall_at_3`, `mrr_at_1`, `must_not_violation_rate` |
| B | `end_to_end_accuracy`, `selection_accuracy`, `novel_accuracy` |

按 `challenge_type` 分层见 `scripts/rag_eval.py` 报告 `by_challenge`。

## 迭代顺序

1. 跑 Track A baseline → 看 `failed_cases`
2. 优先修 **must_not violation**
3. 调 query / ingest / rerank
4. 跑 Track B；必要时用 `qwen` embedding 复测

## 变更记录

### 2026-07-02 · CoT 范畴化评估

- PASS/PARTIAL/FAIL + 代码 policy；删除 match_score / diagnosis_confidence float。

### 2026-07-01 · relevance-only match_score

- Coverage rubric 仅 relevance 四维；`match_score` 替代 `coverage_confidence`；删除 fit/消歧/low_coverage。

### 2026-07-01 · 双轨测试 + coverage 命名

- Makefile：`test-rag-retrieval` / `test-rag-coverage` / `test-rag`；pytest markers `rag_only` / `rag_coverage`。
- Oracle 与图内 coverage 逻辑迁至 `runbook_coverage.py`；harness 入口 `run_retrieve_and_coverage()`。

### 2026-06-30 · DeepSeek chat + Qwen embedding

- L3 smoke：`RAG_EVAL_REAL_LLM=1 pytest tests/rag_eval/test_real_llm_smoke.py`；见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9

### 2026-06-30 · RAG eval 重构

- Coverage oracle：为 top-3 每篇输出 `RunbookPerDocRubric`；finalize 代码选篇；详见 [`rag-architecture-and-tests.md`](rag-architecture-and-tests.md) §9
