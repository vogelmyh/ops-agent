"""ecomm-manager: layered faults — each correct write reveals the next ops-fixable layer; never RECOVERED."""

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

SCENARIO_ID = "ecomm-manager-cascade-exhaust"
SERVICE = "ecomm-manager"
CONFIG_KEY = "rate-limit.max-qps"
BASELINE_VALUE = "5000"
BROKEN_VALUE = "50"
BROKEN_QPS = 400.0
RECOVERED_QPS = 7800.0
FLAG_NAME = "promotion-v2"
LOG_PATH = "/var/log/ecomm-manager"


class FaultLayer(str, Enum):
    RATE_LIMIT = "RATE_LIMIT"
    FEATURE_FLAG = "FEATURE_FLAG"
    DISK_FULL = "DISK_FULL"
    CONN_LEAK = "CONN_LEAK"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    fault_layer: FaultLayer = FaultLayer.RATE_LIMIT
    max_qps: str = BROKEN_VALUE
    admin_api_qps: float = BROKEN_QPS
    flag_enabled: bool = True
    error_rate: float = 0.01
    disk_usage_percent: float = 45.0
    restart_count: int = 0
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.fault_layer = FaultLayer.RATE_LIMIT
        self.max_qps = BROKEN_VALUE
        self.admin_api_qps = BROKEN_QPS
        self.flag_enabled = True
        self.error_rate = 0.01
        self.disk_usage_percent = 45.0
        self.restart_count = 0
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return False

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1

        if self.fault_layer == FaultLayer.RATE_LIMIT and action == "patch_config":
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
            self.admin_api_qps = RECOVERED_QPS
            self.fault_layer = FaultLayer.FEATURE_FLAG
            self.flag_enabled = True
            self.error_rate = 0.18
            msg = f"Patched {CONFIG_KEY}={value}; rate limit cleared, elevated error rate persists"
            result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
            self.last_operation = result
            return result

        if self.fault_layer == FaultLayer.FEATURE_FLAG and action == "toggle_feature_flag":
            flag = body.get("flag_name")
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
            self.flag_enabled = bool(body.get("enabled"))
            self.error_rate = 0.02
            self.fault_layer = FaultLayer.DISK_FULL
            self.disk_usage_percent = 99.0
            msg = (
                f"Updated {FLAG_NAME} enabled={self.flag_enabled}; "
                "error rate improved but disk pressure emerged"
            )
            result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
            self.last_operation = result
            return result

        if self.fault_layer == FaultLayer.DISK_FULL and action == "drain_node":
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
            self.disk_usage_percent = 45.0
            self.fault_layer = FaultLayer.CONN_LEAK
            days = body.get("retention_days", 7)
            msg = f"Cleaned {path} older than {days}d; HTTP connection leak symptoms remain"
            result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
            self.last_operation = result
            return result

        if self.fault_layer == FaultLayer.CONN_LEAK and action == "restart_deployment":
            self.restart_count += 1
            msg = "Rolling restart completed; connection leak metrics remain elevated"
            result = op_result(service=SERVICE, action=action, message=msg, op_id=f"op-{self.op_counter}")
            self.last_operation = result
            return result

        result = op_result(
            service=SERVICE,
            action=action,
            message=f"{action} not applicable for cascade layer {self.fault_layer.value}",
            status=OperationStatus.FAILED,
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "cascade_type": "layered-exhaust",
            "fault_layer": self.fault_layer.value,
            "max_qps": self.max_qps,
            "admin_api_qps": int(self.admin_api_qps),
            "flag_name": FLAG_NAME,
            "flag_enabled": self.flag_enabled,
            "error_rate": self.error_rate,
            "disk_usage_percent": self.disk_usage_percent,
            "restart_count": self.restart_count,
            "phase": self.phase.value,
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
    layer = state.fault_layer
    if layer == FaultLayer.RATE_LIMIT:
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
    elif layer == FaultLayer.FEATURE_FLAG:
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
        ]
    elif layer == FaultLayer.DISK_FULL:
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
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="ERROR",
                message="too many open files",
                service=SERVICE,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message="Connection leak detection: HTTP clients not released",
                service=SERVICE,
            ),
        ]

    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    layer = state.fault_layer
    messages = {
        FaultLayer.RATE_LIMIT: "Merchant admin API QPS below baseline; elevated latency on admin endpoints",
        FaultLayer.FEATURE_FLAG: "Elevated error rate after feature rollout",
        FaultLayer.DISK_FULL: "Disk pressure on audit log volume",
        FaultLayer.CONN_LEAK: "HTTP connection leak degrading admin API latency",
    }
    healthy = layer not in (FaultLayer.DISK_FULL, FaultLayer.CONN_LEAK)
    return ServiceStatus(
        service=SERVICE,
        healthy=healthy,
        replicas_ready=2,
        replicas_desired=2,
        pods=_pods(),
        message=messages[layer],
    )


def project_metrics(state: State) -> MetricSeries:
    layer = state.fault_layer
    if layer == FaultLayer.RATE_LIMIT:
        return MetricSeries(
            service=SERVICE,
            metric="admin_api_qps",
            unit="req/s",
            points=[
                MetricPoint(timestamp=NOW, value=RECOVERED_QPS),
                MetricPoint(timestamp=NOW, value=BROKEN_QPS),
                MetricPoint(timestamp=NOW, value=state.admin_api_qps),
            ],
        )
    if layer == FaultLayer.FEATURE_FLAG:
        return MetricSeries(
            service=SERVICE,
            metric="error_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=state.error_rate)],
        )
    if layer == FaultLayer.DISK_FULL:
        return MetricSeries(
            service=SERVICE,
            metric="disk_usage_percent",
            unit="percent",
            points=[MetricPoint(timestamp=NOW, value=state.disk_usage_percent)],
        )
    return MetricSeries(
        service=SERVICE,
        metric="open_connections",
        unit="count",
        points=[MetricPoint(timestamp=NOW, value=9800.0)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(service=SERVICE, action="none", message="No recent operation")


def project_streams(_state: State) -> list:
    return []
