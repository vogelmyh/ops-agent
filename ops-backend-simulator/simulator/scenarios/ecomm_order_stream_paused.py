"""ecomm-order: order-events stream paused."""

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
    StreamState,
    StreamStatus,
)
from simulator.scenarios.common import NOW, Phase, op_result

SCENARIO_ID = "ecomm-order-stream-paused"
SERVICE = "ecomm-order"
STREAM_ID = "order-events"


@dataclass
class State:
    phase: Phase = Phase.BROKEN
    stream_status: StreamStatus = StreamStatus.PAUSED
    ingest_bytes_per_sec: float = 0.0
    last_operation: OperationResult | None = None
    op_counter: int = 0

    def reset(self) -> None:
        self.phase = Phase.BROKEN
        self.stream_status = StreamStatus.PAUSED
        self.ingest_bytes_per_sec = 0.0
        self.last_operation = None
        self.op_counter = 0

    @property
    def is_recovered(self) -> bool:
        return (
            self.phase == Phase.RECOVERED
            and self.stream_status == StreamStatus.RUNNING
            and self.ingest_bytes_per_sec > 100_000
        )

    def apply_ops(self, action: str, body: dict) -> OperationResult:
        self.op_counter += 1
        if action != "restart_deployment":
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"{action} not applicable; use restart_deployment",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        strategy = body.get("strategy") or "rolling"
        if strategy not in ("rolling", "all"):
            result = op_result(
                service=SERVICE,
                action=action,
                message=f"Unknown strategy {strategy!r}; expected rolling or all",
                status=OperationStatus.FAILED,
                op_id=f"op-{self.op_counter}",
            )
            self.last_operation = result
            return result

        self.phase = Phase.RECOVERED
        self.stream_status = StreamStatus.RUNNING
        self.ingest_bytes_per_sec = 2_000_000.0
        result = op_result(
            service=SERVICE,
            action=action,
            message=f"Restarted deployment {SERVICE} with {strategy} strategy; stream {STREAM_ID} resumed, consumer lag draining",
            op_id=f"op-{self.op_counter}",
        )
        self.last_operation = result
        return result

    def admin_dict(self) -> dict:
        return {
            "stream_id": STREAM_ID,
            "stream_status": self.stream_status.value,
            "ingest_bytes_per_sec": int(self.ingest_bytes_per_sec),
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
                message=f"stream {STREAM_ID} resumed, ingest heartbeat restored",
                service=SERVICE,
                stream=STREAM_ID,
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW,
                level="INFO",
                message=f"stream {STREAM_ID} paused by operator",
                service=SERVICE,
                stream=STREAM_ID,
            ),
            LogEntry(
                timestamp=NOW,
                level="WARN",
                message=f"no ingest heartbeat for stream {STREAM_ID}",
                service=SERVICE,
                stream=STREAM_ID,
            ),
        ]
    if req.keyword:
        kw = req.keyword.lower()
        entries = [e for e in entries if kw in e.message.lower()]
    limit = min(req.limit, len(entries))
    return LogQueryResult(query=req, total=len(entries), entries=entries[:limit])


def project_status(state: State) -> ServiceStatus:
    msg = (
        "Order event stream running, ingest restored"
        if state.phase == Phase.RECOVERED
        else "Order event stream paused; inventory sync stalled"
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
        metric="ingest_bytes_per_sec",
        unit="bytes/s",
        points=[MetricPoint(timestamp=NOW, value=state.ingest_bytes_per_sec)],
    )


def project_k8s_events(_state: State) -> K8sEventResult:
    return K8sEventResult(service=SERVICE, total=0, events=[])


def project_latest_operation(state: State) -> OperationResult:
    if state.last_operation:
        return state.last_operation
    return op_result(
        service=SERVICE,
        action="pause_stream",
        message=f"Stream {STREAM_ID} paused by operator",
    )


def project_streams(state: State) -> list:
    return [
        StreamState(
            project="ecomm",
            stream=STREAM_ID,
            status=state.stream_status,
            topic=f"kafka-{STREAM_ID}",
            last_ingest_at=NOW if state.stream_status == StreamStatus.RUNNING else None,
        )
    ]
