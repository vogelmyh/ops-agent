"""ecomm-manager: audit logs fill disk."""

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

SCENARIO_ID = "ecomm-manager-disk-full"
SERVICE = "ecomm-manager"
LOG_PATH = "/var/log/ecomm-manager"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    disk_usage_percent: float = 99.0
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.disk_usage_percent = 99.0
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return self.phase == Phase.RECOVERED and self.disk_usage_percent < 60

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "cleanup_storage":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable; use cleanup_storage",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        path = body.get("path") or LOG_PATH
        if path != LOG_PATH:
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"Unexpected path {path!r}; expected {LOG_PATH}",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        self.phase = Phase.RECOVERED
        self.disk_usage_percent = 45.0
        days = body.get("retention_days", 7)
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"Cleaned {path} older than {days}d; disk usage dropped to 45%",
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {"disk_usage_percent": self.disk_usage_percent, "path": LOG_PATH}


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
                message="disk cleanup completed, audit log writes resumed",
                service=SERVICE,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="failed to write audit log: no space left on device",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message=f"disk usage {int(state.disk_usage_percent)}% on {LOG_PATH}",
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
        "Disk pressure relieved after log cleanup"
        if state.phase == Phase.RECOVERED
        else "Disk pressure on audit log volume"
    )
    return ServiceStatus(
        service=SERVICE,
        healthy=state.phase == Phase.RECOVERED,
        replicas_ready=2,
        replicas_desired=2,
        pods=_pods(),
        message=msg,
    )


def project_metrics(state: State) -> MetricSeries:
    return MetricSeries(
        service=SERVICE,
        metric="disk_usage_percent",
        unit="percent",
        points=[MetricPoint(timestamp=NOW, value=state.disk_usage_percent)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
