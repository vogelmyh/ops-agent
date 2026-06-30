"""ecomm-order: RDS timeout — out_of_scope, no ops recovery."""

from __future__ import annotations

from dataclasses import dataclass

from simulator.schemas import (
    K8sEventResult,
    LogEntry,
    LogQueryRequest,
    LogQueryResult,
    MetricPoint,
    MetricSeries,
    OperationResult,
    OperationStatus,
    PodStatus,
    ServiceStatus,
)
from simulator.scenarios.common import NOW, Phase, op_result

SCENARIO_ID = "ecomm-order-rds-timeout"
SERVICE = "ecomm-order"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    order_success_rate: float = 0.45
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.order_success_rate = 0.45
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return False

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"{action} cannot fix managed RDS outage; escalate to DBA / cloud RDS on-call",
            status=OperationStatus.FAILED,
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "out_of_scope": True,
            "escalation": "DBA / cloud RDS on-call",
            "order_success_rate": self.order_success_rate,
        }


def _pods() -> list[PodStatus]:
    return [
        PodStatus(
            name=f"ecomm-order-{i}",
            ready=True,
            restarts=0,
            phase="Running",
            image="registry/ecomm-order:3.2.1",
        )
        for i in range(3)
    ]


def project_logs(_state: State, req: LogQueryRequest) -> LogQueryResult:
    entries = [
        LogEntry(
            timestamp=NOW,
            level="ERROR",
            message="SQLException: Connection timed out waiting for RDS",
            service=SERVICE,
        ),
        LogEntry(
            timestamp=NOW,
            level="ERROR",
            message="HikariPool: Connection is not available, request timed out",
            service=SERVICE,
        ),
        LogEntry(
            timestamp=NOW,
            level="ERROR",
            message="order persist failed: database unreachable",
            service=SERVICE,
        ),
    ]
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(_state: State) -> ServiceStatus:
    return ServiceStatus(
        service=SERVICE,
        healthy=True,
        replicas_ready=3,
        replicas_desired=3,
        pods=_pods(),
        message="Order persist failures reported; checkout success rate degraded",
    )


def project_metrics(state: State) -> MetricSeries:
    return MetricSeries(
        service=SERVICE,
        metric="order_success_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=state.order_success_rate)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
