"""In-memory mock state: service telemetry after successful remediation."""

from __future__ import annotations

_REMEDIATED: set[str] = set()
_REMEDIATION_BLOCKED: set[str] = set()


def block_remediation(service: str) -> None:
    """Prevent mock telemetry from recovering even after a successful write tool."""
    _REMEDIATION_BLOCKED.add(service)


def is_remediation_blocked(service: str) -> bool:
    return service in _REMEDIATION_BLOCKED


def mark_remediated(service: str) -> None:
    if service in _REMEDIATION_BLOCKED:
        return
    _REMEDIATED.add(service)


def is_remediated(service: str) -> bool:
    return service in _REMEDIATED


def clear_remediated(service: str | None = None) -> None:
    if service is None:
        _REMEDIATED.clear()
        _REMEDIATION_BLOCKED.clear()
    else:
        _REMEDIATED.discard(service)
        _REMEDIATION_BLOCKED.discard(service)
