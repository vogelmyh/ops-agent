package com.example.opsbackend.model;

import java.util.List;

public record LogQueryResult(LogQueryRequest query, int total, List<LogEntry> entries) {}
