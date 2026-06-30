"""ecomm-manager: discount logic bug — out_of_scope, no ops recovery."""

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

SCENARIO_ID = "ecomm-manager-discount-bug"
SERVICE = "ecomm-manager"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
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
            message=(
                f"{action} cannot fix application logic bug; escalate to development team"
            ),
            status=OperationStatus.FAILED,
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {"out_of_scope": True, "escalation": "development team"}


def _pods() -> list[PodStatus]:
    return [
        PodStatus(
            name=f"ecomm-manager-{i}",
            ready=True,
            restarts=0,
            phase="Running",
            image="registry/ecomm-manager:2.0.8",
        )
        for i in range(2)
    ]


def project_logs(_state: State, req: LogQueryRequest) -> LogQueryResult:
    entries = [
        LogEntry(
            timestamp=NOW,
            level="ERROR",
            message="ArithmeticException: discount overflow in DiscountEngine",
            service=SERVICE,
        ),
        LogEntry(
            timestamp=NOW,
            level="ERROR",
            message="order amount mismatch: expected=99.00 actual=0.01",
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
        replicas_ready=2,
        replicas_desired=2,
        pods=_pods(),
        message="Pods healthy but order amount calculation incorrect",
    )


def project_metrics(_state: State) -> MetricSeries:
    return MetricSeries(
        service=SERVICE,
        metric="order_amount_error_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=0.12)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
