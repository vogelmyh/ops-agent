"""ecomm-order: payment-gw upstream failure — open circuit breaker."""

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

SCENARIO_ID = "ecomm-order-payment-circuit"
SERVICE = "ecomm-order"
UPSTREAM = "payment-gw"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    circuit_open: bool = False
    payment_error_rate: float = 0.82
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.circuit_open = False
        self.payment_error_rate = 0.82
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.circuit_open

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "enable_circuit_breaker":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable; use enable_circuit_breaker",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        upstream = body.get("upstream")
        cb_state = body.get("state")
        if upstream != UPSTREAM or cb_state != "open":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"Expected upstream={UPSTREAM!r} state=open; got {upstream!r} {cb_state!r}",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        self.phase = Phase.RECOVERED
        self.circuit_open = True
        self.payment_error_rate = 0.15
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"Circuit breaker OPEN for {UPSTREAM}; fast-fail protecting thread pool",
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "upstream": UPSTREAM,
            "circuit_open": self.circuit_open,
            "payment_error_rate": self.payment_error_rate,
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


def project_logs(state: State, req: LogQueryRequest) -> LogQueryResult:
    if state.phase == Phase.RECOVERED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message=f"circuit breaker OPEN for {UPSTREAM}",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message=f"payment gateway timeout: upstream {UPSTREAM} unreachable",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message=f"PaymentClient: 503 from {UPSTREAM}, circuit not open",
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
        f"Circuit breaker open on {UPSTREAM}, payment storm contained"
        if state.phase == Phase.RECOVERED
        else "Payment gateway errors elevated on checkout path"
    )
    return ServiceStatus(
        service=SERVICE,
        healthy=True,
        replicas_ready=3,
        replicas_desired=3,
        pods=_pods(),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    return MetricSeries(
        service=SERVICE,
        metric="payment_error_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=state.payment_error_rate)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
