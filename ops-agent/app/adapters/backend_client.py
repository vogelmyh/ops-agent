from functools import lru_cache
from typing import Any

import httpx

from app.adapters import mock_data
from app.config import Settings, get_settings
from app.schemas import (
    K8sEventResult,
    LogQueryRequest,
    LogQueryResult,
    MetricSeries,
    OperationResult,
    OperationStatus,
    ServiceStatus,
    StreamState,
)


class BackendClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http = httpx.Client(
            base_url=self.settings.backend_base_url.rstrip("/"),
            timeout=30.0,
        )

    def query_app_logs(self, req: LogQueryRequest) -> LogQueryResult:
        """Query application logs from the log platform (stdout/stderr of service processes)."""
        if self.settings.backend_is_mock:
            return mock_data.get_mock_handler(req.service)["app_logs"](req)
        resp = self._http.post("/api/v1/logs/query", json=req.model_dump(mode="json"))
        resp.raise_for_status()
        return LogQueryResult.model_validate(resp.json())

    def query_k8s_events(self, service: str) -> K8sEventResult:
        """Query K8s infrastructure events (CrashLoop, probe failures, scheduling) from the K8s API."""
        if self.settings.backend_is_mock:
            return mock_data.get_mock_handler(service)["k8s_events"]()
        resp = self._http.get(f"/api/v1/services/{service}/k8s-events")
        resp.raise_for_status()
        return K8sEventResult.model_validate(resp.json())

    def get_service_status(self, service: str) -> ServiceStatus:
        if self.settings.backend_is_mock:
            return mock_data.get_mock_handler(service)["status"]()
        resp = self._http.get(f"/api/v1/services/{service}/status")
        resp.raise_for_status()
        return ServiceStatus.model_validate(resp.json())

    def get_stream_states(self, service: str) -> list[StreamState]:
        if self.settings.backend_is_mock:
            return mock_data.get_mock_handler(service)["streams"]()
        resp = self._http.get(f"/api/v1/services/{service}/streams")
        resp.raise_for_status()
        data = resp.json()
        return [StreamState.model_validate(item) for item in data]

    def get_metrics(self, service: str) -> MetricSeries:
        if self.settings.backend_is_mock:
            return mock_data.get_mock_handler(service)["metrics"]()
        resp = self._http.get(f"/api/v1/services/{service}/metrics")
        resp.raise_for_status()
        return MetricSeries.model_validate(resp.json())

    def get_latest_operation(self, service: str) -> OperationResult:
        if self.settings.backend_is_mock:
            return mock_data._latest_operation(service)
        resp = self._http.get(f"/api/v1/services/{service}/operations/latest")
        resp.raise_for_status()
        return OperationResult.model_validate(resp.json())

    def execute_ops_action(self, action: str, service: str, body: dict[str, Any]) -> OperationResult:
        if self.settings.backend_is_mock:
            return OperationResult(
                operation_id=f"mock-{action}-{service}",
                service=service,
                action=action,
                status=OperationStatus.SUCCEEDED,
                message=f"Mock {action} executed for {service}",
                started_at=mock_data.NOW,
                finished_at=mock_data.NOW,
            )
        payload = {"service": service, **body}
        resp = self._http.post(f"/api/v1/ops/{action}", json=payload)
        resp.raise_for_status()
        return OperationResult.model_validate(resp.json())


@lru_cache
def get_backend_client() -> BackendClient:
    return BackendClient()
