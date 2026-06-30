"""Pydantic models aligned with ops-agent/app/schemas.py (JSON snake_case)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StreamStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DELETED = "DELETED"


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    message: str
    service: str
    stream: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LogQueryRequest(BaseModel):
    service: str
    keyword: str | None = None
    limit: int = 50


class LogQueryResult(BaseModel):
    query: LogQueryRequest
    total: int
    entries: list[LogEntry]


class PodStatus(BaseModel):
    name: str
    ready: bool
    restarts: int
    phase: str
    image: str
    reason: str | None = None


class ServiceStatus(BaseModel):
    service: str
    healthy: bool
    replicas_ready: int
    replicas_desired: int
    pods: list[PodStatus]
    message: str | None = None


class StreamState(BaseModel):
    project: str
    stream: str
    status: StreamStatus
    topic: str
    last_ingest_at: datetime | None = None


class MetricPoint(BaseModel):
    timestamp: datetime
    value: float


class MetricSeries(BaseModel):
    service: str
    metric: str
    unit: str
    points: list[MetricPoint]


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OperationResult(BaseModel):
    operation_id: str
    service: str
    action: str
    status: OperationStatus
    message: str
    started_at: datetime
    finished_at: datetime | None = None


class K8sEvent(BaseModel):
    timestamp: datetime
    type: str
    reason: str
    involved_object: str
    message: str
    service: str


class K8sEventResult(BaseModel):
    service: str
    total: int
    events: list[K8sEvent]


class OpsRequest(BaseModel):
    service: str
    target_version: str | None = None
    replicas: int | None = None
    strategy: str | None = None
    upstream: str | None = None
    state: str | None = None
    cache_key_pattern: str | None = None
    queue_name: str | None = None
    config_key: str | None = None
    config_value: str | None = None
    flag_name: str | None = None
    enabled: bool | None = None
    stream_id: str | None = None
    path: str | None = None
    retention_days: int | None = None


class AdminStateResponse(BaseModel):
    scenario: str
    service: str
    phase: str
    recovered: bool
    details: dict[str, Any] = Field(default_factory=dict)
    last_operation: OperationResult | None = None
