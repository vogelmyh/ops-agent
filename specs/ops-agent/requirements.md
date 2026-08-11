# Requirements: ops-agent

**Status**: Approved
**Source**: extracted from existing codebase (CLAUDE.md v2026-08-09, docs/agent/, agent/app/)

## Introduction

ops-agent 是一个拟真电商 SaaS 运维诊断与自动修复 Agent。它接收故障工单，自动采集遥测数据，通过 RAG 检索 runbook 知识库，利用 LLM 诊断根因并执行修复操作。知识库无法覆盖时走 HITL 写回新 runbook。系统基于 LangGraph 状态图编排，通过 FastAPI 对外暴露 HTTP API。

## Requirements

### Requirement 1: Incident Triage

**User Story:** As an SRE, I want the agent to classify an incoming incident by affected service, so that targeted runbooks can be retrieved.

#### Acceptance Criteria

1. WHEN an incident is submitted via `POST /incident` THEN the agent SHALL identify the affected service from the incident description and telemetry context.
2. The identified service SHALL be stored in `AgentState.target_service`.

### Requirement 2: Telemetry Collection

**User Story:** As an SRE, I want the agent to automatically collect logs, metrics, and status data for the affected service, so that diagnosis is based on objective evidence.

#### Acceptance Criteria

1. WHEN diagnosis begins THEN the agent SHALL collect telemetry from the backend via the configured adapter (mock or real).
2. WHEN `BACKEND_MODE=mock` THEN telemetry SHALL be sourced from `agent/app/adapters/mock_data.py`.
3. WHEN `BACKEND_MODE=real` THEN telemetry SHALL be fetched via HTTP from the backend service.
4. Collected telemetry SHALL be stored in `AgentState.telemetry_snapshot`.

### Requirement 3: Runbook Retrieval (RAG)

**User Story:** As an SRE, I want the agent to find the most relevant runbooks from the knowledge base, so that diagnosis can leverage past incident playbooks.

#### Acceptance Criteria

1. WHEN symptoms are extracted from the incident THEN the agent SHALL perform hybrid retrieval (Chroma vector + BM25, RRF fusion) to get top-20 chunks.
2. The top-20 chunks SHALL be reranked (fusion score + BM25 + lexical overlap) to top-10.
3. Parent document expansion SHALL expand chunks to full runbook excerpts, returning the top-3 `RunbookCandidate` objects.
4. Retrieval SHALL NOT invoke any LLM — it is a pure search pipeline.
5. IF no runbook matches the query THEN `runbook_available` SHALL be set to `false`.

### Requirement 4: Root Cause Diagnosis

**User Story:** As an SRE, I want the agent to produce a root cause analysis with a confidence score, so that I can trust or escalate the diagnosis.

#### Acceptance Criteria

1. WHEN `runbook_available=true` THEN the agent SHALL evaluate top-3 runbook candidates via LLM rubric (4-dimension CoT: relevance, coverage, actionability, correctness) and use code-based `finalize_runbook_coverage()` to select the best match.
2. WHEN `runbook_available=false` THEN the agent SHALL perform exploratory diagnosis without runbook guidance.
3. The agent SHALL produce a `RootCauseDraft` with hypothesis and evidence sources.
4. The agent SHALL assess confidence; IF `confidence_sufficient=false` THEN the graph SHALL route to summary (skip decide/remediate).
5. Confidence thresholds SHALL be configurable via `diagnosis_confidence_max_partial`.

### Requirement 5: Remediation Decision

**User Story:** As an SRE, I want the agent to classify incidents as actionable, uncertain, or out-of-scope, so that only safe remediations proceed.

#### Acceptance Criteria

1. WHEN diagnosis is complete and confidence is sufficient THEN the agent SHALL classify the incident as `actionable`, `uncertain`, or `out_of_scope`.
2. `actionable` outcomes SHALL proceed to tool selection; `uncertain` and `out_of_scope` SHALL route to summary.
3. WHEN `runbook_available=false` THEN all write actions SHALL require HITL approval.

### Requirement 6: HITL Approval Gate

**User Story:** As an SRE, I want high-risk remediation actions to require my explicit approval, so that dangerous changes cannot run automatically.

#### Acceptance Criteria

