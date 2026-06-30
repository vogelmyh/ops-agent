package com.example.opsbackend.model;

import java.time.Instant;

public record StreamState(
        String project,
        String stream,
        String status,
        String topic,
        Instant lastIngestAt
) {}
