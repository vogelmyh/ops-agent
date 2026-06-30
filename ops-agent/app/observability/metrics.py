from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "ops_agent_http_requests_total",
    "HTTP requests",
    ["method", "endpoint", "status"],
)
RUN_LATENCY = Histogram(
    "ops_agent_run_duration_seconds",
    "Agent run duration",
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
