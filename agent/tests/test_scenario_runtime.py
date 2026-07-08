"""Tests for shared simulator session lifecycle."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

import scenario_runtime as rt


def test_start_simulator_skips_when_already_healthy():
    rt._thread_started_ports.clear()
    with patch.object(rt, "simulator_is_healthy", return_value=True):
        with patch.object(rt, "_start_simulator_thread") as start_thread:
            rt.start_simulator(8099)
            start_thread.assert_not_called()


def test_prepare_simulator_uses_active_session():
    class FakeSession:
        def prepare_act(self, scenario_id, *, mock_service, mock_scenario):
            return f"client:{scenario_id}"

    fake = FakeSession()
    rt._active_session = fake
    try:
        client = rt.prepare_simulator(
            "ecomm-order-stream-paused",
            mock_service="ecomm-order",
            mock_scenario="stream-paused",
        )
        assert client == "client:ecomm-order-stream-paused"
    finally:
        rt._active_session = None
