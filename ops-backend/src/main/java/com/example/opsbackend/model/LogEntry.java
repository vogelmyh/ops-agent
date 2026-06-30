package com.example.opsbackend.model;

import java.time.Instant;
import java.util.Map;

public record LogEntry(
        Instant timestamp,
        String level,
        String message,
        String service,
        String stream,
        Map<String, Object> metadata
) {
    public LogEntry(Instant timestamp, String level, String message, String service) {
        this(timestamp, level, message, service, null, Map.of());
    }
}
