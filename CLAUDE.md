# CLAUDE.md

<!-- Project constitution. Claude Code reads this file automatically in every session.
     Keep it short and factual: every line costs context. -->

## Project Overview

ops-agent is a production-like ops diagnosis & auto-remediation agent for an e-commerce SaaS platform. It receives incident tickets, collects telemetry, retrieves runbooks via RAG, diagnoses root cause with LLM, and executes remediation — all orchestrated by a **LangGraph state graph** exposed through **FastAPI HTTP API**. Falls back to HITL when the knowledge base has no coverage or when high-risk actions are selected.

## Tech Stack

- **Language**: Python 3.12
- **Agent Framework**: LangGraph (`StateGraph`) — 12 nodes + 6 conditional edges + 3 HITL interrupts
- **Web Framework**: FastAPI — 7 endpoints
- **LLM**: ChatOpenAI (DeepSeek V4 recommended), `invoke_structured()` with vendor-specific routing
- **Vector Store**: ChromaDB (`local-hash` mode, no API key needed)
- **Retrieval**: hybrid (Chroma + BM25 RRF) + lexical rerank — pure Python, no external service
- **Embedding**: Qwen `text-embedding-v3` (recommended) or `local-hash` (offline)
- **Checkpoint**: LangGraph sqlite / memory / redis
- **Observability**: Prometheus + LangSmith
- **Backend Simulator**: Python FastAPI (13 stateful fault scenarios)
- **Package manager**: uv (lockfile at `agent/uv.lock`); `pyproject.toml` with hatchling
- **Testing**: pytest — 5-layer pyramid + dual-track RAG

## Commands

Run from monorepo root:

```bash
make install-hooks              # one-time: pre-commit auto-runs path-based tests
make test                       # full pytest suite
make test-rag                   # dual-track RAG (retrieval + coverage)
make test-rag-retrieval         # Track A: recall@3, MRR@1
make test-rag-coverage          # Track B: selection accuracy
make test-graph                 # graph-path contracts (mock LLM)
make test-api                   # eval / tracing / health
make test-simulator             # simulator state machine
make demo                       # offline 3-scenario demo (no API keys)
make demo-real                  # interactive real-LLM demo
make impact                     # working-tree diff → suggested docs + tests
```

Scenario characterization:

```bash
# mock smoke (KB scenarios: fixed mock LLM)
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios KB-01 KB-02

# real LLM (DEC / LOOP; needs simulator on :8081)
CHECKPOINTER=memory LLM_MODE=real BACKEND_MODE=real \
  .venv/bin/python scripts/run_scenarios.py --scenarios DEC-01 LOOP-02

# single scenario step-JSON
CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios REM-01 --mock-llm --step-json
```

Start services:

```bash
# Mock mode (no API keys)
cd agent && BACKEND_MODE=mock LLM_MODE=mock EMBEDDINGS_PROVIDER=local-hash \
  .venv/bin/python -m uvicorn app.main:app --port 8000

# Real LLM + Simulator (two terminals)
# T1: cd ops-backend-simulator && SCENARIO_ID=ecomm-manager-rate-limit uvicorn simulator.app:app --port 8081
# T2: cd agent && BACKEND_MODE=real LLM_MODE=real BACKEND_BASE_URL=http://127.0.0.1:8081 uvicorn app.main:app --port 8000
```

## Project Structure

