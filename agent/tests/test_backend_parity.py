import os

import httpx
import pytest

from app.adapters.backend_client import BackendClient
from app.config import get_settings
from app.schemas import LogQueryRequest

BACKEND_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8080")


def _backend_reachable() -> bool:
    try:
        resp = httpx.get(f"{BACKEND_URL.rstrip('/')}/actuator/health", timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


@pytest.fixture
def _clients(monkeypatch):
    monkeypatch.setenv("BACKEND_BASE_URL", BACKEND_URL)
    get_settings.cache_clear()
    monkeypatch.setenv("BACKEND_MODE", "mock")
    get_settings.cache_clear()
    mock_client = BackendClient()
    monkeypatch.setenv("BACKEND_MODE", "real")
    get_settings.cache_clear()
    real_client = BackendClient()
    yield mock_client, real_client
    get_settings.cache_clear()


@pytest.mark.skipif(not _backend_reachable(), reason="ops-backend not running")
def test_logs_parity_ecomm_manager(_clients):
    mock_client, real_client = _clients
    req = LogQueryRequest(service="ecomm-manager", keyword="rate", limit=5)
    mock_result = mock_client.query_logs(req)
    real_result = real_client.query_logs(req)
    assert real_result.total == mock_result.total
    assert len(real_result.entries) == len(mock_result.entries)
