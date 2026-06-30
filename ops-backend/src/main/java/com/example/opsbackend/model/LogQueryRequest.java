package com.example.opsbackend.model;

public record LogQueryRequest(String service, String keyword, int limit) {
    public LogQueryRequest {
        if (limit <= 0) {
            limit = 50;
        }
    }
}
