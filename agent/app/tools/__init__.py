from app.tools.log_tools import query_app_logs, query_k8s_events
from app.tools.metric_tools import get_metrics
from app.tools.ops_tools import (
    cordon_node,
    delete_pod,
    drain_node,
    enable_circuit_breaker,
    flush_cache,
    patch_config,
    restart_deployment,
    rollback_deployment,
    scale_deployment,
    toggle_feature_flag,
)
from app.tools.runbook_tools import search_runbook
from app.tools.status_tools import get_latest_operation, get_service_status, get_stream_states

READ_TOOLS = [
    query_app_logs,
    query_k8s_events,
    get_service_status,
    get_stream_states,
    get_metrics,
    get_latest_operation,
    search_runbook,
]
WRITE_TOOLS = [
    rollback_deployment,
    scale_deployment,
    restart_deployment,
    delete_pod,
    cordon_node,
    drain_node,
    patch_config,
    enable_circuit_breaker,
    toggle_feature_flag,
    flush_cache,
]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
