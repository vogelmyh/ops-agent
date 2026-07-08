"""Curated runbook specs for RAG eval corpus expansion.

Each spec renders a full markdown runbook under data/runbooks/.
Run: python scripts/generate_rag_corpus.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Risk = Literal["low", "medium", "high"]


@dataclass
class Remediation:
    tool: str
    detail: str
    risk: Risk = "medium"


@dataclass
class RunbookSpec:
    stem: str
    service: str
    title: str
    excludes: list[str]
    symptoms: list[str]
    diagnosis: list[str]
    root_cause: str
    remediation: list[Remediation]
    verification: list[str]
    forbidden: list[str]
    followup: str = "若 24h 内复发，升级对应服务 on-call 与平台团队。"


def render_markdown(spec: RunbookSpec) -> str:
    lines = [
        f"# {spec.title}",
        "",
        "## 适用范围",
        f"- **仅适用于服务 `{spec.service}`**。",
    ]
    if spec.excludes:
        lines.append(f"- 不适用于：{'；'.join(spec.excludes)}。")
    lines.extend(["", "## 症状"])
    lines.extend(f"- {s}" for s in spec.symptoms)
    lines.extend(["", "## 诊断（先确认再动手）"])
    for i, step in enumerate(spec.diagnosis, 1):
        lines.append(f"{i}. {step}")
    lines.extend(["", "## 根因", spec.root_cause, "", "## 处置（标准修复）"])
    for i, rem in enumerate(spec.remediation, 1):
        lines.append(f"{i}. 执行 **`{rem.tool}`**：{rem.detail}（policy risk={rem.risk}）。")
    lines.extend(["", "## 验证（修复后必须满足）"])
    lines.extend(f"- {v}" for v in spec.verification)
    lines.extend(["", "## 勿用手段"])
    lines.extend(f"- {f}" for f in spec.forbidden)
    lines.extend(["", "## 后续与升级", spec.followup, ""])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 38 eval expansion runbooks (mixed with 17 production runbooks → ~55 total)
# ---------------------------------------------------------------------------

RUNBOOK_SPECS: list[RunbookSpec] = [
    # --- ecomm-order (6) ---
    RunbookSpec(
        stem="ecomm-order-connection-pool-exhaust",
        service="ecomm-order",
        title="电商数据面下单服务连接池耗尽",
        excludes=["坏镜像 CrashLoop", "OOMKilled 内存泄漏", "RDS 实例故障", "支付熔断", "事件流暂停"],
        symptoms=[
            "下单 API 超时，错误率升高，Pod 仍为 Running 且镜像版本稳定。",
            "应用日志：`connection pool exhausted, cannot acquire connection`、`HikariPool - Connection is not available`。",
            "K8s 事件通常无 BackOff；`get_latest_operation` 无近期 upgrade。",
            "指标 `order_error_rate` 上升，`ready_replicas` 正常。",
        ],
        diagnosis=[
            "应用日志确认 connection pool exhausted，而非 OOM 或 startup failed。",
            "服务状态：Pod image 为当前稳定版本，非 bad 镜像。",
            "最近操作：无 rollback/upgrade 记录。",
            "区分于 RDS 超时：日志无 `Communications link failure` / RDS 连接拒绝为主因。",
        ],
        root_cause="应用侧数据库连接池配置过小或连接泄漏，导致 acquire 超时；非数据库实例宕机。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-order`，**config_key**: `datasource.max-pool-size`，**config_value**: `80`",
                "low",
            ),
            Remediation(
                "restart_pods",
                "**service**: `ecomm-order`，**strategy**: `rolling`（池配置生效后仍僵死时）",
                "medium",
            ),
        ],
        verification=[
            "`order_error_rate` 降至基线（< 1%）。",
            "日志不再持续 `connection pool exhausted`。",
        ],
        forbidden=[
            "**不要** `rollback_deployment`（镜像未变更）。",
            "**不要** `scale_replicas` 代替池配置修复（新副本同样耗尽）。",
        ],
    ),
    RunbookSpec(
        stem="ecomm-order-kafka-consumer-lag",
        service="ecomm-order",
        title="电商数据面下单服务 Kafka 消费积压",
        excludes=["事件流 ingest 暂停（stream paused）", "CrashLoop", "支付熔断"],
        symptoms=[
            "订单状态同步延迟，下游看到 pending 订单堆积。",
            "指标 `kafka_consumer_lag` 持续升高（> 10000）。",
            "应用日志：`consumer poll timeout`、`lag behind offset`。",
            "Stream 状态为 RUNNING（非 PAUSED）。",
        ],
        diagnosis=[
            "确认 `kafka_consumer_lag` 异常升高。",
            "检查 stream 状态：consumer group 活跃，非 ingest 暂停。",
            "区分 stream-paused：无 `stream paused` / ingest stopped 日志。",
            "最近无坏镜像升级记录。",
        ],
        root_cause="消费者处理变慢或分区热点导致 lag 堆积；ingest 通道正常。",
        remediation=[
            Remediation(
                "scale_replicas",
                "**service**: `ecomm-order`，**replicas**: `5`（扩展消费者实例）",
                "medium",
            ),
            Remediation(
                "restart_pods",
                "**service**: `ecomm-order`，**strategy**: `rolling`（单消费者僵死时）",
                "medium",
            ),
        ],
        verification=["`kafka_consumer_lag` 回落至 < 1000。", "订单状态同步延迟恢复正常。"],
        forbidden=[
            "**不要** `resume_event_stream`（stream 未 paused）。",
            "**不要** `rollback_deployment`（非版本问题）。",
        ],
    ),
    RunbookSpec(
        stem="ecomm-order-deadlock-storm",
        service="ecomm-order",
        title="电商数据面下单服务数据库死锁风暴",
        excludes=["RDS 网络超时", "连接池耗尽", "坏镜像"],
        symptoms=[
            "下单失败激增，延迟抖动。",
            "应用日志：`Deadlock found when trying to get lock`、`MySQLTransactionRollbackException`。",
            "指标 `order_error_rate` 突增；DB 连接数正常。",
        ],
        diagnosis=[
            "日志明确 Deadlock / lock wait timeout。",
            "非 Communications link failure（RDS 网络类）。",
            "非 connection pool exhausted。",
            "Pod 健康，镜像稳定。",
        ],
        root_cause="并发下单热点行竞争引发 InnoDB 死锁风暴。",
        remediation=[
            Remediation(
                "restart_pods",
                "**service**: `ecomm-order`，**strategy**: `rolling`（清理僵死事务连接）",
                "medium",
            ),
        ],
        verification=["`order_error_rate` 恢复。", "死锁日志频率降至基线。"],
        forbidden=[
            "**不要** `patch_config` 随意改池大小（非根因）。",
            "**不要** `rollback_deployment`。",
        ],
    ),
    RunbookSpec(
        stem="ecomm-order-certificate-expiry",
        service="ecomm-order",
        title="电商数据面下单服务 TLS 证书过期",
        excludes=["坏镜像 CrashLoop", "内存泄漏", "RDS 超时"],
        symptoms=[
            "对外 HTTPS 调用失败，下单链路中断。",
            "应用日志：`certificate expired`、`SSLHandshakeException`、` PKIX path validation failed`。",
            "Pod Running；近期可能有 cert 轮换变更。",
        ],
        diagnosis=[
            "日志含 certificate expired / SSLHandshakeException。",
            "非 Application startup failed / BackOff。",
            "非 OOMKilled。",
            "检查最近 operation 是否含 cert/config 变更。",
        ],
        root_cause="服务端或出站 TLS 证书过期，握手失败。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-order`，**config_key**: `tls.trust-store-version`，**config_value**: `2026-06`",
                "low",
            ),
            Remediation(
                "restart_pods",
                "**service**: `ecomm-order`，**strategy**: `rolling`",
                "medium",
            ),
        ],
        verification=["SSL 握手错误日志消失。", "下单成功率恢复。"],
        forbidden=["**不要** `rollback_deployment`（除非明确坏镜像）。"],
    ),
    RunbookSpec(
        stem="ecomm-order-grpc-deadline-exceeded",
        service="ecomm-order",
        title="电商数据面下单服务 gRPC 超时级联",
        excludes=["支付熔断", "RDS 超时", "连接池耗尽"],
        symptoms=[
            "下单超时，P99 延迟飙升。",
            "应用日志：`DEADLINE_EXCEEDED`、`grpc.StatusCode.DEADLINE_EXCEEDED`。",
            "下游 inventory/payment 调用超时；Pod 正常。",
        ],
        diagnosis=[
            "日志以 gRPC DEADLINE_EXCEEDED 为主，非 pool exhausted。",
            "非 payment circuit open 主导（无 bulkhead/circuit 日志）。",
            "指标延迟升但 error 可能未达熔断阈值。",
        ],
        root_cause="下游依赖响应慢导致 gRPC 客户端 deadline 超时级联。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-order`，**config_key**: `grpc.deadline-ms`，**config_value**: `8000`",
                "low",
            ),
            Remediation(
                "enable_circuit_breaker",
                "**service**: `ecomm-order`，**target**: `ecomm-inventory`",
                "medium",
            ),
        ],
        verification=["P99 延迟回落至 SLA 内。", "DEADLINE_EXCEEDED 日志减少。"],
        forbidden=["**不要** `restart_pods` 作为首选（未缓解下游慢）。"],
    ),
    RunbookSpec(
        stem="ecomm-order-network-partition",
        service="ecomm-order",
        title="电商数据面下单服务网络分区 DNS 故障",
        excludes=["RDS 实例故障", "证书过期", "CrashLoop"],
        symptoms=[
            "大量 `UnknownHostException`、`no such host` 日志。",
            "跨服务调用全部失败；Pod Running。",
            "K8s 事件偶发 `FailedMount` / DNS 相关 warning。",
        ],
        diagnosis=[
            "日志含 UnknownHostException / no such host。",
            "非 SSL/certificate 错误。",
            "非数据库 Communications link failure 单独主导。",
        ],
        root_cause="集群 DNS 或 CoreDNS 异常导致服务发现失败。",
        remediation=[
            Remediation(
                "restart_pods",
                "**service**: `ecomm-order`，**strategy**: `rolling`",
                "medium",
            ),
            Remediation(
                "scale_replicas",
                "**service**: `ecomm-order`，**replicas**: `3`",
                "low",
            ),
        ],
        verification=["UnknownHost 日志消失。", "跨服务调用恢复。"],
        forbidden=["**不要** `patch_config` 改数据源（非配置项根因）。"],
    ),
    # --- ecomm-manager (5) ---
    RunbookSpec(
        stem="ecomm-manager-thread-pool-exhaust",
        service="ecomm-manager",
        title="电商管理面线程池耗尽",
        excludes=["限流误配", "CrashLoop", "磁盘满"],
        symptoms=[
            "管理 API 超时，线程池拒绝任务。",
            "应用日志：`RejectedExecutionException`、`Thread pool is EXHAUSTED`。",
            "Pod Running；`admin_api_qps` 可能正常或下降。",
        ],
        diagnosis=[
            "日志明确线程池耗尽，非 rate limit exceeded。",
            "核对 `rate-limit.max-qps` 正常（约 5000）。",
            "无 CrashLoopBackOff。",
        ],
        root_cause="异步任务堆积或线程池 max 配置过低。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-manager`，**config_key**: `executor.max-threads`，**config_value**: `200`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-manager`，**strategy**: `rolling`", "medium"),
        ],
        verification=["RejectedExecutionException 消失。", "API P99 恢复。"],
        forbidden=["**不要**仅 `patch_config` rate-limit（非限流问题）。"],
    ),
    RunbookSpec(
        stem="ecomm-manager-jvm-gc-storm",
        service="ecomm-manager",
        title="电商管理面 JVM GC 风暴导致 STW",
        excludes=["限流误配", "OOMKilled", "磁盘满"],
        symptoms=[
            "API 周期性卡顿，P99 尖刺。",
            "应用日志：`GC overhead limit exceeded`、`Pause Full GC` 频繁。",
            "Pod 未 OOM；heap 使用率高。",
        ],
        diagnosis=[
            "GC 日志频繁 Full GC，非 rate limit。",
            "非 OOMKilled（进程仍在）。",
            "镜像稳定。",
        ],
        root_cause="堆内存压力大或 GC 参数不当导致 STW 过长。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-manager`，**config_key**: `jvm.gc.max-pause-ms`，**config_value**: `200`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-manager`，**strategy**: `rolling`", "medium"),
        ],
        verification=["Full GC 频率下降。", "P99 尖刺消失。"],
        forbidden=["**不要** `rollback_deployment`（非镜像问题）。"],
    ),
    RunbookSpec(
        stem="ecomm-manager-connection-leak",
        service="ecomm-manager",
        title="电商管理面 HTTP 连接泄漏",
        excludes=["限流误配", "线程池耗尽"],
        symptoms=[
            "管理 API 变慢，文件句柄或连接数接近上限。",
            "应用日志：`too many open files`、`Connection leak detection`。",
        ],
        diagnosis=[
            "连接泄漏日志，非 rate limit exceeded。",
            "Pod 仍 Ready。",
        ],
        root_cause="HTTP 客户端未释放连接导致泄漏。",
        remediation=[Remediation("restart_pods", "**service**: `ecomm-manager`，**strategy**: `rolling`", "medium")],
        verification=["too many open files 告警消失。", "API 延迟恢复。"],
        forbidden=["**不要** `patch_config` rate-limit。"],
    ),
    RunbookSpec(
        stem="ecomm-manager-cache-stampede",
        service="ecomm-manager",
        title="电商管理面本地缓存击穿",
        excludes=["限流误配", "Redis 故障"],
        symptoms=[
            "热点商家接口延迟飙升。",
            "应用日志：`cache stampede`、`thundering herd on merchant-profile`。",
            "下游 Redis 压力偶发升高。",
        ],
        diagnosis=[
            "缓存击穿日志，非 rate limit。",
            "非 admin_api_qps 整体骤降模式。",
        ],
        root_cause="热点 key 过期瞬间大量回源。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-manager`，**config_key**: `cache.hot-key-ttl-jitter-sec`，**config_value**: `30`",
                "low",
            ),
            Remediation("flush_cache", "**service**: `ecomm-manager`，**scope**: `merchant-profile`", "low"),
        ],
        verification=["热点接口 P99 恢复。", "stampede 日志消失。"],
        forbidden=["**不要** `rollback_deployment`。"],
    ),
    RunbookSpec(
        stem="ecomm-manager-dns-resolution-fail",
        service="ecomm-manager",
        title="电商管理面 DNS 解析失败",
        excludes=["限流误配", "磁盘满"],
        symptoms=[
            "调用下游失败，`UnknownHostException`。",
            "管理 API 部分功能不可用。",
        ],
        diagnosis=[
            "UnknownHost 为主，非 rate limit。",
            "Pod Running。",
        ],
        root_cause="DNS 解析异常或错误 service 名配置。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-manager`，**config_key**: `dns.cache-ttl-sec`，**config_value**: `60`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-manager`，**strategy**: `rolling`", "medium"),
        ],
        verification=["UnknownHost 消失。", "下游调用恢复。"],
        forbidden=["**不要** `patch_config` rate-limit。"],
    ),
    # --- ecomm-search (5) ---
    RunbookSpec(
        stem="ecomm-search-index-corruption",
        service="ecomm-search",
        title="电商搜索索引分片损坏",
        excludes=["OOM 导致索引重建中断", "查询热点"],
        symptoms=[
            "搜索返回空结果或分片错误。",
            "应用日志：`index corruption`、`shard failure`、`corrupt file`。",
            "索引重建任务可能失败。",
        ],
        diagnosis=[
            "corruption / shard failure 日志。",
            "非单纯 heap OOM（可有损坏后续）。",
        ],
        root_cause="磁盘或异常关机导致 Lucene 分片损坏。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-search`，**config_key**: `index.rebuild-from-snapshot`，**config_value**: `true`",
                "medium",
            ),
            Remediation("restart_pods", "**service**: `ecomm-search`，**strategy**: `rolling`", "medium"),
        ],
        verification=["搜索可用率恢复。", "corruption 日志消失。"],
        forbidden=["**不要** `flush_cache` 代替索引重建。"],
    ),
    RunbookSpec(
        stem="ecomm-search-slow-query-hotspot",
        service="ecomm-search",
        title="电商搜索慢查询热点",
        excludes=["索引损坏", "OOM 索引重建"],
        symptoms=[
            "搜索 P99 延迟高但无索引损坏错误。",
            "应用日志：`slow query`、`took_millis > 3000`、特定 query pattern。",
        ],
        diagnosis=[
            "慢查询日志，无 corruption。",
            "副本同步正常。",
        ],
        root_cause="热点查询未命中缓存或缺少索引字段。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-search`，**config_key**: `query.slow-log-threshold-ms`，**config_value**: `2000`",
                "low",
            ),
            Remediation("scale_replicas", "**service**: `ecomm-search`，**replicas**: `4`", "low"),
        ],
        verification=["P99 < 1s。", "slow query 比例下降。"],
        forbidden=["**不要**全量 rebuild 索引（无损坏证据）。"],
    ),
    RunbookSpec(
        stem="ecomm-search-replica-sync-lag",
        service="ecomm-search",
        title="电商搜索副本同步延迟",
        excludes=["索引损坏", "分片 unassigned"],
        symptoms=[
            "搜索结果不一致，新商品不可见。",
            "日志：`replica lag`、`sync delayed`。",
        ],
        diagnosis=["replica lag 日志。", "主分片健康。"],
        root_cause="副本同步落后主分片。",
        remediation=[Remediation("restart_pods", "**service**: `ecomm-search`，**strategy**: `rolling`", "medium")],
        verification=["lag 指标回落。", "新数据可搜索。"],
        forbidden=["**不要** `flush_cache` 作为唯一手段。"],
    ),
    RunbookSpec(
        stem="ecomm-search-shard-unassigned",
        service="ecomm-search",
        title="电商搜索分片未分配",
        excludes=["慢查询热点", "索引逻辑损坏"],
        symptoms=[
            "集群 red/yellow，部分分片 UNASSIGNED。",
            "日志：`unassigned shard`、`cluster_block`。",
        ],
        diagnosis=["分片 UNASSIGNED。", "非 slow query 主导。"],
        root_cause="节点宕机或磁盘水位导致分片无法分配。",
        remediation=[
            Remediation("scale_replicas", "**service**: `ecomm-search`，**replicas**: `3`", "medium"),
            Remediation("restart_pods", "**service**: `ecomm-search`，**strategy**: `rolling`", "medium"),
        ],
        verification=["集群 green。", "UNASSIGNED 为 0。"],
        forbidden=["**不要**仅调慢查询阈值。"],
    ),
    # --- ecomm-cache (5) ---
    RunbookSpec(
        stem="ecomm-cache-hot-key",
        service="ecomm-cache",
        title="电商缓存 Redis 热 key 打满单分片",
        excludes=["Redis 内存满", "连接风暴", "Pod OOM"],
        symptoms=[
            "单 key QPS 极高，延迟抖动。",
            "日志：`hot key`、`single shard cpu 100%`。",
            "Redis 内存未满。",
        ],
        diagnosis=["hot key 证据。", "非 OOMKilled。", "非 maxmemory 满。"],
        root_cause="热点 key 分布不均。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-cache`，**config_key**: `redis.hot-key-split`，**config_value**: `enabled`",
                "low",
            ),
            Remediation("flush_cache", "**service**: `ecomm-cache`，**scope**: `hot-sku`", "low"),
        ],
        verification=["单分片 CPU 回落。", "P99 正常。"],
        forbidden=["**不要** `restart_pods` 作为首选（丢热点预热）。"],
    ),
    RunbookSpec(
        stem="ecomm-cache-redis-memory-full",
        service="ecomm-cache",
        title="电商缓存 Redis 内存打满",
        excludes=["热 key", "连接风暴"],
        symptoms=[
            "写入失败 `OOM command not allowed`。",
            "日志：`maxmemory`、`eviction policy`。",
            "读延迟升高。",
        ],
        diagnosis=["maxmemory 相关日志。", "非 hot key cpu 单分片模式。"],
        root_cause="缓存容量不足或 TTL 过长大面积堆积。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-cache`，**config_key**: `redis.maxmemory-policy`，**config_value**: `allkeys-lru`",
                "low",
            ),
            Remediation("flush_cache", "**service**: `ecomm-cache`，**scope**: `low-value-keys`", "medium"),
        ],
        verification=["写入恢复。", "eviction 正常。"],
        forbidden=["**不要**无限 `scale_replicas` 而不调 policy。"],
    ),
    RunbookSpec(
        stem="ecomm-cache-connection-storm",
        service="ecomm-cache",
        title="电商缓存 Redis 连接风暴",
        excludes=["热 key", "内存满"],
        symptoms=[
            "Redis `max clients reached`。",
            "应用连接超时；Pod 频繁重连。",
        ],
        diagnosis=["max clients 日志。", "内存未满。"],
        root_cause="客户端连接池配置过大或泄漏。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-cache`，**config_key**: `redis.max-clients`，**config_value**: `10000`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-cache`，**strategy**: `rolling`", "medium"),
        ],
        verification=["连接数稳定。", "拒绝连接消失。"],
        forbidden=["**不要** `flush_cache`（非数据问题）。"],
    ),
    RunbookSpec(
        stem="ecomm-cache-pipeline-timeout",
        service="ecomm-cache",
        title="电商缓存 Pipeline 批量超时",
        excludes=["热 key", "内存满", "连接风暴"],
        symptoms=[
            "批量读超时，单 key 正常。",
            "日志：`pipeline timeout`、`batch get timeout`。",
        ],
        diagnosis=["pipeline/batch 超时。", "单 op 正常。"],
        root_cause="pipeline 批次过大或网络抖动。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-cache`，**config_key**: `redis.pipeline-batch-size`，**config_value**: `50`",
                "low",
            ),
        ],
        verification=["batch 超时消失。", "批量读成功。"],
        forbidden=["**不要** `flush_cache` 全库。"],
    ),
    # --- ecomm-catalog (2) ---
    RunbookSpec(
        stem="ecomm-catalog-db-connection-timeout",
        service="ecomm-catalog",
        title="电商目录服务数据库连接超时",
        excludes=["ES 集群红", "搜索索引问题"],
        symptoms=[
            "目录 API 超时。",
            "日志：`Communications link failure`、`catalog db timeout`。",
        ],
        diagnosis=["DB 连接超时日志。", "ES 集群正常。"],
        root_cause="目录库连接池或网络到 catalog DB 异常。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-catalog`，**config_key**: `datasource.connection-timeout-ms`，**config_value**: `5000`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-catalog`，**strategy**: `rolling`", "medium"),
        ],
        verification=["目录 API 成功率恢复。"],
        forbidden=["**不要** `resume_event_stream`。"],
    ),
    RunbookSpec(
        stem="ecomm-catalog-es-cluster-red",
        service="ecomm-catalog",
        title="电商目录 ES 集群不可用",
        excludes=["MySQL 连接超时"],
        symptoms=[
            "商品搜索/目录查询失败。",
            "日志：`ElasticsearchException`、`cluster_block read-only`。",
        ],
        diagnosis=["ES 异常为主。", "MySQL 连接正常。"],
        root_cause="ES 磁盘水位或分片异常导致集群 red。",
        remediation=[
            Remediation("cleanup_storage", "**service**: `ecomm-catalog`，**path**: `/data/es`", "medium"),
            Remediation("restart_pods", "**service**: `ecomm-catalog`，**strategy**: `rolling`", "medium"),
        ],
        verification=["ES 集群 green。", "目录查询恢复。"],
        forbidden=["**不要**仅调 MySQL 池（非 DB 根因）。"],
    ),
    # --- ecomm-payment (5) ---
    RunbookSpec(
        stem="ecomm-payment-channel-timeout",
        service="ecomm-payment",
        title="电商支付渠道响应超时",
        excludes=["支付熔断已打开", "对账失败"],
        symptoms=[
            "支付 pend 比例升高。",
            "日志：`channel timeout`、`payment gateway read timed out`。",
            "熔断器未 open。",
        ],
        diagnosis=["channel timeout。", "无 circuit open 主导日志。"],
        root_cause="外部支付渠道响应慢。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-payment`，**config_key**: `channel.timeout-ms`，**config_value**: `15000`",
                "low",
            ),
        ],
        verification=["支付成功率恢复。", "timeout 日志减少。"],
        forbidden=["**不要** `enable_circuit_breaker` 作为首选（渠道仍可用）。"],
    ),
    RunbookSpec(
        stem="ecomm-payment-circuit-open",
        service="ecomm-payment",
        title="电商支付熔断器打开",
        excludes=["渠道单次超时", "结算对账"],
        symptoms=[
            "支付全部失败，快速失败。",
            "日志：`circuit breaker open`、`bulkhead rejected`。",
        ],
        diagnosis=["circuit open 明确。", "非单次 read timeout。"],
        root_cause="下游渠道连续失败触发熔断。",
        remediation=[
            Remediation(
                "enable_circuit_breaker",
                "**service**: `ecomm-payment`，**target**: `channel-primary`，**state**: `half-open`",
                "medium",
            ),
            Remediation("restart_pods", "**service**: `ecomm-payment`，**strategy**: `rolling`", "medium"),
        ],
        verification=["熔断关闭。", "支付恢复。"],
        forbidden=["**不要**仅加长 timeout（熔断已 open）。"],
    ),
    RunbookSpec(
        stem="ecomm-payment-settlement-reconcile-fail",
        service="ecomm-payment",
        title="电商支付结算对账不平",
        excludes=["渠道超时", "熔断"],
        symptoms=[
            "结算 job 失败告警。",
            "日志：`reconcile mismatch`、`settlement delta non-zero`。",
        ],
        diagnosis=["对账不平日志。", "支付通道调用正常。"],
        root_cause="批次结算文件与渠道账单不一致。",
        remediation=[
            Remediation(
                "purge_dead_letter_queue",
                "**service**: `ecomm-payment`，**queue**: `settlement-retry`",
                "medium",
            ),
        ],
        verification=["对账 job 成功。", "delta 归零。"],
        forbidden=["**不要** `restart_pods` 作为首选。"],
    ),
    RunbookSpec(
        stem="ecomm-payment-idempotency-collision",
        service="ecomm-payment",
        title="电商支付幂等键冲突风暴",
        excludes=["渠道超时", "熔断"],
        symptoms=[
            "重复支付拒绝激增。",
            "日志：`idempotency key collision`、`duplicate payment rejected`。",
        ],
        diagnosis=["幂等冲突日志。", "渠道正常。"],
        root_cause="客户端重试未更换幂等键。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-payment`，**config_key**: `idempotency.ttl-sec`，**config_value**: `86400`",
                "low",
            ),
        ],
        verification=["冲突率下降。", "支付成功恢复。"],
        forbidden=["**不要** `enable_circuit_breaker`。"],
    ),
    # --- ecomm-gateway (4) ---
    RunbookSpec(
        stem="ecomm-gateway-upstream-timeout",
        service="ecomm-gateway",
        title="电商网关上游服务超时",
        excludes=["502 坏网关", "CORS 风暴", "鉴权拦截"],
        symptoms=[
            "网关 504 增多。",
            "日志：`upstream timed out`、`504 Gateway Timeout`。",
        ],
        diagnosis=["504/upstream timeout。", "上游 pod 可能健康。"],
        root_cause="上游响应超过网关 proxy timeout。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-gateway`，**config_key**: `proxy.read-timeout-ms`，**config_value**: `10000`",
                "low",
            ),
        ],
        verification=["504 下降。", "路由成功。"],
        forbidden=["**不要** `restart_pods` 网关而不调 timeout。"],
    ),
    RunbookSpec(
        stem="ecomm-gateway-502-bad-gateway",
        service="ecomm-gateway",
        title="电商网关上游连接拒绝 502",
        excludes=["上游慢超时", "CORS"],
        symptoms=[
            "502 Bad Gateway 激增。",
            "日志：`connection refused`、`no healthy upstream`。",
        ],
        diagnosis=["connection refused / no healthy upstream。", "非 read timeout。"],
        root_cause="上游实例全不可用或 service endpoints 空。",
        remediation=[
            Remediation("scale_replicas", "**service**: `ecomm-gateway`，**replicas**: `3`", "low"),
            Remediation(
                "patch_config",
                "**service**: `ecomm-gateway`，**config_key**: `loadbalancer.health-check-interval-sec`，**config_value**: `5`",
                "low",
            ),
        ],
        verification=["502 消失。", "upstream 健康。"],
        forbidden=["**不要**仅加长 read-timeout（连接被拒绝）。"],
    ),
    RunbookSpec(
        stem="ecomm-gateway-auth-filter-block",
        service="ecomm-gateway",
        title="电商网关鉴权过滤器误拦截",
        excludes=["502", "CORS preflight"],
        symptoms=[
            "合法请求 401/403 激增。",
            "日志：`auth filter rejected`、`invalid token signature`。",
        ],
        diagnosis=["auth filter 拒绝。", "上游未收到请求。"],
        root_cause="鉴权配置或 JWKS 缓存过期。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-gateway`，**config_key**: `auth.jwks-cache-ttl-sec`，**config_value**: `300`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-gateway`，**strategy**: `rolling`", "low"),
        ],
        verification=["401/403 恢复正常。", "合法流量通过。"],
        forbidden=["**不要** `patch_config` proxy timeout。"],
    ),
    RunbookSpec(
        stem="ecomm-gateway-cors-preflight-storm",
        service="ecomm-gateway",
        title="电商网关 CORS 预检风暴",
        excludes=["502", "鉴权误拦"],
        symptoms=[
            "OPTIONS 流量打满，业务 GET/POST 下降。",
            "日志：`CORS preflight storm`、`OPTIONS flood`。",
        ],
        diagnosis=["OPTIONS 风暴。", "非 upstream timeout。"],
        root_cause="浏览器预检缓存失效或错误 CORS 配置。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-gateway`，**config_key**: `cors.max-age-sec`，**config_value**: `3600`",
                "low",
            ),
        ],
        verification=["OPTIONS QPS 下降。", "业务 QPS 恢复。"],
        forbidden=["**不要** `scale_replicas` 而不修 CORS。"],
    ),
    # --- ecomm-auth (3) ---
    RunbookSpec(
        stem="ecomm-auth-jwt-secret-mismatch",
        service="ecomm-auth",
        title="电商认证服务 JWT 密钥不一致",
        excludes=["Redis session 故障", "暴力破解锁号"],
        symptoms=[
            "全站登录失败。",
            "日志：`JWT signature does not match`、`invalid signature`。",
        ],
        diagnosis=["JWT signature 错误。", "session store 正常。"],
        root_cause="签发与验签密钥 rotation 不一致。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-auth`，**config_key**: `jwt.signing-key-version`，**config_value**: `v3`",
                "medium",
            ),
            Remediation("restart_pods", "**service**: `ecomm-auth`，**strategy**: `rolling`", "medium"),
        ],
        verification=["登录成功率恢复。"],
        forbidden=["**不要** `flush_cache` session 作为首选。"],
    ),
    RunbookSpec(
        stem="ecomm-auth-session-redis-down",
        service="ecomm-auth",
        title="电商认证 Session Redis 不可用",
        excludes=["JWT 密钥问题", "暴力破解"],
        symptoms=[
            "登录后立即掉线。",
            "日志：`session redis connection refused`、`NOAUTH`。",
        ],
        diagnosis=["Redis session 错误。", "JWT 签发可能成功。"],
        root_cause="Session Redis 宕机或密码轮换。",
        remediation=[
            Remediation("restart_pods", "**service**: `ecomm-auth`，**strategy**: `rolling`", "medium"),
            Remediation("flush_cache", "**service**: `ecomm-auth`，**scope**: `session`", "low"),
        ],
        verification=["会话保持正常。"],
        forbidden=["**不要** `patch_config` jwt key（非 JWT 根因）。"],
    ),
    RunbookSpec(
        stem="ecomm-auth-login-brute-force",
        service="ecomm-auth",
        title="电商认证暴力破解锁号风暴",
        excludes=["JWT 密钥", "Redis 宕机"],
        symptoms=[
            "登录 QPS 极高，大量 lockout。",
            "日志：`brute force detected`、`account locked`。",
        ],
        diagnosis=["暴力破解/锁号日志。", "基础设施正常。"],
        root_cause="恶意登录尝试触发全站锁号策略。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-auth`，**config_key**: `login.rate-limit-per-ip`，**config_value**: `30`",
                "low",
            ),
            Remediation(
                "enable_circuit_breaker",
                "**service**: `ecomm-auth`，**target**: `login-api`",
                "medium",
            ),
        ],
        verification=["锁号率下降。", "正常用户可登录。"],
        forbidden=["**不要** `restart_pods` 作为唯一手段。"],
    ),
    # --- ecomm-inventory (3) ---
    RunbookSpec(
        stem="ecomm-inventory-oversell-race",
        service="ecomm-inventory",
        title="电商库存超卖竞态",
        excludes=["同步 lag", "预占泄漏"],
        symptoms=[
            "库存为负或超卖告警。",
            "日志：`oversell detected`、`negative stock`。",
        ],
        diagnosis=["超卖日志。", "非 sync lag。"],
        root_cause="并发扣减竞态条件。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-inventory`，**config_key**: `stock.optimistic-lock-retry`，**config_value**: `5`",
                "low",
            ),
            Remediation("restart_pods", "**service**: `ecomm-inventory`，**strategy**: `rolling`", "medium"),
        ],
        verification=["负库存消失。", "扣减成功。"],
        forbidden=["**不要** `purge_dead_letter_queue`（非 MQ 根因）。"],
    ),
    RunbookSpec(
        stem="ecomm-inventory-sync-lag",
        service="ecomm-inventory",
        title="电商库存同步延迟",
        excludes=["超卖竞态", "预占泄漏"],
        symptoms=[
            "各渠道库存不一致。",
            "日志：`inventory sync lag`、`warehouse delta pending`。",
        ],
        diagnosis=["sync lag 日志。", "无 negative stock。"],
        root_cause="仓配同步 worker 堆积。",
        remediation=[
            Remediation("scale_replicas", "**service**: `ecomm-inventory`，**replicas**: `4`", "medium"),
            Remediation(
                "purge_dead_letter_queue",
                "**service**: `ecomm-inventory`，**queue**: `sync-retry`",
                "medium",
            ),
        ],
        verification=["lag 指标正常。", "渠道库存一致。"],
        forbidden=["**不要**改 optimistic-lock（非竞态根因）。"],
    ),
    RunbookSpec(
        stem="ecomm-inventory-reservation-leak",
        service="ecomm-inventory",
        title="电商库存预占泄漏",
        excludes=["超卖", "同步 lag"],
        symptoms=[
            "可售库存长期偏低。",
            "日志：`reservation leak`、`unreleased hold`。",
        ],
        diagnosis=["预占未释放。", "无 oversell。"],
        root_cause="订单取消未释放预占。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-inventory`，**config_key**: `reservation.ttl-sec`，**config_value**: `900`",
                "low",
            ),
            Remediation(
                "purge_dead_letter_queue",
                "**service**: `ecomm-inventory`，**queue**: `reservation-cleanup`",
                "low",
            ),
        ],
        verification=["可售库存恢复。", "hold 数量下降。"],
        forbidden=["**不要** `scale_replicas`  alone。"],
    ),
    # --- ecomm-notification (3) ---
    RunbookSpec(
        stem="ecomm-notification-email-smtp-fail",
        service="ecomm-notification",
        title="电商通知邮件 SMTP 失败",
        excludes=["webhook 积压", "推送厂商故障"],
        symptoms=[
            "邮件通知失败率 100%。",
            "日志：`SMTP connect failed`、`535 authentication failed`。",
        ],
        diagnosis=["SMTP 错误。", "webhook 正常。"],
        root_cause="SMTP 凭证过期或端口被封。",
        remediation=[
            Remediation(
                "patch_config",
                "**service**: `ecomm-notification`，**config_key**: `smtp.relay-host`，**config_value**: `smtp-backup.internal`",
                "low",
            ),
        ],
        verification=["邮件发送成功。"],
        forbidden=["**不要** `purge_dead_letter_queue` 而不换 relay。"],
    ),
    RunbookSpec(
        stem="ecomm-notification-webhook-retry-storm",
        service="ecomm-notification",
        title="电商通知 Webhook 重试风暴",
        excludes=["SMTP 故障", "推送 down"],
        symptoms=[
            "MQ 积压，webhook 延迟。",
            "日志：`webhook retry storm`、`DLQ growing`。",
        ],
        diagnosis=["webhook retry/DLQ。", "SMTP 正常。"],
        root_cause="下游 webhook 5xx 导致无限重试。",
        remediation=[
            Remediation(
                "purge_dead_letter_queue",
                "**service**: `ecomm-notification`，**queue**: `webhook-dlq`",
                "medium",
            ),
            Remediation(
                "patch_config",
                "**service**: `ecomm-notification`，**config_key**: `webhook.max-retries`，**config_value**: `5`",
                "low",
            ),
        ],
        verification=["DLQ 清空。", "投递延迟恢复。"],
        forbidden=["**不要** `patch_config` smtp。"],
    ),
    RunbookSpec(
        stem="ecomm-notification-push-provider-down",
        service="ecomm-notification",
        title="电商通知推送厂商不可用",
        excludes=["SMTP", "webhook"],
        symptoms=[
            "App push 全失败。",
            "日志：`push provider 503`、`FCM unavailable`。",
        ],
        diagnosis=["push provider 错误。", "邮件/webhook 正常。"],
        root_cause="第三方推送服务故障。",
        remediation=[
            Remediation(
                "enable_circuit_breaker",
                "**service**: `ecomm-notification`，**target**: `push-provider`",
                "medium",
            ),
            Remediation(
                "patch_config",
                "**service**: `ecomm-notification`，**config_key**: `push.fallback-channel`，**config_value**: `sms`",
                "low",
            ),
        ],
        verification=["推送或 fallback 恢复。"],
        forbidden=["**不要** `purge_dead_letter_queue` webhook 队列。"],
    ),
]

assert len(RUNBOOK_SPECS) == 38, len(RUNBOOK_SPECS)
