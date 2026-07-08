# ops-backend-simulator

Stateful Python HTTP backend for **ops-agent** eval and manual debugging. Exposes the same REST contract as [ops-backend](../ops-backend) (Java), with **write-aware telemetry** per scenario.

## Design intent

Simulator is a **stateful stand-in for the real backend**, not a catalog of full agent E2E tests.

### What it is responsible for

1. **Read path (before write)** — Project consistent fault evidence for diagnosis: `logs`, `metrics`, `status`, `k8s_events`, etc. Initial state is always `BROKEN` (or scenario-equivalent) after `/admin/reset`.
2. **Write path** — Accept ops-agent write tools via `POST /api/v1/ops/{action}`, update internal `State`, return `OperationResult` (SUCCEEDED / FAILED + message).
3. **Read path (after write)** — Post-write telemetry must reflect the new state so `eval_remediation` can tell whether the incident actually recovered.

Together this is the **write → read verification loop** that mock-only tests cannot fully exercise.

### Fault script types

| Type | Examples | `is_recovered` |
|------|----------|----------------|
| **Recoverable** | rate-limit, feature-flag, crashloop, stream-paused, … | `true` after correct write |
| **Static unrecoverable** | discount-bug, rds-timeout | always `false`; writes FAIL or do not help |
| **Dynamic chaos** | chaos-morph (recoverable demo), chaos-oos (early OOS) | rules change after a correct step (morph) |
| **Layered cascade** | cascade-exhaust | each correct write reveals next ops-fixable layer; never `RECOVERED` |

Chaos scenarios are for **react-loop / honest-termination** testing (LOOP / DEC in ops-agent), not the only reason Simulator exists.

### Relationship to ops-agent tests

| agent layer | Uses Simulator? | Role of Simulator |
|-----------------|-----------------|-------------------|
| `agent/tests/graph_paths/` (mock LLM) | Usually **no** — `mock_data` mirrors logic | Optional for LOOP/DEC integration (real `BACKEND_MODE`) |
| `agent/scripts/run_scenarios.py` (real LLM) | **yes** | Ground truth for write + post-write telemetry |
| KB / HITL / `block_remediation` tests | **no** | Novel services and agent-side hooks, not backend worlds |

- **Simulator `SCENARIO_ID`** = backend world script (e.g. `ecomm-manager-cascade-exhaust`).
- **agent test ID** = agent behaviour spec (e.g. `LOOP-03`) — see [test-scenario-trajectories.md](../docs/agent/test-scenario-trajectories.md).
- When mock LLM is used with Simulator, also set `set_mock_scenario(service, "<key>")` in ops-agent (`cascade-exhaust`, not the full scenario id).

Simulator defines **world truth**; agent tests assert **graph + LLM behaviour** in that world.

## E-commerce scenarios (default)

| Scenario ID | Service | Type | Fix (write tool) |
|-------------|---------|------|------------------|
| `ecomm-manager-rate-limit` | ecomm-manager | recoverable | `patch_config` (`rate-limit.max-qps=5000`) |
| `ecomm-manager-feature-flag` | ecomm-manager | recoverable | `toggle_feature_flag` (`promotion-v2=false`) |
| `ecomm-manager-crashloop` | ecomm-manager | recoverable | `rollback_deployment` |
| `ecomm-manager-disk-full` | ecomm-manager | recoverable | `cleanup_storage` |
| `ecomm-manager-discount-bug` | ecomm-manager | static OOS | no recovery (logic bug) |
| `ecomm-manager-chaos-morph` | ecomm-manager | chaos (recoverable) | `patch_config` then `toggle_feature_flag` |
| `ecomm-manager-cascade-exhaust` | ecomm-manager | layered exhaust | rate-limit → feature-flag → disk-full → conn-leak; never `RECOVERED` |
| `ecomm-manager-chaos-oos` | ecomm-manager | chaos (early OOS) | morph to logic bug; ops cannot fix |
| `ecomm-order-stream-paused` | ecomm-order | recoverable | `resume_event_stream` (`order-events`) |
| `ecomm-order-memory-leak` | ecomm-order | recoverable | `restart_pods` |
| `ecomm-order-payment-circuit` | ecomm-order | recoverable | `enable_circuit_breaker` (`payment-gw`, open) |
| `ecomm-order-crashloop` | ecomm-order | recoverable | `rollback_deployment` |
| `ecomm-order-rds-timeout` | ecomm-order | static OOS | no recovery (RDS / PaaS) |

