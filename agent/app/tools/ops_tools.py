from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.adapters.backend_client import get_backend_client
from app.audit.audit_log import record_audit
from app.config import get_settings


class ServiceInput(BaseModel):
    service: str = Field(description="Target K8s workload / microservice name")


class RollbackDeploymentInput(ServiceInput):
    target_version: str | None = Field(
        default=None,
        description="Image tag or release version to roll back to; defaults to previous stable",
    )


class ScaleReplicasInput(ServiceInput):
    replicas: int = Field(ge=0, description="Desired ready replica count")


class RestartPodsInput(ServiceInput):
    strategy: Literal["rolling", "all"] = Field(
        default="rolling",
        description="Pod restart strategy: rolling (default) or all at once",
    )


class CircuitBreakerInput(ServiceInput):
    upstream: str = Field(description="Upstream dependency or route to break")
    state: Literal["open", "closed"] = Field(description="Circuit breaker state")


class FlushCacheInput(ServiceInput):
    cache_key_pattern: str = Field(
        default="*",
        description="Cache key pattern to flush; * clears all keys for the service",
    )


class PurgeDeadLetterQueueInput(ServiceInput):
    queue_name: str = Field(description="Dead-letter queue name to purge")


class PatchConfigInput(ServiceInput):
    config_key: str = Field(description="Configuration key path, e.g. rate-limit.threshold")
    config_value: str = Field(description="New configuration value")


class ToggleFeatureFlagInput(ServiceInput):
    flag_name: str = Field(description="Feature flag identifier")
    enabled: bool = Field(description="Whether to enable the flag")


class ResumeEventStreamInput(ServiceInput):
    stream_id: str = Field(description="Event or stream identifier to resume")


class CleanupStorageInput(ServiceInput):
    path: str = Field(default="/var/log", description="Storage path to clean on pod or node")
    retention_days: int = Field(default=7, ge=1, description="Delete data older than N days")


def _run_ops_action(
    *,
    action: str,
    service: str,
    body: dict,
    mock_message: str,
    audit_action: str | None = None,
) -> dict:
    settings = get_settings()
    audit_name = audit_action or action
    if settings.backend_is_mock:
        payload = {
            "service": service,
            "status": "SUCCEEDED",
            "message": mock_message,
            **body,
        }
    else:
        client = get_backend_client()
        result = client.execute_ops_action(action, service, body)
        payload = result.model_dump(mode="json")
        for key, value in body.items():
            payload.setdefault(key, value)
    record_audit(audit_name, service, payload)
    return payload


@tool(args_schema=RollbackDeploymentInput)
def rollback_deployment(service: str, target_version: str | None = None) -> dict:
    """Roll back a deployment to a previous stable version after a bad release."""
    version = target_version or "previous-stable"
    return _run_ops_action(
        action="rollback_deployment",
        service=service,
        body={"target_version": target_version},
        mock_message=(
            f"Mock rollback: restored {service} to version {version}, "
            "ready replicas recovering"
        ),
    )


@tool(args_schema=ScaleReplicasInput)
def scale_replicas(service: str, replicas: int) -> dict:
    """Scale deployment replica count up or down to handle traffic or resource pressure."""
    return _run_ops_action(
        action="scale_replicas",
        service=service,
        body={"replicas": replicas},
        mock_message=f"Mock scale: {service} scaled to {replicas} replicas",
    )


@tool(args_schema=RestartPodsInput)
def restart_pods(service: str, strategy: Literal["rolling", "all"] = "rolling") -> dict:
    """Restart pods without changing the deployment version (e.g. memory leak, stale connections)."""
    return _run_ops_action(
        action="restart_pods",
        service=service,
        body={"strategy": strategy},
        mock_message=(
            f"Mock restart: {service} pods restarted with {strategy} strategy, "
            "workload recovering"
        ),
    )


@tool(args_schema=CircuitBreakerInput)
def enable_circuit_breaker(service: str, upstream: str, state: Literal["open", "closed"]) -> dict:
    """Open or close a circuit breaker on an upstream dependency to stop cascading failures."""
    return _run_ops_action(
        action="enable_circuit_breaker",
        service=service,
        body={"upstream": upstream, "state": state},
        mock_message=(
            f"Mock circuit breaker: {service} upstream={upstream} set to {state}"
        ),
    )


@tool(args_schema=FlushCacheInput)
def flush_cache(service: str, cache_key_pattern: str = "*") -> dict:
    """Flush stale or poisoned cache entries for a service."""
    return _run_ops_action(
        action="flush_cache",
        service=service,
        body={"cache_key_pattern": cache_key_pattern},
        mock_message=(
            f"Mock cache flush: cleared keys matching {cache_key_pattern!r} for {service}"
        ),
    )


@tool(args_schema=PurgeDeadLetterQueueInput)
def purge_dead_letter_queue(service: str, queue_name: str) -> dict:
    """Purge a dead-letter queue that is blocking downstream consumption."""
    return _run_ops_action(
        action="purge_dead_letter_queue",
        service=service,
        body={"queue_name": queue_name},
        mock_message=(
            f"Mock DLQ purge: cleared queue {queue_name!r} for {service}"
        ),
    )


@tool(args_schema=PatchConfigInput)
def patch_config(service: str, config_key: str, config_value: str) -> dict:
    """Patch a runtime configuration value (thresholds, limits, env-style settings)."""
    return _run_ops_action(
        action="patch_config",
        service=service,
        body={"config_key": config_key, "config_value": config_value},
        mock_message=(
            f"Mock config patch: {service} {config_key}={config_value!r}, "
            "workload applying new settings"
        ),
    )


@tool(args_schema=ToggleFeatureFlagInput)
def toggle_feature_flag(service: str, flag_name: str, enabled: bool) -> dict:
    """Enable or disable a feature flag to mitigate a bad rollout or restore stable behavior."""
    state = "enabled" if enabled else "disabled"
    return _run_ops_action(
        action="toggle_feature_flag",
        service=service,
        body={"flag_name": flag_name, "enabled": enabled},
        mock_message=f"Mock feature flag: {service} {flag_name} {state}",
    )


@tool(args_schema=ResumeEventStreamInput)
def resume_event_stream(service: str, stream_id: str) -> dict:
    """Resume a paused event or message stream so consumers can catch up."""
    return _run_ops_action(
        action="resume_event_stream",
        service=service,
        body={"stream_id": stream_id},
        mock_message=(
            f"Mock stream resume: {service} stream {stream_id!r} is RUNNING, "
            "consumer lag draining"
        ),
    )


@tool(args_schema=CleanupStorageInput)
def cleanup_storage(
    service: str,
    path: str = "/var/log",
    retention_days: int = 7,
) -> dict:
    """Clean old logs or temporary files to free disk space on a pod or node."""
    return _run_ops_action(
        action="cleanup_storage",
        service=service,
        body={"path": path, "retention_days": retention_days},
        mock_message=(
            f"Mock cleanup: removed data under {path} older than {retention_days}d "
            f"for {service}, disk usage dropped from 99% to ~45%"
        ),
    )
