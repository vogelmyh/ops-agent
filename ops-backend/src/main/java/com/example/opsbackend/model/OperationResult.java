package com.example.opsbackend.model;

import java.time.Instant;

public record OperationResult(
        String operationId,
        String service,
        String action,
        String status,
        String message,
        Instant startedAt,
        Instant finishedAt
) {}
