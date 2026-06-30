package com.example.opsbackend.seed;

import com.example.opsbackend.model.K8sEvent;
import com.example.opsbackend.model.K8sEventResult;
import com.example.opsbackend.model.LogEntry;
import com.example.opsbackend.model.LogQueryRequest;
import com.example.opsbackend.model.LogQueryResult;
import com.example.opsbackend.model.MetricPoint;
import com.example.opsbackend.model.MetricSeries;
import com.example.opsbackend.model.OperationResult;
import com.example.opsbackend.model.PodStatus;
import com.example.opsbackend.model.ServiceStatus;
import com.example.opsbackend.model.StreamState;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
public class SeedData {

    private static final Instant NOW = Instant.parse("2026-06-04T07:00:00Z");

    public LogQueryResult queryLogs(LogQueryRequest req) {
        List<LogEntry> entries = switch (req.service()) {
            case "lts-access" -> ltsAccessLogs();
            case "bcs-agent" -> bcsAgentLogs();
            case "lts-config" -> ltsConfigLogs();
            default -> List.of();
        };
        List<LogEntry> filtered = new ArrayList<>();
        for (LogEntry e : entries) {
            if (req.keyword() == null || req.keyword().isBlank()
                    || e.message().toLowerCase().contains(req.keyword().toLowerCase())) {
                filtered.add(e);
            }
        }
        int limit = Math.min(req.limit(), filtered.size());
        return new LogQueryResult(req, filtered.size(), filtered.subList(0, limit));
    }

    public ServiceStatus serviceStatus(String service) {
        return switch (service) {
            case "lts-access" -> new ServiceStatus(
                    "lts-access", true, 3, 3,
                    List.of(
                            pod("lts-access", 0, true, "Running", "registry/lts-access:2.4.1"),
                            pod("lts-access", 1, true, "Running", "registry/lts-access:2.4.1"),
                            pod("lts-access", 2, true, "Running", "registry/lts-access:2.4.1")),
                    "Service up but ingest QPS degraded due to rate limit misconfiguration");
            case "bcs-agent" -> new ServiceStatus(
                    "bcs-agent", false, 0, 3,
                    List.of(
                            pod("bcs-agent", 0, false, "CrashLoopBackOff", "registry/bcs-agent:9.9.9-bad"),
                            pod("bcs-agent", 1, false, "CrashLoopBackOff", "registry/bcs-agent:9.9.9-bad"),
                            pod("bcs-agent", 2, false, "CrashLoopBackOff", "registry/bcs-agent:9.9.9-bad")),
                    "All replicas failing after bad image upgrade");
            case "lts-config" -> new ServiceStatus(
                    "lts-config", true, 2, 2,
                    List.of(
                            pod("lts-config", 0, true, "Running", "registry/lts-config:1.8.0"),
                            pod("lts-config", 1, true, "Running", "registry/lts-config:1.8.0")),
                    "Control plane healthy; one stream paused causing zero ingest");
            default -> throw new IllegalArgumentException("unknown service: " + service);
        };
    }

    public List<StreamState> streamStates(String service) {
        if (!"lts-config".equals(service)) {
            return List.of();
        }
        return List.of(
                new StreamState("proj-a", "stream-ingest", "RUNNING", "kafka-proj-a-ingest", NOW.minusSeconds(30)),
                new StreamState("proj-b", "stream-audit", "PAUSED", "kafka-proj-b-audit", NOW.minusSeconds(6 * 3600)));
    }

    public MetricSeries metrics(String service) {
        return switch (service) {
            case "lts-access" -> new MetricSeries(
                    "lts-access", "ingest_qps", "req/s",
                    List.of(
                            point(NOW.minusSeconds(600), 12000),
                            point(NOW.minusSeconds(300), 800),
                            point(NOW, 750)));
            case "bcs-agent" -> new MetricSeries(
                    "bcs-agent", "ready_replicas", "count",
                    List.of(
                            point(NOW.minusSeconds(900), 3),
                            point(NOW.minusSeconds(300), 0),
                            point(NOW, 0)));
            case "lts-config" -> new MetricSeries(
                    "lts-config", "ingest_bytes_per_sec", "bytes/s",
                    List.of(
                            point(NOW.minusSeconds(7200), 5000000),
                            point(NOW.minusSeconds(3600), 0),
                            point(NOW, 0)));
            default -> throw new IllegalArgumentException("unknown service: " + service);
        };
    }

    public OperationResult latestOperation(String service) {
        if ("bcs-agent".equals(service)) {
            return new OperationResult(
                    "op-7788",
                    service,
                    "upgrade",
                    "SUCCEEDED",
                    "Deployed bcs-agent:9.9.9-bad (bad release)",
                    NOW.minusSeconds(600),
                    NOW.minusSeconds(540));
        }
        return new OperationResult(
                "op-none",
                service,
                "none",
                "SUCCEEDED",
                "No recent operation",
                NOW.minusSeconds(86400),
                NOW.minusSeconds(86400));
    }