Default active scenario: **`ecomm-manager-rate-limit`**.

## Adding a new scenario

Use this checklist so Simulator, runbooks, mock_data, and tests stay aligned.

### 1. Decide if you need Simulator at all

Add a Simulator module only when the test needs **`BACKEND_MODE=real`** and a **stateful write → read** loop.

Do **not** add Simulator for: novel services (KB), pure HITL gates, `block_remediation`, or RAG-only cases — handle those in ops-agent `mock_data` / graph tests.

### 2. Implement the scenario module

Create `simulator/scenarios/ecomm_<service>_<name>.py` with:

- `SCENARIO_ID`, `SERVICE`, `@dataclass State` with `reset()`, `apply_ops()`, `is_recovered`
- Projections: `project_logs`, `project_status`, `project_metrics`, … (reuse patterns from siblings)
- `apply_ops` must:
  - Return **FAILED** for wrong action, wrong params, or unmet preconditions (do not throw).
  - Update **all** read projections that `eval_remediation` checks (metrics names, log messages, `phase`).
  - Set `phase=RECOVERED` only when `is_recovered` should be true.

Register in `simulator/scenarios/registry.py`.

### 3. Keep symptoms neutral in logs/status

Avoid embedding the fix in log text (e.g. “run patch_config with key X”). Logs should look like production alerts; runbooks carry remediation hints.

### 4. Mirror in ops-agent `mock_data` (for mock backend)

For each new `ecomm-manager` / `ecomm-order` scenario key, extend `mock_data.py` so `BACKEND_MODE=mock` and `real` stay consistent.

### 5. Agent mock matrix (mock LLM only)

If graph_paths tests use mock LLM, update `decide_spec.py`, `diagnose.py`, `verify_remediation.py` as needed. Use a **short mock key** (e.g. `cascade-exhaust`) separate from `SCENARIO_ID`.

### 6. Runbook

Add `agent/data/runbooks/ecomm-<service>-<name>.md` (7-section template), then reindex RAG if the scenario should be retrievable.

### 7. Tests

| Where | What |
|-------|------|
| `ops-backend-simulator/tests/` | State machine: `apply_ops` transitions, `is_recovered`, morph phases |
| `agent/tests/graph_paths/` | Graph contract with mock LLM (+ Simulator if real backend path) |
| `agent/scripts/run_scenarios.py` | Optional real-LLM characterization + LangSmith |
| `docs/agent/test-scenario-trajectories.md` | Human/agent spec: new **test ID** (REM/HITL/LOOP/…), steps, simulator fields |

### 8. Naming

- **Simulator**: `ecomm-manager-<kebab-name>` (`SCENARIO_ID`)
- **Mock key**: short name without service prefix when scoped by service in `set_mock_scenario`
- **Test ID**: capability code + number (`LOOP-04`), documented in trajectories — not required to equal `SCENARIO_ID`

### 9. Chaos-specific rules

- State **morph** only on **correct** remediation steps (wrong tool should FAIL, not advance the script).
- If the story is **unrecoverable**, `is_recovered` must stay `false` even when ops return SUCCEEDED.
- Document whether the agent should **exhaust** react loops (LOOP) or **exit early** out_of_scope (DEC).

## Run

```bash
cd ops-backend-simulator
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn simulator.app:app --host 0.0.0.0 --port 8081
```

Point agent at the simulator (联调步骤与验收点见 [docs/agent/backend-adapters-architecture.md](../docs/agent/backend-adapters-architecture.md) §5；本文保留实现与场景细节):

```bash
export BACKEND_MODE=real
export BACKEND_BASE_URL=http://localhost:8081
```

## Admin (simulator-only)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin/scenarios` | List scenario ids |
| POST | `/admin/scenario/{id}` | Load scenario + reset to BROKEN |
| GET | `/admin/state` | Dump internal state |
| POST | `/admin/reset` | Reset current scenario |

## Write API

`POST /api/v1/ops/{action}` — aligned with ops-agent write tools and ops-backend.

Example:

```json
POST /api/v1/ops/patch_config
{
  "service": "ecomm-manager",
  "config_key": "rate-limit.max-qps",
  "config_value": "5000"
}
```

Runbooks: `agent/data/runbooks/ecomm-*.md`.

## Tests

```bash
pytest -q
```
