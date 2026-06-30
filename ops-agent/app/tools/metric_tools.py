from langchain_core.tools import tool

from app.tools.status_tools import ServiceInput
from app.adapters.backend_client import get_backend_client


@tool(args_schema=ServiceInput)
def get_metrics(service: str) -> dict:
    """Get key metric time series for a service."""
    client = get_backend_client()
    return client.get_metrics(service).model_dump(mode="json")
