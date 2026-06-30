from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.adapters.backend_client import get_backend_client


class ServiceInput(BaseModel):
    service: str = Field(description="Service name")


@tool(args_schema=ServiceInput)
def get_service_status(service: str) -> dict:
    """Get deployment health and pod status for a service."""
    client = get_backend_client()
    return client.get_service_status(service).model_dump(mode="json")


@tool(args_schema=ServiceInput)
def get_stream_states(service: str) -> list:
    """List event stream states (RUNNING/PAUSED) for ecomm-order related flows."""
    client = get_backend_client()
    return [s.model_dump(mode="json") for s in client.get_stream_states(service)]


@tool(args_schema=ServiceInput)
def get_latest_operation(service: str) -> dict:
    """Get the latest dataplane operation (upgrade/rollback) for a service."""
    client = get_backend_client()
    return client.get_latest_operation(service).model_dump(mode="json")
