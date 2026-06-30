"""HTTP sequence tests (L3) — mirrors ops-agent BackendClient + write tools."""

import pytest
from fastapi.testclient import TestClient

from simulator.app import app

ECOMM_MANAGER_RATE_LIMIT_PATCH = {
    "service": "ecomm-manager",
    "config_key": "rate-limit.max-qps",
    "config_value": "5000",
}


@pytest.fixture
def client():
    c = TestClient(app)
    c.post("/admin/scenario/ecomm-manager-rate-limit")
    c.post("/admin/reset")
    yield c
    c.post("/admin/reset")


def test_health():
    resp = TestClient(app).get("/actuator/health")
    assert resp.status_code == 200


def test_list_scenarios():
    resp = TestClient(app).get("/admin/scenarios")
    assert resp.status_code == 200
    ids = {s["id"] for s in resp.json()}
    assert "ecomm-manager-rate-limit" in ids
    assert "ecomm-order-crashloop" in ids


def test_ecomm_manager_rate_limit_recover_sequence(client):
    status = client.get("/api/v1/services/ecomm-manager/status").json()
    msg = status["message"].lower()
    assert status["healthy"] is True
    assert any(k in msg for k in ("degraded", "rate limit", "qps", "baseline"))

    metrics = client.get("/api/v1/services/ecomm-manager/metrics").json()
    assert metrics["metric"] == "admin_api_qps"
    assert metrics["points"][-1]["value"] < 3000

    patch = client.post("/api/v1/ops/patch_config", json=ECOMM_MANAGER_RATE_LIMIT_PATCH)
    assert patch.status_code == 200
    assert patch.json()["status"] == "SUCCEEDED"

    metrics_after = client.get("/api/v1/services/ecomm-manager/metrics").json()
    assert metrics_after["points"][-1]["value"] >= 3000

    admin = client.get("/admin/state").json()
    assert admin["phase"] == "RECOVERED"
    assert admin["recovered"] is True


def test_wrong_patch_stays_broken(client):
    client.post(
        "/api/v1/ops/patch_config",
        json={
            "service": "ecomm-manager",
            "config_key": "rate-limit.max-qps",
            "config_value": "50",
        },
    )
    metrics = client.get("/api/v1/services/ecomm-manager/metrics").json()
    assert metrics["points"][-1]["value"] < 3000
    assert client.get("/admin/state").json()["phase"] == "BROKEN"


def test_unknown_service_404(client):
    assert client.get("/api/v1/services/ecomm-order/status").status_code == 404


def test_load_scenario_and_reset(client):
    client.post("/admin/scenario/ecomm-order-crashloop")
    assert client.get("/api/v1/services/ecomm-order/status").json()["replicas_ready"] == 0

    rollback = client.post(
        "/api/v1/ops/rollback_deployment",
        json={"service": "ecomm-order", "target_version": "ecomm-order:3.2.1-stable"},
    )
    assert rollback.status_code == 200
    assert client.get("/api/v1/services/ecomm-order/status").json()["replicas_ready"] == 3

    client.post("/admin/reset")
    assert client.get("/api/v1/services/ecomm-order/status").json()["replicas_ready"] == 0
