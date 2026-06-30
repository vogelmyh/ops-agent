"""ecomm-order: bad image upgrade CrashLoop."""

from __future__ import annotations

from dataclasses import dataclass

from simulator.schemas import (
    K8sEvent,
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

SCENARIO_ID = "ecomm-order-crashloop"
SERVICE = "ecomm-order"
BAD_IMAGE = "registry/ecomm-order:3.3.0-bad"
STABLE_IMAGE = "registry/ecomm-order:3.2.1-stable"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    image: str = BAD_IMAGE
    ready: int = 0
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.image = BAD_IMAGE
        self.ready = 0
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.ready == 3

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "rollback_deployment":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable; use rollback_deployment",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        self.image = STABLE_IMAGE
        self.phase = Phase.RECOVERED
        self.ready = 3
        target = body.get("target_version") or STABLE_IMAGE
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"Rolled back {SERVICE} to {target}, ready replicas recovering",
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {"image": self.image, "ready_replicas": self.ready, "desired_replicas": 3}


def _pods(state: State) -> list[PodStatus]:
    pods = []
    for i in range(3):
        ready = state.ready > i
        pods.append(
            PodStatus(
                name=f"ecomm-order-{i}",
                ready=ready,
                restarts=0 if ready else 12,
                phase="Running" if ready else "CrashLoopBackOff",
                image=state.image,
                reason=None if ready else "CrashLoopBackOff",
            )
        )
    return pods


def project_logs(state: State, req: LogQueryRequest) -> LogQueryResult:
    if state.phase == Phase.RECOVERED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message="Application started successfully after rollback",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="FATAL",
                message="Application startup failed",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="Back-off restarting failed container",
                service=SERVICE,
            ),
        ]
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    healthy = state.ready == 3
    msg = (
        "All replicas ready after rollback to stable image"
        if state.phase == Phase.RECOVERED
        else "All replicas failing after bad image upgrade"
    )
    return ServiceStatus(
        service=SERVICE,
        healthy=healthy,
        replicas_ready=state.ready,
        replicas_desired=3,
        pods=_pods(state),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    return MetricSeries(
        service=SERVICE,
        metric="ready_replicas",
        unit="count",
        points=[MetricPoint(timestamp=NOW, value=float(state.ready))],
    )


def project_k8s_events(state: State) -> K8sEventResult:
    if state.phase == Phase.RECOVERED:
        return K8sEventResult(service=SERVICE, total=0, events=[])
    events = [
        K8sEvent(
            timestamp=NOW,
            type="Warning",
            reason="BackOff",
            involved_object="pod/ecomm-order-0",
            message="Back-off restarting failed container ecomm-order",
            service=SERVICE,
        ),
        K8sEvent(
            timestamp=NOW,
            type="Warning",
            reason="Unhealthy",
            involved_object="pod/ecomm-order-1",
            message="Readiness probe failed: connection refused :8080",
            service=SERVICE,
        ),
    ]
    return K8sEventResult(service=SERVICE, total=len(events), events=events)


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(
        service=SERVICE,
        action="deploy",
        message=f"Deployed {BAD_IMAGE} (bad release)",
    )


def project_streams(_state: State) -> list:
    return []
