"""Active scenario session — dispatches read/write to loaded scenario module."""

from __future__ import annotations

from types import ModuleType

from simulator.scenarios.registry import DEFAULT_SCENARIO_ID, get_scenario


class ScenarioSession:
    def __init__(self, scenario_id: str = DEFAULT_SCENARIO_ID) -> None:
        self._module: ModuleType = get_scenario(scenario_id)
        self._state = self._module.State()

    @property
    def scenario_id(self) -> str:
        return self._module.SCENARIO_ID

    @property
    def service(self) -> str:
        return self._module.SERVICE

    @property
    def state(self):
        return self._state

    def load(self, scenario_id: str) -> None:
        self._module = get_scenario(scenario_id)
        self._state = self._module.State()

    def reset(self) -> None:
        self._state.reset()

    def apply_ops(self, action: str, body: dict):
        return self._state.apply_ops(action, body)

    def project_logs(self, req):
        return self._module.project_logs(self._state, req)

    def project_status(self):
        return self._module.project_status(self._state)

    def project_metrics(self):
        return self._module.project_metrics(self._state)

    def project_k8s_events(self):
        return self._module.project_k8s_events(self._state)

    def project_latest_operation(self):
        return self._module.project_latest_operation(self._state)

    def project_streams(self):
        return self._module.project_streams(self._state)

    def admin_payload(self) -> dict:
        phase = getattr(self._state, "phase", None)
        phase_value = phase.value if hasattr(phase, "value") else str(phase)
        return {
            "scenario": self.scenario_id,
            "service": self.service,
            "phase": phase_value,
            "recovered": self._state.is_recovered,
            "details": self._state.admin_dict(),
            "last_operation": self._state.last_operation,
        }