1. WHEN `compute_needs_approval()` returns true THEN the graph SHALL interrupt at the `approve` node and return `awaiting_approval` status.
2. `needs_approval` SHALL be true if: (a) any HIGH-risk tool is selected, (b) `remediation_attempt >= 1` and incident is not yet resolved, or (c) `runbook_available=false`.
3. The user SHALL resume via `POST /approve` with `{approved: true/false}`.
4. WHEN approved THEN execution proceeds; WHEN rejected THEN the graph routes to summary.

### Requirement 7: Remediation Execution

**User Story:** As an SRE, I want the agent to execute the selected remediation tools automatically, so that incidents are resolved quickly.

#### Acceptance Criteria

1. The agent SHALL select tools from 10 write tools across 3 risk tiers (HIGH: rollback, scale, drain; MEDIUM: restart, delete_pod, cordon, circuit_breaker, flush_cache; LOW: patch_config, toggle_feature_flag).
2. WHEN `BACKEND_MODE=mock` THEN tool execution SHALL use `mock_remediation.py`; WHEN `real` THEN HTTP to backend.
3. Execution results SHALL be recorded in `AgentState.pending_tool_results`.

### Requirement 8: Remediation Verification

**User Story:** As an SRE, I want the agent to verify that remediation actually resolved the incident, so that I don't close unresolved issues.

#### Acceptance Criteria

1. AFTER tool execution THEN the agent SHALL re-collect telemetry and evaluate whether the incident is resolved.
2. WHEN resolved THEN the graph SHALL route to summary.
3. WHEN not resolved AND `remediation_attempt < max_remediation_attempts` (default 3) THEN the agent SHALL re-enter diagnosis (react loop).
4. WHEN not resolved AND max attempts exhausted THEN the graph SHALL route to summary with failure status.

### Requirement 9: Knowledge Base Write-Back

**User Story:** As an SRE, I want the agent to draft new runbooks when the knowledge base has no coverage, so that the system learns from novel incidents.

#### Acceptance Criteria

1. WHEN `runbook_available=false` (after summary) THEN the agent SHALL interrupt at `request_runbook_notes` and return `awaiting_runbook_notes` status.
2. The user SHALL provide notes via `POST /runbooks/notes`.
3. The agent SHALL draft a runbook from notes, then interrupt at `review_runbook` (`awaiting_runbook_review`).
4. The user SHALL approve/edit via `POST /runbooks/review`.
5. WHEN approved THEN the runbook SHALL be ingested into the knowledge base (indexed for future retrieval).

### Requirement 10: Summary Generation

**User Story:** As an SRE, I want a structured summary of the entire incident lifecycle, so that I have an audit trail.

#### Acceptance Criteria

1. AFTER either successful remediation, max-retry exhaustion, or out-of-scope decision THEN the agent SHALL generate a summary.
2. The summary SHALL include: incident ID, service, diagnosis, actions taken, outcome, and runbook coverage status.

## Edge Cases

- WHEN the backend is unreachable in `real` mode THEN telemetry collection SHALL fail gracefully with a clear error status.
- WHEN LLM returns malformed JSON THEN `invoke_structured()` SHALL apply schema coerce functions as fallback before failing.
- WHEN rerank scores are below `retrieval_rerank_min_score` (0.15 default, 0 for local-hash) THEN candidates SHALL be filtered out.
- WHEN `runbook_match_min_pass_count` (default 2) is not met THEN the runbook SHALL be marked as not selectable (`runbook_available=false`).

## Non-Functional Requirements

- **Mock-first**: default `BACKEND_MODE=mock LLM_MODE=mock` — the full CI pipeline must run without API keys.
- **Observability**: all graph runs SHALL emit Prometheus `RUN_LATENCY` histogram; LangSmith tracing when configured.
- **Testability**: every agent path SHALL be verifiable via graph-path contract tests (mock LLM, fixed routes).
- **Compatibility**: existing scenario IDs (REM-01 through EXEC-02, 16 total) SHALL maintain their expected trajectories.
- **Vendor neutrality**: LLM provider (DeepSeek, Qwen, OpenAI) SHALL be switchable via `OPENAI_BASE_URL` + `OPENAI_MODEL`.

## Non-Goals

- Real-time alert ingestion from monitoring systems (out of scope — incidents are submitted manually via API).
- Multi-tenant incident management dashboard.
- Automated rollback orchestration beyond tool-level execution.
- Self-healing infrastructure provisioning (the agent diagnoses and remediates within existing services, does not provision new resources).

## Open Questions

*(none — this document describes the current built state)*