```text
ops-agent/                        # Git monorepo root
├── agent/                        # 🐍 Python 3.12 main project (LangGraph + FastAPI)
│   ├── app/
│   │   ├── main.py               # FastAPI entry, 7 endpoints
│   │   ├── config.py             # pydantic-settings, all configuration
│   │   ├── schemas.py            # Pydantic request/response models
│   │   ├── graph/                # LangGraph ★core★ — builder, runner, state, 12 nodes
│   │   ├── rag/                  # RAG pipeline — retrieval, hybrid, rerank, ingest, store
│   │   ├── tools/                # LangChain Tools — 7 read + 10 write + risk policy
│   │   ├── llm/provider.py       # invoke_structured() — single LLM entry point
│   │   ├── adapters/             # mock/real backend client + mock data + mock remediation
│   │   ├── memory/short_term.py  # LangGraph checkpointer (sqlite/memory/redis)
│   │   └── observability/        # Prometheus metrics + LangSmith tracing
│   ├── data/runbooks/            # 55 runbook markdown files (RAG indexing source)
│   ├── tests/                    # pytest — graph_paths/, rag_eval/, 30+ test files
│   ├── eval/                     # LLM eval — dataset.jsonl (15 scenarios), judges
│   ├── scripts/                  # CLI — demo, run_scenarios, rag_eval, demo_presenter/
│   └── pyproject.toml
├── ops-backend-simulator/        # 🧪 Stateful HTTP backend stand-in (13 scenarios)
├── ops-backend/                  # ☕ Java Spring Boot — production contract reference only
├── deploy/                       # 🚀 docker-compose.yml + k8s manifests
├── docs/                         # 📚 Component architecture docs (agent/), README
│   └── agent/                    # Detailed component docs — read before modifying code
├── tooling/                      # change_impact.py, migrate_paths.py
├── specs/                        # 📋 Spec-driven development documents
│   └── ops-agent/
│       ├── requirements.md       # what the project does (EARS format)
│       ├── design.md             # high-level architecture map
│       └── tasks.md              # dev workflow + maintenance task templates
└── Makefile                      # unified command entry
```

## Code Style & Conventions

### Development Discipline (mandatory 7-step SOP)

1. `git status / git diff` — confirm impact scope
2. Read the component doc for the affected area (see table below) + its §"Agent 改动同步指南"
3. **Output a sync plan before code** — list must-change code/tests/docs, no-change items, and verification commands. **Wait for user approval.**
4. Implement — small, revertible commits; order: logic + unit tests → integration tests → docs
5. Run targeted `make test-*`; paste pass/fail summary
6. Update changelog in affected component doc (date + 1–3 lines in §变更记录)
7. Self-check against the checklist in `specs/ops-agent/tasks.md`

### Change → Doc Mapping

| Change touches | Primary doc |
|----------------|-------------|
| `app/rag/`, `retrieve_runbooks`, `runbook_coverage` | `docs/agent/rag-architecture-and-tests.md` §5 |
| `builder.py`, `nodes/` (non-RAG), `runner.py` | `docs/agent/graph-agent-architecture.md` §6 |
| `decide`, `tools/`, `verify_remediation`, `approve` | `docs/agent/decide-remediation-architecture.md` §7 |
| `app/adapters/`, simulator integration | `docs/agent/backend-adapters-architecture.md` §7 |
| KB write-back chain | `docs/agent/kb-lifecycle-architecture.md` §6 |
| `main.py`, `config.py`, LLM/checkpoint | `docs/agent/api-runtime-architecture.md` §7 |
| Scenario IDs / expected trajectories | `docs/agent/test-scenario-trajectories.md` |

### LLM Rules

