package com.example.opsbackend.model;

import java.time.Instant;

public record MetricPoint(Instant timestamp, double value) {}
