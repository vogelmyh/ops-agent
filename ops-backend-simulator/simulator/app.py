"""FastAPI application — ops-backend compatible routes + admin debug."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from simulator.schemas import (
    AdminStateResponse,
    K8sEventResult,
    LogQueryRequest,
    LogQueryResult,
    MetricSeries,
    OperationResult,
    OpsRequest,
    ServiceStatus,
)
from simulator.scenarios.registry import list_scenarios
from simulator.session import ScenarioSession

ALLOWED_OPS_ACTIONS = frozenset(
    {
        "rollback_deployment",
        "scale_deployment",
        "restart_deployment",
        "delete_pod",
        "cordon_node",
        "drain_node",
        "enable_circuit_breaker",
        "flush_cache",
        "patch_config",
        "toggle_feature_flag",
    }
)

session = ScenarioSession()

app = FastAPI(title="ops-backend-simulator", version="0.2.0")


def _require_service(service: str) -> None:
    if service != session.service:
        raise HTTPException(
            status_code=404,
            detail=f"unknown service: {service} (active scenario service={session.service})",
        )


@app.get("/actuator/health")
def health() -> dict:
    return {"status": "UP"}


@app.post("/api/v1/logs/query", response_model=LogQueryResult)
def query_logs(req: LogQueryRequest) -> LogQueryResult:
    _require_service(req.service)
    return session.project_logs(req)


@app.get("/api/v1/services/{service}/status", response_model=ServiceStatus)
def service_status(service: str) -> ServiceStatus:
    _require_service(service)
    return session.project_status()


@app.get("/api/v1/services/{service}/metrics", response_model=MetricSeries)
def service_metrics(service: str) -> MetricSeries:
    _require_service(service)
    return session.project_metrics()


@app.get("/api/v1/services/{service}/k8s-events", response_model=K8sEventResult)
def k8s_events(service: str) -> K8sEventResult:
    _require_service(service)
    return session.project_k8s_events()


@app.get("/api/v1/services/{service}/operations/latest", response_model=OperationResult)
def latest_operation(service: str) -> OperationResult:
    _require_service(service)
    return session.project_latest_operation()


@app.get("/api/v1/services/{service}/streams")
def stream_states(service: str) -> list:
    _require_service(service)
    return session.project_streams()


@app.post("/api/v1/ops/{action}", response_model=OperationResult)
def ops_action(action: str, req: OpsRequest) -> OperationResult:
    if action not in ALLOWED_OPS_ACTIONS:
        raise HTTPException(status_code=404, detail=f"unknown ops action: {action}")
    _require_service(req.service)
    body = req.model_dump(exclude_none=True, exclude={"service"})
    return session.apply_ops(action, body)


@app.get("/admin/scenarios")
def admin_list_scenarios() -> list[dict[str, str]]:
    return list_scenarios()


@app.post("/admin/scenario/{scenario_id}")
def admin_load_scenario(scenario_id: str) -> dict:
    try:
        session.load(scenario_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_id}") from None
    session.reset()
    return {"status": "loaded", "scenario": session.scenario_id, "service": session.service}


@app.get("/admin/state", response_model=AdminStateResponse)
def admin_state() -> AdminStateResponse:
    payload = session.admin_payload()
    return AdminStateResponse(**payload)


@app.post("/admin/reset")
def admin_reset() -> dict:
    session.reset()
    return {"status": "reset", "scenario": session.scenario_id, "phase": session.admin_payload()["phase"]}
