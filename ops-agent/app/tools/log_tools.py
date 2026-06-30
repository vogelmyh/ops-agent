from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.adapters.backend_client import get_backend_client
from app.schemas import LogQueryRequest, LogQueryResult


class QueryAppLogsInput(BaseModel):
    service: str = Field(description="Service name, e.g. ecomm-manager")
    keyword: str | None = Field(default=None, description="Optional keyword filter")
    limit: int = Field(default=20, ge=1, le=200)


class QueryK8sEventsInput(BaseModel):
    service: str = Field(description="Service name, e.g. ecomm-order")


@tool(args_schema=QueryAppLogsInput)
def query_app_logs(service: str, keyword: str | None = None, limit: int = 20) -> dict:
    """Query application logs from the log platform (stdout/stderr of service processes).
    Use this to understand business-level errors, config issues, and runtime behaviour."""
    client = get_backend_client()
    req = LogQueryRequest(service=service, keyword=keyword, limit=limit)
    result: LogQueryResult = client.query_app_logs(req)
    return result.model_dump(mode="json")


@tool(args_schema=QueryK8sEventsInput)
def query_k8s_events(service: str) -> dict:
    """Query K8s infrastructure events from the K8s API (kubelet/scheduler/controller).
    Use this to understand CrashLoop, probe failures, scheduling issues, and container lifecycle events."""
    client = get_backend_client()
    result = client.query_k8s_events(service)
    return result.model_dump(mode="json")