- `invoke_structured()` is the **only** structured-output entry point — all nodes must use it.
- **DeepSeek**: `json_mode` (API doesn't support `json_schema`); `thinking: disabled` by default.
- **Qwen/DashScope**: `include_raw` + ValidationError fallback to plain JSON.
- **New provider** → must update both `get_chat_model()` and `invoke_structured()` routing.
- **New LLM-output schema** → must add a coerce function + unit test. See existing 6 coerce functions in `app/graph/eval_schemas.py` and `app/graph/decide_spec.py`.

### Key Design Rules

- **Mock-first**: default `BACKEND_MODE=mock LLM_MODE=mock` — CI must run without API keys.
- **RAG never calls LLM**: retrieval is pure engineering; LLM rubric only in `diagnose` coverage stage.
- **LLM doesn't select runbooks**: LLM outputs rubric scores; `finalize_runbook_coverage()` code selects.
- **Single source of truth**: scenario IDs → `test-scenario-trajectories.md`; simulator → `ops-backend-simulator/README.md`; RAG thresholds → `config.py`.
- **Schema robustness**: all LLM JSON outputs validated through coerce functions before Pydantic parsing.

## Testing

5-layer pyramid:

| Layer | What | Command |
|-------|------|---------|
| L0: Simulator state machine | Fault injection → recovery transitions | `make test-simulator` |
| L1: Unit / policy | Individual functions, tool risk, coerce | `make test` |
| L2: Graph-path contracts | Full graph with mock LLM, fixed routes | `make test-graph` |
| L3: Golden / integration | RAG retrieval + coverage (46 golden cases) | `make test-rag` |
| L4: Scenario characterization | Real LLM E2E trajectories | `run_scenarios.py` |

Dual-track RAG: Track A (`make test-rag-retrieval`) = recall@3, MRR@1, must_not_violation; Track B (`make test-rag-coverage`) = selection accuracy, end_to_end_accuracy.

16 scenario IDs across REM / HITL / LOOP / DEC / KB / RAG / EXEC domains — see `docs/agent/test-scenario-trajectories.md`.

Definition of done: relevant `make test-*` passes, changelog updated, learnings written back.

## Constraints (Do NOT)

- ❌ Do not modify code without first reading the relevant component doc and outputting a sync plan.
- ❌ Do not copy simulator implementation details into `docs/agent/` — simulator docs live only in `ops-backend-simulator/README.md`.
- ❌ Do not commit `.env`, checkpoint databases, audit logs, Chroma index markers (`data/.rag_indexed_*`), or `data/scenario_runs/`.
- ❌ Do not include full `relevant_runbook` text in LLM prompts — full text is loaded by `resolve_selected_runbook()` in code.
- ❌ Do not enable real LLM for KB scenarios (KB-01/KB-02 force mock in `run_scenarios.py`).
- ❌ Do not duplicate RAG thresholds or tool risk tables across docs — link to the component doc.
- ❌ Do not add new runtime dependencies without asking.
- ❌ Do not modify files under `ops-backend/` (Java contract reference — not part of CI).

## Learnings / Gotchas

### Critical Concept Distinctions

- `runbook_available` (RAG coverage) ≠ `confidence_sufficient` (diagnosis quality) — first is a retrieval problem, second is a semantic problem.
- `runbook_available=false` → all write actions force HITL approval.
- `decide_outcome` values: `actionable` | `uncertain` | `out_of_scope` | `skipped_low_confidence`.
- `needs_approval` is set by `compute_needs_approval()` (policy.py), not by the LLM.

### Debugging Quick Reference

| Symptom | First check |
|---------|-------------|
| Wrong graph route | `builder.py` routing functions, `decide_outcome`, `needs_approval` |
| Tools not executing | Was `approve` rejected? `pending_tool_calls()` empty? |
| False recovery | `verify_remediation`, real-LLM summary |
| Wrong novel judgment | `retrieve_runbooks` top-3, `diagnose` coverage, `runbook_unavailable_reason` |
| Skipped decide node | `confidence_sufficient`, `diagnose_spec` RCA rubric |
| Poor RAG recall | hybrid/rerank scores, `extract_symptoms` query, stale BM25 index |
| Schema validation crash | coerce function, `invoke_structured()` fallback path, JSON fences |

### Design Decisions (why things are the way they are)

- **Retrieval/coverage separation**: retrieval is engineering (hybrid/rerank), coverage is semantic (LLM rubric + code policy). Decoupled for independent tuning.
- **LLM doesn't select**: code-based selection is deterministic and testable; LLM selection isn't.
- **diagnose/decide split**: with-KB vs without-KB are fundamentally different diagnosis modes.
- **KB scenarios force mock**: real-LLM novel/draft quality is guaranteed by RAG golden; KB scenarios only test graph routing.
- **DeepSeek json_mode**: DeepSeek API doesn't support `json_schema`; structured output uses `response_format: {"type": "json_object"}` with prompt injection.

## Spec-Driven Workflow

Feature work is driven by documents in `specs/{feature}/`:

- `requirements.md` — what to build (user stories, EARS acceptance criteria)
- `design.md` — how to build it (architecture, components, data models)
- `tasks.md` — ordered atomic task checklist with requirement traceability

The current project baseline is documented in:

- `specs/ops-agent/requirements.md` — what the project does (current built state)
- `specs/ops-agent/design.md` — high-level architecture map (references `docs/agent/` for details)

When a new feature is needed, create `specs/{feature}/` with the three spec documents above. `tasks.md` is created **only** when there is active development work — it contains concrete, atomic tasks with exact file paths, not workflow templates.

When implementing:

- Work through `tasks.md` top to bottom; mark tasks `- [x]` when complete.
- Follow the 7-step SOP in Code Style & Conventions above — always output a sync plan before code.
- If implementation reveals a spec document is wrong, update the document — do not silently diverge.
- After completing a task or solving a non-trivial bug, write any reusable insight into Learnings / Gotchas above.
- Before merge, run `make test` and update changelogs in affected `docs/agent/*.md` files.
