"""ecomm-order: memory leak / OOM on stable image."""

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

SCENARIO_ID = "ecomm-order-memory-leak"
SERVICE = "ecomm-order"
STABLE_IMAGE = "registry/ecomm-order:3.2.1"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    pod_restarts: int = 8
    order_success_rate: float = 0.82
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.pod_restarts = 8
        self.order_success_rate = 0.82
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.order_success_rate > 0.99

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "restart_pods":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable; use restart_pods",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        strategy = body.get("strategy") or "rolling"
        self.phase = Phase.RECOVERED
        self.pod_restarts = 0
        self.order_success_rate = 0.995
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"Restarted pods with {strategy} strategy; connection pool recovering",
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "pod_restarts": self.pod_restarts,
            "order_success_rate": self.order_success_rate,
            "image": STABLE_IMAGE,
        }


def _pods(state: State) -> list[PodStatus]:
    restarts = state.pod_restarts if state.phase == Phase.BROKEN else 0
    return [
        PodStatus(
            name=f"ecomm-order-{i}",
            ready=True,
            restarts=restarts + i,
            phase="Running",
            image=STABLE_IMAGE,
        )
        for i in range(3)
    ]


def project_logs(state: State, req: LogQueryRequest) -> LogQueryResult:
    if state.phase == Phase.RECOVERED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message="order processing resumed after rolling pod restart",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="java.lang.OutOfMemoryError: Java heap space",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="connection pool exhausted, cannot acquire connection",
                service=SERVICE,
            ),
        ]
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    msg = (
        "Order success rate recovered after pod restart"
        if state.phase == Phase.RECOVERED
        else "OOM and connection pool exhaustion on stable image"
    )
    return ServiceStatus(
        service=SERVICE,
        healthy=state.phase == Phase.RECOVERED,
        replicas_ready=3,
        replicas_desired=3,
        pods=_pods(state),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    return MetricSeries(
        service=SERVICE,
        metric="order_success_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=state.order_success_rate)],
    )


def project_k8s_events(state: State) -> K8sEventResult:
    if state.phase == Phase.RECOVERED:
        return K8sEventResult(service=SERVICE, total=0, events=[])
    events = [
        K8sEvent(
            timestamp=NOW,
            type="Warning",
            reason="OOMKilled",
            involved_object="pod/ecomm-order-0",
            message="Container ecomm-order was OOMKilled",
            service=SERVICE,
        ),
    ]
    return K8sEventResult(service=SERVICE, total=len(events), events=events)


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