    public OperationResult executeOps(String action, com.example.opsbackend.model.OpsRequest request) {
        String service = request.service();
        String message = switch (action) {
            case "rollback_deployment" -> {
                String version = request.targetVersion() != null ? request.targetVersion() : "previous-stable";
                yield "Rolled back " + service + " to version " + version + ", ready replicas recovering";
            }
            case "scale_replicas" -> "Scaled " + service + " to " + request.replicas() + " replicas";
            case "restart_pods" -> {
                String strategy = request.strategy() != null ? request.strategy() : "rolling";
                yield "Restarted " + service + " pods with " + strategy + " strategy";
            }
            case "enable_circuit_breaker" ->
                    "Set circuit breaker on " + service + " upstream=" + request.upstream()
                            + " state=" + request.state();
            case "flush_cache" -> {
                String pattern = request.cacheKeyPattern() != null ? request.cacheKeyPattern() : "*";
                yield "Flushed cache keys matching " + pattern + " for " + service;
            }
            case "purge_dead_letter_queue" ->
                    "Purged dead-letter queue " + request.queueName() + " for " + service;
            case "patch_config" ->
                    "Patched " + service + " " + request.configKey() + "=" + request.configValue();
            case "toggle_feature_flag" ->
                    "Set feature flag " + request.flagName() + "="
                            + (Boolean.TRUE.equals(request.enabled()) ? "enabled" : "disabled")
                            + " on " + service;
            case "resume_event_stream" ->
                    "Resumed stream " + request.streamId() + " on " + service + ", consumer lag draining";
            case "cleanup_storage" -> {
                String path = request.path() != null ? request.path() : "/var/log";
                int days = request.retentionDays() != null ? request.retentionDays() : 7;
                yield "Cleaned storage under " + path + " older than " + days + "d for " + service;
            }
            default -> throw new IllegalArgumentException("unknown ops action: " + action);
        };
        return new OperationResult(
                "op-" + action + "-" + System.currentTimeMillis(),
                service,
                action,
                "SUCCEEDED",
                message,
                NOW,
                NOW);
    }

    private PodStatus pod(String prefix, int idx, boolean ready, String phase, String image) {
        return new PodStatus(
                prefix + "-" + idx,
                ready,
                ready ? 0 : 12 + idx,
                phase,
                image,
                ready ? null : phase);
    }

    private MetricPoint point(Instant ts, double value) {
        return new MetricPoint(ts, value);
    }

    private List<LogEntry> ltsAccessLogs() {
        return List.of(
                new LogEntry(
                        NOW.minusSeconds(300),
                        "WARN",
                        "rate limit exceeded, forwarding batch to retry-topic lts-retry",
                        "lts-access",
                        "proj-a/stream-ingest",
                        Map.of("topic", "lts-retry", "cost", 120, "threshold", 50)),
                new LogEntry(
                        NOW.minusSeconds(240),
                        "INFO",
                        "ingest qps dropped from 12000 to 800 after limiter config reload",
                        "lts-access",
                        null,
                        Map.of("qps_before", 12000, "qps_after", 800)),
                new LogEntry(
                        NOW.minusSeconds(180),
                        "ERROR",
                        "RateLimitService: threshold misconfigured method-cost=50 expected=500",
                        "lts-access"));
    }

    private List<LogEntry> bcsAgentLogs() {
        // True application-level logs from the bcs-agent process before it crashed.
        // K8s infrastructure events (CrashLoop, probe failures) are returned separately via k8sEvents().
        return List.of(
                new LogEntry(
                        NOW.minusSeconds(540),
                        "ERROR",
                        "Failed to initialize fabric gateway client: connection timeout to orderer",
                        "bcs-agent"),
                new LogEntry(
                        NOW.minusSeconds(538),
                        "FATAL",
                        "Application startup failed: fabric gateway unavailable, aborting",
                        "bcs-agent"),
                new LogEntry(
                        NOW.minusSeconds(530),
                        "ERROR",
                        "Health check server failed to start on :8080: address already in use",
                        "bcs-agent"));
    }

    public K8sEventResult k8sEvents(String service) {
        return switch (service) {
            case "bcs-agent" -> new K8sEventResult("bcs-agent", 4, List.of(
                    new K8sEvent(NOW.minusSeconds(480), "Warning", "BackOff",
                            "pod/bcs-agent-0",
                            "Back-off restarting failed container bcs-agent in pod bcs-agent-0",
                            "bcs-agent"),
                    new K8sEvent(NOW.minusSeconds(450), "Warning", "BackOff",
                            "pod/bcs-agent-1",
                            "Back-off restarting failed container bcs-agent in pod bcs-agent-1",
                            "bcs-agent"),
                    new K8sEvent(NOW.minusSeconds(420), "Warning", "Failed",
                            "pod/bcs-agent-0",
                            "Error: failed to create containerd task: container exited immediately",
                            "bcs-agent"),
                    new K8sEvent(NOW.minusSeconds(360), "Warning", "Unhealthy",
                            "pod/bcs-agent-2",
                            "Readiness probe failed: Get http://10.0.0.5:8080/healthz: connection refused",
                            "bcs-agent")
            ));
            // lts-access and lts-config are healthy at infra level; no significant K8s events
            default -> new K8sEventResult(service, 0, List.of());
        };
    }

    private List<LogEntry> ltsConfigLogs() {
        return List.of(
                new LogEntry(
                        NOW.minusSeconds(3600),
                        "INFO",
                        "stream proj-b/stream-audit paused by operator user=ops-admin",
                        "lts-config",
                        "proj-b/stream-audit",
                        Map.of()),
                new LogEntry(
                        NOW.minusSeconds(1200),
                        "WARN",
                        "no ingest heartbeat for stream proj-b/stream-audit in 360min",
                        "lts-config"));
    }
}
