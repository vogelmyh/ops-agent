"""ecomm-manager: bad image upgrade CrashLoop."""

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

SCENARIO_ID = "ecomm-manager-crashloop"
SERVICE = "ecomm-manager"
BAD_IMAGE = "registry/ecomm-manager:2.1.0-bad"
STABLE_IMAGE = "registry/ecomm-manager:2.0.8-stable"


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
        return self.phase == Phase.RECOVERED and self.ready == 2

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

        target = body.get("target_version") or STABLE_IMAGE
        self.image = STABLE_IMAGE if "stable" in str(target) else str(target)
        self.phase = Phase.RECOVERED
        self.ready = 2
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"Rolled back {SERVICE} to {self.image}, ready replicas recovering",
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {"image": self.image, "ready_replicas": self.ready, "desired_replicas": 2}


def _pods(state: State) -> list[PodStatus]:
    pods = []
    for i in range(2):
        ready = state.ready > i
        pods.append(
            PodStatus(
                name=f"ecomm-manager-{i}",
                ready=ready,
                restarts=0 if ready else 14,
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
                message="Application startup failed: health check server failed to start",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="Health check server failed to start on :8080: connection refused",
                service=SERVICE,
            ),
        ]
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    healthy = state.ready == 2
    msg = (
        "All replicas ready after rollback to stable image"
        if state.phase == Phase.RECOVERED
        else "All replicas failing after bad image upgrade"
    )
    return ServiceStatus(
        service=SERVICE,
        healthy=healthy,
        replicas_ready=state.ready,
        replicas_desired=2,
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
            involved_object="pod/ecomm-manager-0",
            message="Back-off restarting failed container ecomm-manager in pod ecomm-manager-0",
            service=SERVICE,
        ),
        K8sEvent(
            timestamp=NOW,
            type="Warning",
            reason="Unhealthy",
            involved_object="pod/ecomm-manager-1",
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
