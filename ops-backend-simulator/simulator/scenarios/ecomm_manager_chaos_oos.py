"""ecomm-manager Type C-②: morph reveals application logic bug; ops catalog cannot remediate."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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

SCENARIO_ID = "ecomm-manager-chaos-oos"
SERVICE = "ecomm-manager"
CONFIG_KEY = "rate-limit.max-qps"
BASELINE_VALUE = "5000"
BROKEN_VALUE = "50"
BROKEN_QPS = 400.0
RECOVERED_QPS = 7800.0


class FaultPhase(str, Enum):
    MASKED = "MASKED"
    REVEALED_LOGIC = "REVEALED_LOGIC"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    fault_phase: FaultPhase = FaultPhase.MASKED
    max_qps: str = BROKEN_VALUE
    admin_api_qps: float = BROKEN_QPS
    order_amount_error_rate: float = 0.12
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.fault_phase = FaultPhase.MASKED
        self.max_qps = BROKEN_VALUE
        self.admin_api_qps = BROKEN_QPS
        self.order_amount_error_rate = 0.12
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return False

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if self.fault_phase == FaultPhase.MASKED and action == "patch_config":
            key = body.get("config_key")
            value = body.get("config_value")
            if key != CONFIG_KEY:
                result = op_result(
                    service=SERVICE,
                    action=action,
                    message=f"Unknown config_key {key!r}; expected {CONFIG_KEY}",
                    status=OperationStatus.FAILED,
                    op_id=f"op-{self.op_counter}",
                )
                self.last_operation = result
                return result
            self.max_qps = str(value)
            if str(value) == BASELINE_VALUE:
                self.fault_phase = FaultPhase.REVEALED_LOGIC
                self.admin_api_qps = RECOVERED_QPS
                msg = f"Patched {CONFIG_KEY}={value}; config reload completed"
            else:
                msg = (
                    f"Patched {CONFIG_KEY}={value} but baseline is {BASELINE_VALUE}; "
                    "rate limiting persists"
                )
            result = op_result(
                service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}"
            )
            self.last_operation = result
            return result

        result = op_result(
            service=SERVICE,
            action=action,
            message=f"{action} cannot fix application logic defect; escalate to development team",
            status=OperationStatus.FAILED,
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "chaos_type": "C-oos",
            "fault_phase": self.fault_phase.value,
            "max_qps": self.max_qps,
            "admin_api_qps": int(self.admin_api_qps),
            "order_amount_error_rate": self.order_amount_error_rate,
            "phase": self.phase.value,
            "out_of_scope": True,
            "recoverable": False,
        }


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


def project_logs(state: State, req: LogQueryRequest) -> LogQueryResult:
    if state.fault_phase == FaultPhase.MASKED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message="rate limit exceeded for merchant-api",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message=(
                    f"RateLimitFilter: threshold misconfigured max-qps={state.max_qps} "
                    f"expected={BASELINE_VALUE}"
                ),
                service=SERVICE,
            ),
        ]
    else:
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


def project_status(state: State) -> ServiceStatus:
    if state.fault_phase == FaultPhase.MASKED:
        msg = "Merchant admin API QPS below baseline; elevated latency on admin endpoints"
    else:
        msg = "Merchant admin API QPS within baseline; order amount validation failures elevated"
    return ServiceStatus(
        service=SERVICE,
        healthy=True,
        replicas_ready=2,
        replicas_desired=2,
        pods=_pods(),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    if state.fault_phase == FaultPhase.MASKED:
        return MetricSeries(
            service=SERVICE,
            metric="admin_api_qps",
            unit="req/s",
            points=[MetricPoint(timestamp=NOW, value=state.admin_api_qps)],
        )
    return MetricSeries(
        service=SERVICE,
        metric="order_amount_error_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=state.order_amount_error_rate)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_streams(_state: State) -> list:
    return []


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")
