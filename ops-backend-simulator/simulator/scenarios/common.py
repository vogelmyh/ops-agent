"""Shared helpers for simulator scenarios."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from simulator.schemas import OperationResult, OperationStatus

NOW = datetime(2026, 6, 4, 7, 0, 0, tzinfo=timezone.utc)


class Phase(str, Enum):
    BROKEN = "BROKEN"
    RECOVERED = "RECOVERED"


def op_result(
    *,
    service: str,
    action: str,
    message: str,
    status: OperationStatus = OperationStatus.SUCCEEDED,
    op_id: str | None = None,
) -> OperationResult:
    oid = op_id or f"op-{action}-{service}"
    return OperationResult(
        operation_id=oid,
        service=service,
        action=action,
        status=status,
        message=message,
        started_at=NOW,
        finished_at=NOW,
    )
