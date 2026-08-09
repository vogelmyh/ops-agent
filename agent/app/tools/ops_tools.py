from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.adapters.backend_client import get_backend_client
from app.audit.audit_log import record_audit
from app.config import get_settings


class ServiceInput(BaseModel):
    service: str = Field(description="Target K8s workload / microservice name")


# ── K8s Infrastructure Layer ──────────────────────────────────────────────


class RollbackDeploymentInput(ServiceInput):
    target_version: str | None = Field(
        default=None,
        description="Image tag or release version to roll back to; defaults to previous stable",
    )


class ScaleDeploymentInput(ServiceInput):
    replicas: int = Field(ge=0, description="Desired ready replica count")


class RestartDeploymentInput(ServiceInput):
    strategy: Literal["rolling", "all"] = Field(
        default="rolling",
        description="Pod restart strategy: rolling (default) or all at once",
    )


class DeletePodInput(ServiceInput):
    pod_name: str = Field(description="Full pod name to delete (e.g. my-deploy-abc123)")
    grace_period_seconds: int = Field(
        default=30, ge=0, description="Grace period before force kill"
    )


class CordonNodeInput(ServiceInput):
    node_name: str = Field(description="K8s node name to mark unschedulable")


class DrainNodeInput(ServiceInput):
    node_name: str = Field(description="K8s node name to drain")
    force: bool = Field(
        default=False, description="Force evict even if PDB would block"
    )
    delete_emptydir: bool = Field(
        default=False, description="Delete pods that use emptyDir volumes"
    )


# ── Platform Layer ───────────────────────────────────────────────────────


class PatchConfigInput(ServiceInput):
    config_key: str = Field(
        description="Configuration key path, e.g. rate-limit.max-qps"
    )
    config_value: str = Field(description="New configuration value")


class CircuitBreakerInput(ServiceInput):
    upstream: str = Field(description="Upstream dependency or route to break")
    state: Literal["open", "closed"] = Field(description="Circuit breaker state")


class ToggleFeatureFlagInput(ServiceInput):
    flag_name: str = Field(description="Feature flag identifier")
    enabled: bool = Field(description="Whether to enable the flag")


class FlushCacheInput(ServiceInput):
    cache_key_pattern: str = Field(
        default="*",
        description="Cache key pattern to flush; * clears all keys for the service",
    )


# ── Shared execution helper ──────────────────────────────────────────────


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


# ── K8s Infrastructure Tools ──────────────────────────────────────────────


@tool(args_schema=RollbackDeploymentInput)
def rollback_deployment(service: str, target_version: str | None = None) -> dict:
    """Roll back a deployment to a previous stable version after a bad release (kubectl rollout undo)."""
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


@tool(args_schema=ScaleDeploymentInput)
def scale_deployment(service: str, replicas: int) -> dict:
    """Scale deployment replica count up or down to handle traffic or resource pressure (kubectl scale)."""
    return _run_ops_action(
        action="scale_deployment",
        service=service,
        body={"replicas": replicas},
        mock_message=f"Mock scale: {service} scaled to {replicas} replicas",
    )


@tool(args_schema=RestartDeploymentInput)
def restart_deployment(service: str, strategy: Literal["rolling", "all"] = "rolling") -> dict:
    """Restart a deployment without changing the image version (kubectl rollout restart)."""
    return _run_ops_action(
        action="restart_deployment",
        service=service,
        body={"strategy": strategy},
        mock_message=(
            f"Mock restart: {service} restarted with {strategy} strategy, "
            "workload recovering"
        ),
    )


@tool(args_schema=DeletePodInput)
def delete_pod(service: str, pod_name: str, grace_period_seconds: int = 30) -> dict:
    """Force-delete a specific pod by name (kubectl delete pod)."""
    return _run_ops_action(
        action="delete_pod",
        service=service,
        body={"pod_name": pod_name, "grace_period_seconds": grace_period_seconds},
        mock_message=(
            f"Mock pod delete: {pod_name} in {service} terminated "
            f"with {grace_period_seconds}s grace period"
        ),
    )


@tool(args_schema=CordonNodeInput)
def cordon_node(service: str, node_name: str) -> dict:
    """Mark a K8s node as unschedulable to prevent new pods from being assigned (kubectl cordon)."""
    return _run_ops_action(
        action="cordon_node",
        service=service,
        body={"node_name": node_name},
        mock_message=f"Mock cordon: node {node_name} marked unschedulable",
    )


@tool(args_schema=DrainNodeInput)
def drain_node(
    service: str, node_name: str, force: bool = False, delete_emptydir: bool = False
) -> dict:
    """Evict all pods from a node and cordon it for maintenance (kubectl drain)."""
    return _run_ops_action(
        action="drain_node",
        service=service,
        body={"node_name": node_name, "force": force, "delete_emptydir": delete_emptydir},
        mock_message=(
            f"Mock drain: node {node_name} cordoned and pods evicted"
            + (" (forced)" if force else "")
            + (" (emptydir deleted)" if delete_emptydir else "")
        ),
    )


# ── Platform Tools ───────────────────────────────────────────────────────


@tool(args_schema=PatchConfigInput)
def patch_config(service: str, config_key: str, config_value: str) -> dict:
    """Patch a runtime configuration value (ConfigMap, env var, or app config)."""
    return _run_ops_action(
        action="patch_config",
        service=service,
        body={"config_key": config_key, "config_value": config_value},
        mock_message=(
            f"Mock config patch: {service} {config_key}={config_value!r}, "
            "workload applying new settings"
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


@tool(args_schema=FlushCacheInput)
def flush_cache(service: str, cache_key_pattern: str = "*") -> dict:
    """Flush stale or poisoned cache entries for a service (Redis / KV cache)."""
    return _run_ops_action(
        action="flush_cache",
        service=service,
        body={"cache_key_pattern": cache_key_pattern},
        mock_message=(
            f"Mock cache flush: cleared keys matching {cache_key_pattern!r} for {service}"
        ),
    )
