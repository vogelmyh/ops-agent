"""Mock backend telemetry keyed by service + scenario (e-commerce SaaS)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.adapters.mock_remediation import is_remediated
from app.schemas import (
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
    StreamState,
    StreamStatus,
)

NOW = datetime.now(timezone.utc)

KNOWN_SERVICES = ("ecomm-manager", "ecomm-order")

DEFAULT_SCENARIOS: dict[str, str] = {
    "ecomm-manager": "rate-limit",
    "ecomm-order": "crashloop",
}

_active_scenarios: dict[str, str] = dict(DEFAULT_SCENARIOS)


def get_mock_scenario(service: str) -> str:
    return _active_scenarios.get(service, DEFAULT_SCENARIOS.get(service, "default"))


def set_mock_scenario(service: str, scenario: str) -> None:
    _active_scenarios[service] = scenario


def reset_mock_scenarios() -> None:
    _active_scenarios.clear()
    _active_scenarios.update(DEFAULT_SCENARIOS)


def _filter_logs(entries: list[LogEntry], req: LogQueryRequest) -> LogQueryResult:
    filtered = [
        e for e in entries
        if not req.keyword or req.keyword.lower() in e.message.lower()
    ]
    return LogQueryResult(query=req, total=len(filtered), entries=filtered[: req.limit])


# ---------------------------------------------------------------------------
# ecomm-manager scenarios
# ---------------------------------------------------------------------------

def _manager_rate_limit_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-manager"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="admin api qps recovered after rate limit config patch",
                service="ecomm-manager",
                metadata={"qps": 7800},
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=5),
            level="WARN",
            message="rate limit exceeded for merchant-api",
            service="ecomm-manager",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=4),
            level="INFO",
            message="admin api qps dropped from 8000 to 400 after config reload",
            service="ecomm-manager",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=3),
            level="ERROR",
            message="RateLimitFilter: threshold misconfigured max-qps=50 expected=5000",
            service="ecomm-manager",
        ),
    ]
    return _filter_logs(entries, req)


def _manager_feature_flag_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-manager"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="feature flag promotion-v2 disabled, error rate normalized",
                service="ecomm-manager",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=3),
            level="ERROR",
            message="NullPointerException in PromotionService.applyDiscount",
            service="ecomm-manager",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=2),
            level="WARN",
            message="feature flag promotion-v2 enabled, code path unstable",
            service="ecomm-manager",
        ),
    ]
    return _filter_logs(entries, req)


def _manager_crashloop_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-manager"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="Application started successfully after rollback",
                service="ecomm-manager",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=9),
            level="FATAL",
            message="Application startup failed: health check server failed to start",
            service="ecomm-manager",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=8),
            level="ERROR",
            message="Health check server failed to start on :8080: connection refused",
            service="ecomm-manager",
        ),
    ]
    return _filter_logs(entries, req)


def _manager_discount_bug_logs(req: LogQueryRequest) -> LogQueryResult:
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=3),
            level="ERROR",
            message="ArithmeticException: discount overflow in DiscountEngine",
            service="ecomm-manager",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=2),
            level="ERROR",
            message="order amount mismatch: expected=99.00 actual=0.01",
            service="ecomm-manager",
        ),
    ]
    return _filter_logs(entries, req)


def _manager_disk_full_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-manager"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="disk cleanup completed, audit log writes resumed",
                service="ecomm-manager",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=3),
            level="ERROR",
            message="failed to write audit log: no space left on device",
            service="ecomm-manager",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=2),
            level="WARN",
            message="disk usage 99% on /var/log/ecomm-manager",
            service="ecomm-manager",
        ),
    ]
    return _filter_logs(entries, req)


def _manager_pods(running: bool = True, image: str = "registry/ecomm-manager:2.0.8") -> list[PodStatus]:
    if running:
        return [
            PodStatus(
                name=f"ecomm-manager-{i}",
                ready=True,
                restarts=0,
                phase="Running",
                image=image,
            )
            for i in range(2)
        ]
    return [
        PodStatus(
            name=f"ecomm-manager-{i}",
            ready=False,
            restarts=14 + i,
            phase="CrashLoopBackOff",
            image=image,
            reason="CrashLoopBackOff",
        )
        for i in range(2)
    ]


def _manager_status(scenario: str) -> ServiceStatus:
    if scenario == "rate-limit":
        msg = (
            "Admin API QPS recovered after rate limit config patch"
            if is_remediated("ecomm-manager")
            else "Service up but admin API QPS degraded due to rate limit misconfiguration"
        )
        return ServiceStatus(
            service="ecomm-manager",
            healthy=True,
            replicas_ready=2,
            replicas_desired=2,
            pods=_manager_pods(),
            message=msg,
        )
    if scenario == "feature-flag":
        return ServiceStatus(
            service="ecomm-manager",
            healthy=True,
            replicas_ready=2,
            replicas_desired=2,
            pods=_manager_pods(),
            message=(
                "Error rate normalized after feature flag disabled"
                if is_remediated("ecomm-manager")
                else "Elevated error rate after feature rollout"
            ),
        )
    if scenario == "crashloop":
        recovered = is_remediated("ecomm-manager")
        return ServiceStatus(
            service="ecomm-manager",
            healthy=recovered,
            replicas_ready=2 if recovered else 0,
            replicas_desired=2,
            pods=_manager_pods(
                running=recovered,
                image="registry/ecomm-manager:2.0.8-stable" if recovered else "registry/ecomm-manager:2.1.0-bad",
            ),
            message=(
                "All replicas ready after rollback to stable image"
                if recovered
                else "All replicas failing after bad image upgrade"
            ),
        )
    if scenario == "discount-bug":
        return ServiceStatus(
            service="ecomm-manager",
            healthy=True,
            replicas_ready=2,
            replicas_desired=2,
            pods=_manager_pods(),
            message="Pods healthy but order amount calculation incorrect",
        )
    if scenario == "disk-full":
        recovered = is_remediated("ecomm-manager")
        return ServiceStatus(
            service="ecomm-manager",
            healthy=recovered,
            replicas_ready=2,
            replicas_desired=2,
            pods=_manager_pods(),
            message=(
                "Disk pressure relieved after log cleanup"
                if recovered
                else "Disk pressure on audit log volume"
            ),
        )
    raise ValueError(f"unknown ecomm-manager scenario: {scenario}")


def _manager_metrics(scenario: str) -> MetricSeries:
    if scenario == "rate-limit":
        if is_remediated("ecomm-manager"):
            return MetricSeries(
                service="ecomm-manager",
                metric="admin_api_qps",
                unit="req/s",
                points=[
                    MetricPoint(timestamp=NOW - timedelta(minutes=5), value=400),
                    MetricPoint(timestamp=NOW, value=7800),
                ],
            )
        return MetricSeries(
            service="ecomm-manager",
            metric="admin_api_qps",
            unit="req/s",
            points=[
                MetricPoint(timestamp=NOW - timedelta(minutes=10), value=8000),
                MetricPoint(timestamp=NOW - timedelta(minutes=5), value=400),
                MetricPoint(timestamp=NOW, value=380),
            ],
        )
    if scenario == "feature-flag":
        return MetricSeries(
            service="ecomm-manager",
            metric="error_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=0.01 if is_remediated("ecomm-manager") else 0.18)],
        )
    if scenario == "crashloop":
        ready = 2 if is_remediated("ecomm-manager") else 0
        return MetricSeries(
            service="ecomm-manager",
            metric="ready_replicas",
            unit="count",
            points=[MetricPoint(timestamp=NOW, value=float(ready))],
        )
    if scenario == "discount-bug":
        return MetricSeries(
            service="ecomm-manager",
            metric="order_amount_error_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=0.12)],
        )
    if scenario == "disk-full":
        return MetricSeries(
            service="ecomm-manager",
            metric="disk_usage_percent",
            unit="percent",
            points=[MetricPoint(timestamp=NOW, value=45.0 if is_remediated("ecomm-manager") else 99.0)],
        )
    raise ValueError(f"unknown ecomm-manager scenario: {scenario}")


def _manager_k8s_events(scenario: str) -> K8sEventResult:
    if scenario != "crashloop" or is_remediated("ecomm-manager"):
        return K8sEventResult(service="ecomm-manager", total=0, events=[])
    events = [
        K8sEvent(
            timestamp=NOW - timedelta(minutes=8),
            type="Warning",
            reason="BackOff",
            involved_object="pod/ecomm-manager-0",
            message="Back-off restarting failed container ecomm-manager in pod ecomm-manager-0",
            service="ecomm-manager",
        ),
        K8sEvent(
            timestamp=NOW - timedelta(minutes=6),
            type="Warning",
            reason="Unhealthy",
            involved_object="pod/ecomm-manager-1",
            message="Readiness probe failed: connection refused :8080",
            service="ecomm-manager",
        ),
    ]
    return K8sEventResult(service="ecomm-manager", total=len(events), events=events)


# ---------------------------------------------------------------------------
# ecomm-order scenarios
# ---------------------------------------------------------------------------

def _order_crashloop_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-order"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="Application started successfully after rollback",
                service="ecomm-order",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=9),
            level="FATAL",
            message="Application startup failed",
            service="ecomm-order",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=8),
            level="ERROR",
            message="Health check server failed to start on :8080: connection refused",
            service="ecomm-order",
        ),
    ]
    return _filter_logs(entries, req)


def _order_stream_paused_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-order"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="stream order-events resumed; ingest heartbeat restored",
                service="ecomm-order",
                stream="order-events",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(hours=1),
            level="INFO",
            message="stream order-events paused by operator",
            service="ecomm-order",
            stream="order-events",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=20),
            level="WARN",
            message="no ingest heartbeat for stream order-events",
            service="ecomm-order",
        ),
    ]
    return _filter_logs(entries, req)


def _order_memory_leak_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-order"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="order processing resumed after rolling pod restart",
                service="ecomm-order",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=5),
            level="ERROR",
            message="java.lang.OutOfMemoryError: Java heap space",
            service="ecomm-order",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=4),
            level="ERROR",
            message="connection pool exhausted, cannot acquire connection",
            service="ecomm-order",
        ),
    ]
    return _filter_logs(entries, req)


def _order_payment_circuit_logs(req: LogQueryRequest) -> LogQueryResult:
    if is_remediated("ecomm-order"):
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="circuit breaker OPEN for payment-gw",
                service="ecomm-order",
            ),
        ]
        return LogQueryResult(query=req, total=len(entries), entries=entries[: req.limit])
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=3),
            level="ERROR",
            message="payment gateway timeout: upstream payment-gw unreachable",
            service="ecomm-order",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=2),
            level="ERROR",
            message="PaymentClient: 503 from payment-gw, circuit not open",
            service="ecomm-order",
        ),
    ]
    return _filter_logs(entries, req)


def _order_rds_timeout_logs(req: LogQueryRequest) -> LogQueryResult:
    entries = [
        LogEntry(
            timestamp=NOW - timedelta(minutes=3),
            level="ERROR",
            message="SQLException: Connection timed out waiting for RDS",
            service="ecomm-order",
        ),
        LogEntry(
            timestamp=NOW - timedelta(minutes=2),
            level="ERROR",
            message="HikariPool: Connection is not available, request timed out",
            service="ecomm-order",
        ),
    ]
    return _filter_logs(entries, req)


def _order_pods(
    *,
    running: bool = True,
    image: str = "registry/ecomm-order:3.2.1",
    restarts: int = 0,
) -> list[PodStatus]:
    if running:
        return [
            PodStatus(
                name=f"ecomm-order-{i}",
                ready=True,
                restarts=restarts + i,
                phase="Running",
                image=image,
            )
            for i in range(3)
        ]
    return [
        PodStatus(
            name=f"ecomm-order-{i}",
            ready=False,
            restarts=12 + i,
            phase="CrashLoopBackOff",
            image=image,
            reason="CrashLoopBackOff",
        )
        for i in range(3)
    ]


def _order_status(scenario: str) -> ServiceStatus:
    if scenario == "crashloop":
        recovered = is_remediated("ecomm-order")
        return ServiceStatus(
            service="ecomm-order",
            healthy=recovered,
            replicas_ready=3 if recovered else 0,
            replicas_desired=3,
            pods=_order_pods(
                running=recovered,
                image="registry/ecomm-order:3.2.1-stable" if recovered else "registry/ecomm-order:3.3.0-bad",
            ),
            message=(
                "All replicas ready after rollback to stable image"
                if recovered
                else "All replicas failing after bad image upgrade"
            ),
        )
    if scenario == "stream-paused":
        return ServiceStatus(
            service="ecomm-order",
            healthy=True,
            replicas_ready=3,
            replicas_desired=3,
            pods=_order_pods(),
            message=(
                "Order event stream running, ingest restored"
                if is_remediated("ecomm-order")
                else "Order event stream paused; inventory sync stalled"
            ),
        )
    if scenario == "memory-leak":
        recovered = is_remediated("ecomm-order")
        return ServiceStatus(
            service="ecomm-order",
            healthy=recovered,
            replicas_ready=3,
            replicas_desired=3,
            pods=_order_pods(restarts=0 if recovered else 8),
            message=(
                "Order success rate recovered after pod restart"
                if recovered
                else "OOM and connection pool exhaustion on stable image"
            ),
        )
    if scenario == "payment-circuit":
        return ServiceStatus(
            service="ecomm-order",
            healthy=True,
            replicas_ready=3,
            replicas_desired=3,
            pods=_order_pods(),
            message=(
                "Circuit breaker open on payment-gw, payment storm contained"
                if is_remediated("ecomm-order")
                else "Payment errors due to payment-gw upstream timeout"
            ),
        )
    if scenario == "rds-timeout":
        return ServiceStatus(
            service="ecomm-order",
            healthy=True,
            replicas_ready=3,
            replicas_desired=3,
            pods=_order_pods(),
            message="Pods healthy but order persist failing due to RDS timeout",
        )
    raise ValueError(f"unknown ecomm-order scenario: {scenario}")


def _order_metrics(scenario: str) -> MetricSeries:
    if scenario == "crashloop":
        ready = 3 if is_remediated("ecomm-order") else 0
        return MetricSeries(
            service="ecomm-order",
            metric="ready_replicas",
            unit="count",
            points=[MetricPoint(timestamp=NOW, value=float(ready))],
        )
    if scenario == "stream-paused":
        val = 2_000_000.0 if is_remediated("ecomm-order") else 0.0
        return MetricSeries(
            service="ecomm-order",
            metric="ingest_bytes_per_sec",
            unit="bytes/s",
            points=[MetricPoint(timestamp=NOW, value=val)],
        )
    if scenario == "memory-leak":
        return MetricSeries(
            service="ecomm-order",
            metric="order_success_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=0.995 if is_remediated("ecomm-order") else 0.82)],
        )
    if scenario == "payment-circuit":
        return MetricSeries(
            service="ecomm-order",
            metric="payment_error_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=0.15 if is_remediated("ecomm-order") else 0.82)],
        )
    if scenario == "rds-timeout":
        return MetricSeries(
            service="ecomm-order",
            metric="order_success_rate",
            unit="ratio",
            points=[MetricPoint(timestamp=NOW, value=0.45)],
        )
    raise ValueError(f"unknown ecomm-order scenario: {scenario}")


def _order_k8s_events(scenario: str) -> K8sEventResult:
    if scenario == "crashloop" and not is_remediated("ecomm-order"):
        events = [
            K8sEvent(
                timestamp=NOW - timedelta(minutes=8),
                type="Warning",
                reason="BackOff",
                involved_object="pod/ecomm-order-0",
                message="Back-off restarting failed container ecomm-order",
                service="ecomm-order",
            ),
            K8sEvent(
                timestamp=NOW - timedelta(minutes=6),
                type="Warning",
                reason="Unhealthy",
                involved_object="pod/ecomm-order-1",
                message="Readiness probe failed: connection refused :8080",
                service="ecomm-order",
            ),
        ]
        return K8sEventResult(service="ecomm-order", total=len(events), events=events)
    if scenario == "memory-leak" and not is_remediated("ecomm-order"):
        events = [
            K8sEvent(
                timestamp=NOW - timedelta(minutes=5),
                type="Warning",
                reason="OOMKilled",
                involved_object="pod/ecomm-order-0",
                message="Container ecomm-order was OOMKilled",
                service="ecomm-order",
            ),
        ]
        return K8sEventResult(service="ecomm-order", total=len(events), events=events)
    return K8sEventResult(service="ecomm-order", total=0, events=[])


def _order_streams(scenario: str) -> list[StreamState]:
    if scenario != "stream-paused":
        return []
    if is_remediated("ecomm-order"):
        return [
            StreamState(
                project="ecomm",
                stream="order-events",
                status=StreamStatus.RUNNING,
                topic="kafka-order-events",
                last_ingest_at=NOW - timedelta(seconds=20),
            ),
        ]
    return [
        StreamState(
            project="ecomm",
            stream="order-events",
            status=StreamStatus.PAUSED,
            topic="kafka-order-events",
            last_ingest_at=NOW - timedelta(hours=6),
        ),
    ]


_MANAGER_LOGS = {
    "rate-limit": _manager_rate_limit_logs,
    "feature-flag": _manager_feature_flag_logs,
    "crashloop": _manager_crashloop_logs,
    "discount-bug": _manager_discount_bug_logs,
    "disk-full": _manager_disk_full_logs,
}

_ORDER_LOGS = {
    "crashloop": _order_crashloop_logs,
    "stream-paused": _order_stream_paused_logs,
    "memory-leak": _order_memory_leak_logs,
    "payment-circuit": _order_payment_circuit_logs,
    "rds-timeout": _order_rds_timeout_logs,
}


def _latest_operation(service: str) -> OperationResult:
    scenario = get_mock_scenario(service)
    if service == "ecomm-manager" and scenario == "feature-flag":
        return OperationResult(
            operation_id="op-flag-991",
            service=service,
            action="toggle_feature_flag",
            status=OperationStatus.SUCCEEDED,
            message="Enabled feature flag promotion-v2 in production",
            started_at=NOW - timedelta(minutes=30),
            finished_at=NOW - timedelta(minutes=29),
        )
    if service == "ecomm-manager" and scenario == "crashloop":
        return OperationResult(
            operation_id="op-7788",
            service=service,
            action="deploy",
            status=OperationStatus.SUCCEEDED,
            message="Deployed registry/ecomm-manager:2.1.0-bad (bad release)",
            started_at=NOW - timedelta(minutes=10),
            finished_at=NOW - timedelta(minutes=9),
        )
    if service == "ecomm-order" and scenario == "crashloop":
        return OperationResult(
            operation_id="op-8899",
            service=service,
            action="deploy",
            status=OperationStatus.SUCCEEDED,
            message="Deployed registry/ecomm-order:3.3.0-bad (bad release)",
            started_at=NOW - timedelta(minutes=10),
            finished_at=NOW - timedelta(minutes=9),
        )
    if service == "ecomm-order" and scenario == "stream-paused":
        return OperationResult(
            operation_id="op-pause-12",
            service=service,
            action="pause_stream",
            status=OperationStatus.SUCCEEDED,
            message="Stream order-events paused by operator",
            started_at=NOW - timedelta(hours=1),
            finished_at=NOW - timedelta(hours=1),
        )
    return OperationResult(
        operation_id="op-none",
        service=service,
        action="none",
        status=OperationStatus.SUCCEEDED,
        message="No recent operation",
        started_at=NOW - timedelta(days=1),
        finished_at=NOW - timedelta(days=1),
    )


def _ecomm_cache_logs(req: LogQueryRequest) -> LogQueryResult:
    recovered = is_remediated("ecomm-cache")
    if recovered:
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=1),
                level="INFO",
                message="redis cache connections stable after rolling restart",
                service="ecomm-cache",
            ),
        ]
    else:
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=5),
                level="ERROR",
                message="redis connection pool exhausted: OOMKilled peer ecomm-cache-1",
                service="ecomm-cache",
            ),
            LogEntry(
                timestamp=NOW - timedelta(minutes=3),
                level="WARN",
                message="cache read latency p99 exceeded 800ms",
                service="ecomm-cache",
            ),
        ]
    return _filter_logs(entries, req)


def _ecomm_cache_k8s_events() -> K8sEventResult:
    if is_remediated("ecomm-cache"):
        return K8sEventResult(service="ecomm-cache", total=0, events=[])
    events = [
        K8sEvent(
            timestamp=NOW - timedelta(minutes=5),
            type="Warning",
            reason="OOMKilled",
            involved_object="pod/ecomm-cache-1",
            message="Container ecomm-cache was OOMKilled",
            service="ecomm-cache",
        ),
    ]
    return K8sEventResult(service="ecomm-cache", total=len(events), events=events)


def _ecomm_cache_status() -> ServiceStatus:
    recovered = is_remediated("ecomm-cache")
    return ServiceStatus(
        service="ecomm-cache",
        healthy=recovered,
        replicas_ready=2 if recovered else 1,
        replicas_desired=2,
        pods=[
            PodStatus(
                name="ecomm-cache-0",
                ready=True,
                restarts=1 if recovered else 2,
                phase="Running",
                image="registry/ecomm-cache:1.2.0",
            ),
            PodStatus(
                name="ecomm-cache-1",
                ready=recovered,
                restarts=0 if recovered else 6,
                phase="Running",
                image="registry/ecomm-cache:1.2.0",
                reason=None if recovered else "OOMKilled",
            ),
        ],
        message="ecomm-cache recovered" if recovered else "ecomm-cache OOMKilled; 1/2 replicas ready",
    )


def _ecomm_cache_metrics() -> MetricSeries:
    recovered = is_remediated("ecomm-cache")
    return MetricSeries(
        service="ecomm-cache",
        metric="error_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=0.02 if recovered else 0.28)],
    )


def _novel_service_logs(service: str):
    def handler(req: LogQueryRequest) -> LogQueryResult:
        entries = [
            LogEntry(
                timestamp=NOW - timedelta(minutes=5),
                level="ERROR",
                message=f"degraded request latency spike in {service}",
                service=service,
            ),
            LogEntry(
                timestamp=NOW - timedelta(minutes=3),
                level="WARN",
                message=f"catalog index rebuild stalled for {service}",
                service=service,
            ),
        ]
        return _filter_logs(entries, req)

    return handler


def _novel_service_status(service: str) -> ServiceStatus:
    return ServiceStatus(
        service=service,
        healthy=False,
        replicas_ready=1,
        replicas_desired=2,
        pods=[
            PodStatus(
                name=f"{service}-0",
                ready=True,
                restarts=2,
                phase="Running",
                image=f"registry/{service}:1.0.0",
            ),
            PodStatus(
                name=f"{service}-1",
                ready=False,
                restarts=5,
                phase="Running",
                image=f"registry/{service}:1.0.0",
                reason="Unhealthy",
            ),
        ],
        message=f"Service {service} degraded; symptoms do not match known runbooks",
    )


def _novel_service_metrics(service: str) -> MetricSeries:
    return MetricSeries(
        service=service,
        metric="error_rate",
        unit="ratio",
        points=[MetricPoint(timestamp=NOW, value=0.22)],
    )


def _handler_for(service: str) -> dict:
    scenario = get_mock_scenario(service)
    if service == "ecomm-manager":
        if scenario not in _MANAGER_LOGS:
            raise ValueError(f"unknown ecomm-manager scenario: {scenario}")
        return {
            "app_logs": _MANAGER_LOGS[scenario],
            "k8s_events": lambda: _manager_k8s_events(scenario),
            "status": lambda: _manager_status(scenario),
            "metrics": lambda: _manager_metrics(scenario),
            "streams": lambda: [],
        }
    if service == "ecomm-order":
        if scenario not in _ORDER_LOGS:
            raise ValueError(f"unknown ecomm-order scenario: {scenario}")
        return {
            "app_logs": _ORDER_LOGS[scenario],
            "k8s_events": lambda: _order_k8s_events(scenario),
            "status": lambda: _order_status(scenario),
            "metrics": lambda: _order_metrics(scenario),
            "streams": lambda: _order_streams(scenario),
        }
    if service == "ecomm-cache":
        return {
            "app_logs": _ecomm_cache_logs,
            "k8s_events": _ecomm_cache_k8s_events,
            "status": _ecomm_cache_status,
            "metrics": _ecomm_cache_metrics,
            "streams": lambda: [],
        }
    if service not in KNOWN_SERVICES:
        return {
            "app_logs": _novel_service_logs(service),
            "k8s_events": lambda: K8sEventResult(service=service, total=0, events=[]),
            "status": lambda: _novel_service_status(service),
            "metrics": lambda: _novel_service_metrics(service),
            "streams": lambda: [],
        }
    raise ValueError(f"unknown service: {service}")


def get_mock_handler(service: str) -> dict:
    return _handler_for(service)
