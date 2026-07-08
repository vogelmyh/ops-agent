from app.tools.log_tools import query_app_logs, query_k8s_events
from app.tools.metric_tools import get_metrics
from app.tools.ops_tools import (
    cleanup_storage,
    enable_circuit_breaker,
    flush_cache,
    patch_config,
    purge_dead_letter_queue,
    restart_pods,
    resume_event_stream,
    rollback_deployment,
    scale_replicas,
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
    scale_replicas,
    restart_pods,
    enable_circuit_breaker,
    flush_cache,
    purge_dead_letter_queue,
    patch_config,
    toggle_feature_flag,
    resume_event_stream,
    cleanup_storage,
]
ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
