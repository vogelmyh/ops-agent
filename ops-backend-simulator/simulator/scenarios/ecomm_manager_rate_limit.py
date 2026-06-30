"""ecomm-manager: rate-limit.max-qps misconfigured (50 vs 5000)."""

from __future__ import annotations

from dataclasses import dataclass, field

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

SCENARIO_ID = "ecomm-manager-rate-limit"
SERVICE = "ecomm-manager"
CONFIG_KEY = "rate-limit.max-qps"
BASELINE_QPS = 8000.0
BROKEN_QPS = 400.0
RECOVERED_QPS = 7800.0
RECOVERY_THRESHOLD = 3000.0
BROKEN_VALUE = "50"
BASELINE_VALUE = "5000"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    max_qps: str = BROKEN_VALUE
    admin_api_qps: float = BROKEN_QPS
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.max_qps = BROKEN_VALUE
        self.admin_api_qps = BROKEN_QPS
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.admin_api_qps >= RECOVERY_THRESHOLD

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "patch_config":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable for rate-limit scenario; use patch_config",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

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
            self.phase = Phase.RECOVERED
            self.admin_api_qps = RECOVERED_QPS
            msg = f"Patched {CONFIG_KEY}={value}; admin API QPS recovering"
        else:
            self.phase = Phase.BROKEN
            self.admin_api_qps = BROKEN_QPS
            msg = f"Patched {CONFIG_KEY}={value} but baseline is {BASELINE_VALUE}; rate limiting persists"

        result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "max_qps": self.max_qps,
            "admin_api_qps": int(self.admin_api_qps),
            "baseline_max_qps": BASELINE_VALUE,
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
    if state.phase == Phase.RECOVERED:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message="admin api qps recovered after rate limit config patch",
                service=SERVICE,
                metadata={"max_qps": state.max_qps, "qps": state.admin_api_qps},
            ),
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message=f"RateLimitFilter: max-qps={state.max_qps} active, within baseline",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message="rate limit exceeded for merchant-api",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message=f"admin api qps dropped from {int(BASELINE_QPS)} to {int(BROKEN_QPS)} after config reload",
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
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    msg = (
        "Admin API QPS recovered after rate limit config patch"
        if state.phase == Phase.RECOVERED
        else "Merchant admin API QPS below baseline; elevated latency on admin endpoints"
    )
    return ServiceStatus(
        service=SERVICE,
        healthy=True,
        replicas_ready=2,
        replicas_desired=2,
        pods=_pods(),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    if state.phase == Phase.RECOVERED:
        points = [MetricPoint(timestamp=NOW, value=state.admin_api_qps)]
    else:
        points = [
            MetricPoint(timestamp=NOW, value=BASELINE_QPS),
            MetricPoint(timestamp=NOW, value=BROKEN_QPS),
            MetricPoint(timestamp=NOW, value=state.admin_api_qps),
        ]
    return MetricSeries(service=SERVICE, metric="admin_api_qps", unit="req/s", points=points)


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
