"""ecomm-manager: promotion-v2 feature flag causes NPE."""

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

SCENARIO_ID = "ecomm-manager-feature-flag"
SERVICE = "ecomm-manager"
FLAG_NAME = "promotion-v2"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    flag_enabled: bool = True
    error_rate: float = 0.18
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.flag_enabled = True
        self.error_rate = 0.18
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.error_rate < 0.02

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "toggle_feature_flag":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable; use toggle_feature_flag",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        flag = body.get("flag_name")
        enabled = body.get("enabled")
        if flag != FLAG_NAME:
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"Unknown flag_name {flag!r}; expected {FLAG_NAME}",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        self.flag_enabled = bool(enabled)
        if enabled is False:
            self.phase = Phase.RECOVERED
            self.error_rate = 0.01
            msg = f"Disabled {FLAG_NAME}; error rate dropping"
        else:
            self.phase = Phase.BROKEN
            self.error_rate = 0.18
            msg = f"Enabled {FLAG_NAME}; unstable code path active"

        result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {"flag_name": FLAG_NAME, "flag_enabled": self.flag_enabled, "error_rate": self.error_rate}


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
                message=f"feature flag {FLAG_NAME} disabled, error rate normalized",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="NullPointerException in PromotionService.applyDiscount",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message=f"feature flag {FLAG_NAME} enabled, code path unstable",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message="error rate spiked after flag promotion-v2 rollout",
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
        "Error rate normalized after feature flag disabled"
        if state.phase == Phase.RECOVERED
        else "Elevated error rate after feature rollout"
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
    return MetricSeries(
        service=SERVICE,
        metric="error_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=state.error_rate)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(
        service=SERVICE,
        action="toggle_feature_flag",
        message=f"Enabled feature flag {FLAG_NAME} in production",
    )


def project_streams(_state: State) -> list:
    return []
