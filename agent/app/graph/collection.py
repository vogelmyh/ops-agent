"""Shared data collection and RAG retrieval helpers for graph nodes."""

from __future__ import annotations

from typing import Any

from app.adapters.backend_client import get_backend_client
from app.config import Settings, get_settings
from app.graph.eval_schemas import RunbookCandidate
from app.graph.runbook_eval_policy import candidates_from_retrieval_dicts
from app.schemas import LogQueryRequest, StreamStatus

KNOWN_SERVICES = frozenset({"ecomm-manager", "ecomm-order"})


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def collect(service: str) -> dict:
    """Pull data from all available sources for the given service."""
    client = get_backend_client()
    data: dict = {}

    data["app_logs"] = client.query_app_logs(LogQueryRequest(service=service, limit=10))
    data["k8s_events"] = client.query_k8s_events(service)
    data["status"] = client.get_service_status(service)
    data["metrics"] = client.get_metrics(service)

    if service in ("ecomm-manager", "ecomm-order"):
        data["streams"] = client.get_stream_states(service)
        data["operation"] = client.get_latest_operation(service)

    return data


def serialize_collected(data: dict) -> dict:
    """Convert Pydantic models in collected data to JSON-serializable dicts."""
    out: dict = {}
    for key, value in data.items():
        if hasattr(value, "model_dump"):
            out[key] = value.model_dump(mode="json")
        elif isinstance(value, list) and value and hasattr(value[0], "model_dump"):
            out[key] = [item.model_dump(mode="json") for item in value]
        else:
            out[key] = value
    return out


def extract_symptoms(
    service: str,
    data: dict,
    *,
    incident_description: str = "",
) -> str:
    """Build a symptom-rich query string from incident text and collected telemetry."""
    parts = [service]

    description = incident_description.strip()
    if description:
        parts.append(description[:200])

    status = data.get("status")
    if status:
        ready = _field(status, "replicas_ready")
        desired = _field(status, "replicas_desired")
        healthy = _field(status, "healthy")
        message = _field(status, "message", "")
        if ready is not None and desired is not None:
            parts.append(f"{ready}/{desired} ready healthy={healthy}")
        if message:
            parts.append(str(message)[:120])
        for pod in (_field(status, "pods") or [])[:3]:
            name = _field(pod, "name", "")
            restarts = _field(pod, "restarts")
            reason = _field(pod, "reason") or _field(pod, "phase")
            image = _field(pod, "image", "")
            pod_bits = [bit for bit in (name, f"restarts={restarts}" if restarts is not None else None, reason, image) if bit]
            if pod_bits:
                parts.append("pod " + " ".join(str(bit) for bit in pod_bits))

    app_logs = data.get("app_logs")
    if app_logs:
        entries = _field(app_logs, "entries") or []
        for entry in entries:
            level = _field(entry, "level")
            message = _field(entry, "message", "")
            if level in ("ERROR", "FATAL", "WARN"):
                parts.append(str(message)[:120])
                break

    k8s = data.get("k8s_events")
    if k8s:
        events = _field(k8s, "events") or []
        if events:
            first = events[0]
            reason = _field(first, "reason")
            message = _field(first, "message", "")
            parts.append(str(reason))
            parts.append(str(message)[:80])

    metrics = data.get("metrics")
    if metrics:
        points = _field(metrics, "points") or []
        metric_name = _field(metrics, "metric", "metric")
        if points:
            first_val = _field(points[0], "value")
            last_val = _field(points[-1], "value")
            if last_val == 0:
                parts.append(f"{metric_name} dropped to zero")
            elif first_val and last_val < first_val * 0.5:
                parts.append(f"{metric_name} degraded from {first_val} to {last_val}")

    streams = data.get("streams")
    if streams:
        for stream in streams:
            stream_status = _field(stream, "status")
            stream_name = _field(stream, "stream")
            if stream_status == StreamStatus.PAUSED or stream_status == "PAUSED":
                parts.append(f"stream {stream_name} paused no ingest")
                break

    op = data.get("operation")
    if op:
        action = _field(op, "action")
        op_message = _field(op, "message", "")
        if action and action != "none":
            parts.append(f"recent operation {action}")
        if op_message:
            parts.append(str(op_message)[:80])

    return " ".join(part for part in parts if part)


def retrieve_runbooks(service: str, symptom_query: str, settings: Settings | None = None) -> list[dict]:
    """Search for relevant runbook chunks, filter by score, expand to parent documents."""
    return [
        c.model_dump()
        for c in retrieve_runbook_candidates(service, symptom_query, settings)
    ]


def retrieve_runbook_candidates(
    service: str,
    symptom_query: str,
    settings: Settings | None = None,
) -> list[RunbookCandidate]:
    """Hybrid BM25 + vector → rerank → parent expand → top-3 candidates for eval."""
    settings = settings or get_settings()
    from app.rag.retrieval import retrieve_ranked_parent_chunks

    parents = retrieve_ranked_parent_chunks(
        symptom_query,
        service=service,
        settings=settings,
    )
    return candidates_from_retrieval_dicts(parents)
