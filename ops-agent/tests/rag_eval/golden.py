"""RAG golden-set cases for offline retrieval evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ChallengeType = Literal[
    "easy_match",
    "same_service_disambiguation",
    "cross_service_trap",
    "lexical_trap",
    "negative_constraint",
    "novel",
]

Difficulty = Literal["easy", "medium", "hard"]


@dataclass
class GoldenCase:
    id: str
    service: str
    incident_description: str
    expected_doc_id: str | None
    challenge_type: ChallengeType
    difficulty: Difficulty
    must_not_select: list[str] = field(default_factory=list)
    expected_runbook_available: bool = True
    telemetry: dict[str, Any] = field(default_factory=dict)


def _status(
    *,
    ready: int = 3,
    desired: int = 3,
    healthy: bool = True,
    message: str = "",
    pods: list[dict] | None = None,
) -> dict:
    return {
        "replicas_ready": ready,
        "replicas_desired": desired,
        "healthy": healthy,
        "message": message,
        "pods": pods or [],
    }


def _log(level: str, message: str) -> dict:
    return {"app_logs": {"entries": [{"level": level, "message": message}]}}


def _k8s(reason: str, message: str) -> dict:
    return {"k8s_events": {"events": [{"reason": reason, "message": message}]}}


def _metrics(name: str, first: float, last: float) -> dict:
    return {"metrics": {"metric": name, "points": [{"value": first}, {"value": last}]}}


GOLDEN_CASES: list[GoldenCase] = [
    # --- easy_match (production runbooks) ---
    GoldenCase(
        id="easy-rate-limit-01",
        service="ecomm-manager",
        incident_description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%",
        expected_doc_id="ecomm-manager-rate-limit",
        challenge_type="easy_match",
        difficulty="easy",
        telemetry={
            **_log("WARN", "rate limit exceeded for merchant-api"),
            **_status(message="admin api degraded rate limit"),
            **_metrics("admin_api_qps", 8000, 400),
        },
    ),
    GoldenCase(
        id="easy-crashloop-order-01",
        service="ecomm-order",
        incident_description="【P0】ecomm-order 下单服务 CrashLoopBackOff 坏镜像升级",
        expected_doc_id="ecomm-order-crashloop",
        challenge_type="easy_match",
        difficulty="easy",
        must_not_select=["ecomm-order-memory-leak"],
        telemetry={
            **_k8s("BackOff", "back-off restarting failed container"),
            **_status(
                ready=0,
                desired=3,
                healthy=False,
                pods=[{"name": "order-1", "restarts": 5, "reason": "CrashLoopBackOff", "image": "ecomm-order:3.3.0-bad"}],
            ),
            **_log("ERROR", "Application startup failed"),
        },
    ),
    GoldenCase(
        id="easy-memory-leak-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order OOMKilled 连接池耗尽 镜像版本未变",
        expected_doc_id="ecomm-order-memory-leak",
        challenge_type="easy_match",
        difficulty="easy",
        must_not_select=["ecomm-order-crashloop"],
        telemetry={
            **_k8s("OOMKilled", "container oom killed"),
            **_log("ERROR", "java.lang.OutOfMemoryError: Java heap space"),
            **_status(pods=[{"name": "order-2", "restarts": 8, "reason": "OOMKilled", "image": "ecomm-order:3.2.1-stable"}]),
        },
    ),
    GoldenCase(
        id="easy-stream-paused-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order 事件流 ingest 暂停 订单状态不同步",
        expected_doc_id="ecomm-order-stream-paused",
        challenge_type="easy_match",
        difficulty="easy",
        telemetry={"streams": [{"stream": "order-events", "status": "PAUSED"}]},
    ),
    GoldenCase(
        id="easy-disk-full-01",
        service="ecomm-manager",
        incident_description="【P1】ecomm-manager 磁盘满 日志盘使用率 95%",
        expected_doc_id="ecomm-manager-disk-full",
        challenge_type="easy_match",
        difficulty="easy",
        telemetry={**_log("ERROR", "no space left on device"), **_status(message="disk usage critical")},
    ),
    GoldenCase(
        id="easy-feature-flag-01",
        service="ecomm-manager",
        incident_description="【P2】ecomm-manager 功能开关误关 结算接口不可用",
        expected_doc_id="ecomm-manager-feature-flag",
        challenge_type="easy_match",
        difficulty="easy",
        telemetry={**_log("WARN", "feature settlement-v2 disabled by flag")},
    ),
    # --- same_service_disambiguation (hard) ---
    GoldenCase(
        id="disambig-pool-vs-rds-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order HikariPool 连接池耗尽 非 OOM 镜像稳定无升级",
        expected_doc_id="ecomm-order-connection-pool-exhaust",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-order-rds-timeout", "ecomm-order-memory-leak", "ecomm-order-crashloop"],
        telemetry={
            **_log("ERROR", "HikariPool - Connection is not available, pool exhausted"),
            **_status(pods=[{"name": "o1", "restarts": 0, "reason": "Running", "image": "ecomm-order:3.2.1-stable"}]),
        },
    ),
    GoldenCase(
        id="disambig-rds-vs-pool-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order RDS Communications link failure 数据库实例不可达",
        expected_doc_id="ecomm-order-rds-timeout",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-order-connection-pool-exhaust", "ecomm-order-deadlock-storm"],
        telemetry={**_log("ERROR", "Communications link failure to RDS instance")},
    ),
    GoldenCase(
        id="disambig-kafka-vs-stream-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order kafka consumer lag 升高 stream 仍 RUNNING",
        expected_doc_id="ecomm-order-kafka-consumer-lag",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-order-stream-paused"],
        telemetry={
            **_metrics("kafka_consumer_lag", 100, 50000),
            **_log("WARN", "consumer lag behind offset"),
            "streams": [{"stream": "order-events", "status": "RUNNING"}],
        },
    ),
    GoldenCase(
        id="disambig-deadlock-vs-rds-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order Deadlock found when trying to get lock",
        expected_doc_id="ecomm-order-deadlock-storm",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-order-rds-timeout", "ecomm-order-connection-pool-exhaust"],
        telemetry={**_log("ERROR", "Deadlock found when trying to get lock")},
    ),
    GoldenCase(
        id="disambig-cert-vs-crash-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order certificate expired SSLHandshakeException",
        expected_doc_id="ecomm-order-certificate-expiry",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-order-crashloop"],
        telemetry={**_log("ERROR", "certificate expired PKIX path validation failed")},
    ),
    GoldenCase(
        id="disambig-grpc-vs-payment-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order gRPC DEADLINE_EXCEEDED 调用 inventory 超时",
        expected_doc_id="ecomm-order-grpc-deadline-exceeded",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-order-payment-circuit", "ecomm-order-connection-pool-exhaust"],
        telemetry={**_log("ERROR", "grpc.StatusCode.DEADLINE_EXCEEDED")},
    ),
    GoldenCase(
        id="disambig-threadpool-vs-ratelimit-01",
        service="ecomm-manager",
        incident_description="【P1】ecomm-manager RejectedExecutionException 线程池耗尽",
        expected_doc_id="ecomm-manager-thread-pool-exhaust",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-manager-rate-limit", "ecomm-manager-jvm-gc-storm"],
        telemetry={**_log("ERROR", "RejectedExecutionException Thread pool is EXHAUSTED")},
    ),
    GoldenCase(
        id="disambig-gc-vs-ratelimit-01",
        service="ecomm-manager",
        incident_description="【P1】ecomm-manager Full GC overhead limit exceeded STW",
        expected_doc_id="ecomm-manager-jvm-gc-storm",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-manager-rate-limit", "ecomm-manager-thread-pool-exhaust"],
        telemetry={**_log("WARN", "GC overhead limit exceeded Pause Full GC")},
    ),
    GoldenCase(
        id="disambig-search-corrupt-vs-slow-01",
        service="ecomm-search",
        incident_description="【P1】ecomm-search index corruption shard failure",
        expected_doc_id="ecomm-search-index-corruption",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-search-slow-query-hotspot", "ecomm-search-shard-unassigned"],
        telemetry={**_log("ERROR", "index corruption shard failure")},
    ),
    GoldenCase(
        id="disambig-cache-hotkey-vs-memory-01",
        service="ecomm-cache",
        incident_description="【P1】ecomm-cache hot key single shard cpu 100%",
        expected_doc_id="ecomm-cache-hot-key",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-cache-redis-memory-full", "ecomm-cache-connection-storm"],
        telemetry={**_log("WARN", "hot key single shard cpu 100%")},
    ),
    GoldenCase(
        id="disambig-payment-circuit-vs-timeout-01",
        service="ecomm-payment",
        incident_description="【P0】ecomm-payment circuit breaker open bulkhead rejected",
        expected_doc_id="ecomm-payment-circuit-open",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-payment-channel-timeout"],
        telemetry={**_log("ERROR", "circuit breaker open bulkhead rejected")},
    ),
    GoldenCase(
        id="disambig-gateway-502-vs-timeout-01",
        service="ecomm-gateway",
        incident_description="【P1】ecomm-gateway 502 connection refused no healthy upstream",
        expected_doc_id="ecomm-gateway-502-bad-gateway",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-gateway-upstream-timeout"],
        telemetry={**_log("ERROR", "connection refused no healthy upstream")},
    ),
    GoldenCase(
        id="disambig-auth-jwt-vs-redis-01",
        service="ecomm-auth",
        incident_description="【P0】ecomm-auth JWT signature does not match 全站登录失败",
        expected_doc_id="ecomm-auth-jwt-secret-mismatch",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-auth-session-redis-down"],
        telemetry={**_log("ERROR", "JWT signature does not match invalid signature")},
    ),
    GoldenCase(
        id="disambig-inventory-oversell-vs-lag-01",
        service="ecomm-inventory",
        incident_description="【P1】ecomm-inventory 超卖告警 库存为负 negative stock",
        expected_doc_id="ecomm-inventory-oversell-race",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-inventory-sync-lag", "ecomm-inventory-reservation-leak"],
        telemetry={**_log("ERROR", "oversell detected negative stock count below zero")},
    ),
    # --- cross_service_trap ---
    GoldenCase(
        id="cross-timeout-order-vs-payment-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order 支付渠道 timeout 下单失败",
        expected_doc_id="ecomm-order-payment-circuit",
        challenge_type="cross_service_trap",
        difficulty="medium",
        must_not_select=["ecomm-payment-channel-timeout"],
        telemetry={**_log("WARN", "payment channel timeout downstream")},
    ),
    GoldenCase(
        id="cross-cache-flush-vs-hotkey-01",
        service="ecomm-manager",
        incident_description="【P2】ecomm-manager 读缓存延迟高 误怀疑 Redis",
        expected_doc_id="ecomm-manager-cache-stampede",
        challenge_type="cross_service_trap",
        difficulty="medium",
        must_not_select=["ecomm-cache-hot-key", "ecomm-cache-redis-memory-full"],
        telemetry={**_log("WARN", "cache stampede thundering herd on merchant-profile")},
    ),
    GoldenCase(
        id="cross-catalog-db-01",
        service="ecomm-catalog",
        incident_description="【P1】ecomm-catalog Communications link failure 目录库",
        expected_doc_id="ecomm-catalog-db-connection-timeout",
        challenge_type="easy_match",
        difficulty="medium",
        must_not_select=["ecomm-catalog-es-cluster-red"],
        telemetry={**_log("ERROR", "Communications link failure catalog db timeout")},
    ),
    GoldenCase(
        id="cross-notification-smtp-01",
        service="ecomm-notification",
        incident_description="【P2】ecomm-notification SMTP connect failed 邮件全失败",
        expected_doc_id="ecomm-notification-email-smtp-fail",
        challenge_type="easy_match",
        difficulty="medium",
        must_not_select=["ecomm-notification-webhook-retry-storm"],
        telemetry={**_log("ERROR", "SMTP connect failed 535 authentication failed")},
    ),
    # --- lexical_trap ---
    GoldenCase(
        id="lexical-timeout-gateway-not-order-01",
        service="ecomm-gateway",
        incident_description="【P1】ecomm-gateway upstream timed out 504 Gateway Timeout",
        expected_doc_id="ecomm-gateway-upstream-timeout",
        challenge_type="lexical_trap",
        difficulty="medium",
        must_not_select=["ecomm-order-rds-timeout", "ecomm-order-grpc-deadline-exceeded", "ecomm-payment-channel-timeout"],
        telemetry={**_log("ERROR", "upstream timed out 504 Gateway Timeout")},
    ),
    GoldenCase(
        id="lexical-restart-not-crashloop-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order Pod 重启增多 OOMKilled heap space",
        expected_doc_id="ecomm-order-memory-leak",
        challenge_type="lexical_trap",
        difficulty="hard",
        must_not_select=["ecomm-order-crashloop"],
        telemetry={
            **_k8s("OOMKilled", "container oom killed"),
            **_log("ERROR", "java.lang.OutOfMemoryError Java heap space"),
        },
    ),
    GoldenCase(
        id="lexical-rate-limit-gateway-01",
        service="ecomm-gateway",
        incident_description="【P2】ecomm-gateway CORS preflight storm OPTIONS flood",
        expected_doc_id="ecomm-gateway-cors-preflight-storm",
        challenge_type="lexical_trap",
        difficulty="medium",
        must_not_select=["ecomm-manager-rate-limit", "ecomm-gateway-auth-filter-block"],
        telemetry={**_log("WARN", "CORS preflight storm OPTIONS flood")},
    ),
    # --- negative_constraint ---
    GoldenCase(
        id="neg-crashloop-no-restart-01",
        service="ecomm-order",
        incident_description="【P0】ecomm-order BackOff bad image ecomm-order:3.3.0-bad",
        expected_doc_id="ecomm-order-crashloop",
        challenge_type="negative_constraint",
        difficulty="hard",
        must_not_select=["ecomm-order-memory-leak"],
        telemetry={
            **_k8s("BackOff", "CrashLoopBackOff"),
            **_status(ready=0, pods=[{"image": "ecomm-order:3.3.0-bad", "reason": "CrashLoopBackOff"}]),
        },
    ),
    GoldenCase(
        id="neg-memory-no-rollback-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order OOMKilled 无升级记录 连接池耗尽",
        expected_doc_id="ecomm-order-memory-leak",
        challenge_type="negative_constraint",
        difficulty="hard",
        must_not_select=["ecomm-order-crashloop"],
        telemetry={**_log("ERROR", "connection pool exhausted"), **_k8s("OOMKilled", "oom")},
    ),
    # --- novel (no good runbook — expect low relevance or novel after eval) ---
    GoldenCase(
        id="novel-k8s-node-notready-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order Pod Pending 节点 NotReady 调度失败",
        expected_doc_id=None,
        expected_runbook_available=False,
        challenge_type="novel",
        difficulty="medium",
        telemetry={**_k8s("FailedScheduling", "node(s) not ready"), **_status(ready=0, desired=3)},
    ),
    GoldenCase(
        id="novel-fulfillment-01",
        service="ecomm-fulfillment",
        incident_description="【P1】ecomm-fulfillment 仓配 WMS 接口超时 无 runbook",
        expected_doc_id=None,
        expected_runbook_available=False,
        challenge_type="novel",
        difficulty="easy",
        telemetry={**_log("ERROR", "WMS warehouse API timeout")},
    ),
    GoldenCase(
        id="novel-security-breach-01",
        service="ecomm-manager",
        incident_description="【P0】ecomm-manager 疑似数据泄露 非标准运维故障",
        expected_doc_id=None,
        expected_runbook_available=False,
        challenge_type="novel",
        difficulty="medium",
        telemetry={**_log("FATAL", "security audit suspicious data exfiltration alert")},
    ),
    GoldenCase(
        id="novel-gpu-outage-01",
        service="ecomm-recommendation",
        incident_description="【P1】ecomm-recommendation GPU 节点宕机 推理不可用",
        expected_doc_id=None,
        expected_runbook_available=False,
        challenge_type="novel",
        difficulty="easy",
        telemetry={**_log("ERROR", "CUDA driver shutdown GPU unavailable")},
    ),
    # --- more eval corpus easy matches ---
    GoldenCase(
        id="easy-payment-settlement-01",
        service="ecomm-payment",
        incident_description="【P2】ecomm-payment reconcile mismatch settlement delta",
        expected_doc_id="ecomm-payment-settlement-reconcile-fail",
        challenge_type="easy_match",
        difficulty="medium",
        telemetry={**_log("ERROR", "reconcile mismatch settlement delta non-zero")},
    ),
    GoldenCase(
        id="easy-inventory-sync-01",
        service="ecomm-inventory",
        incident_description="【P1】ecomm-inventory sync lag warehouse delta pending",
        expected_doc_id="ecomm-inventory-sync-lag",
        challenge_type="easy_match",
        difficulty="medium",
        must_not_select=["ecomm-inventory-oversell-race"],
        telemetry={**_log("WARN", "inventory sync lag warehouse delta pending")},
    ),
    GoldenCase(
        id="easy-auth-brute-01",
        service="ecomm-auth",
        incident_description="【P1】ecomm-auth brute force detected account locked",
        expected_doc_id="ecomm-auth-login-brute-force",
        challenge_type="easy_match",
        difficulty="medium",
        telemetry={**_log("WARN", "brute force detected account locked")},
    ),
    GoldenCase(
        id="disambig-cache-memory-vs-hotkey-01",
        service="ecomm-cache",
        incident_description="【P1】ecomm-cache maxmemory OOM command not allowed",
        expected_doc_id="ecomm-cache-redis-memory-full",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-cache-hot-key"],
        telemetry={**_log("ERROR", "OOM command not allowed maxmemory")},
    ),
    GoldenCase(
        id="disambig-catalog-es-01",
        service="ecomm-catalog",
        incident_description="【P1】ecomm-catalog ElasticsearchException cluster_block read-only",
        expected_doc_id="ecomm-catalog-es-cluster-red",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-catalog-db-connection-timeout"],
        telemetry={**_log("ERROR", "ElasticsearchException cluster_block read-only")},
    ),
    GoldenCase(
        id="disambig-notification-webhook-01",
        service="ecomm-notification",
        incident_description="【P1】ecomm-notification webhook retry storm DLQ growing",
        expected_doc_id="ecomm-notification-webhook-retry-storm",
        challenge_type="same_service_disambiguation",
        difficulty="medium",
        must_not_select=["ecomm-notification-email-smtp-fail"],
        telemetry={**_log("ERROR", "webhook retry storm DLQ growing")},
    ),
    GoldenCase(
        id="disambig-order-network-01",
        service="ecomm-order",
        incident_description="【P1】ecomm-order UnknownHostException no such host",
        expected_doc_id="ecomm-order-network-partition",
        challenge_type="easy_match",
        difficulty="medium",
        must_not_select=["ecomm-order-certificate-expiry"],
        telemetry={**_log("ERROR", "UnknownHostException no such host")},
    ),
    GoldenCase(
        id="disambig-manager-dns-01",
        service="ecomm-manager",
        incident_description="【P1】ecomm-manager UnknownHostException 下游解析失败",
        expected_doc_id="ecomm-manager-dns-resolution-fail",
        challenge_type="easy_match",
        difficulty="medium",
        must_not_select=["ecomm-manager-rate-limit"],
        telemetry={**_log("ERROR", "UnknownHostException downstream")},
    ),
    GoldenCase(
        id="disambig-search-shard-01",
        service="ecomm-search",
        incident_description="【P1】ecomm-search unassigned shard cluster_block",
        expected_doc_id="ecomm-search-shard-unassigned",
        challenge_type="same_service_disambiguation",
        difficulty="hard",
        must_not_select=["ecomm-search-index-corruption"],
        telemetry={**_log("ERROR", "unassigned shard cluster_block")},
    ),
    GoldenCase(
        id="disambig-payment-idempotency-01",
        service="ecomm-payment",
        incident_description="【P2】ecomm-payment idempotency key collision duplicate payment",
        expected_doc_id="ecomm-payment-idempotency-collision",
        challenge_type="easy_match",
        difficulty="medium",
        must_not_select=["ecomm-payment-circuit-open"],
        telemetry={**_log("WARN", "idempotency key collision duplicate payment rejected")},
    ),
    GoldenCase(
        id="disambig-cache-pipeline-01",
        service="ecomm-cache",
        incident_description="【P2】ecomm-cache pipeline timeout batch get timeout",
        expected_doc_id="ecomm-cache-pipeline-timeout",
        challenge_type="same_service_disambiguation",
        difficulty="medium",
        must_not_select=["ecomm-cache-connection-storm"],
        telemetry={**_log("WARN", "pipeline timeout batch get timeout")},
    ),
    GoldenCase(
        id="disambig-inventory-reservation-01",
        service="ecomm-inventory",
        incident_description="【P2】ecomm-inventory reservation leak unreleased hold",
        expected_doc_id="ecomm-inventory-reservation-leak",
        challenge_type="same_service_disambiguation",
        difficulty="medium",
        must_not_select=["ecomm-inventory-oversell-race"],
        telemetry={**_log("WARN", "reservation leak unreleased hold")},
    ),
]

assert len(GOLDEN_CASES) >= 40, len(GOLDEN_CASES)

# Subset for manual / nightly real-LLM rubric smoke (API cost ~10 calls).
REAL_LLM_SMOKE_IDS: tuple[str, ...] = (
    "disambig-pool-vs-rds-01",
    "disambig-rds-vs-pool-01",
    "disambig-kafka-vs-stream-01",
    "lexical-restart-not-crashloop-01",
    "disambig-payment-circuit-vs-timeout-01",
    "disambig-gateway-502-vs-timeout-01",
    "disambig-auth-jwt-vs-redis-01",
    "disambig-search-corrupt-vs-slow-01",
    "disambig-cache-memory-vs-hotkey-01",
    "neg-crashloop-no-restart-01",
)

_GOLDEN_BY_ID = {c.id: c for c in GOLDEN_CASES}


def select_golden_cases(
    *,
    ids: list[str] | None = None,
    challenge_type: str | None = None,
    difficulty: str | None = None,
    limit: int | None = None,
    smoke_only: bool = False,
) -> list[GoldenCase]:
    if smoke_only:
        cases = [_GOLDEN_BY_ID[i] for i in REAL_LLM_SMOKE_IDS if i in _GOLDEN_BY_ID]
    elif ids:
        cases = [_GOLDEN_BY_ID[i] for i in ids if i in _GOLDEN_BY_ID]
    else:
        cases = list(GOLDEN_CASES)
    if challenge_type:
        cases = [c for c in cases if c.challenge_type == challenge_type]
    if difficulty:
        cases = [c for c in cases if c.difficulty == difficulty]
    if limit is not None:
        cases = cases[:limit]
    return cases
