package com.example.opsbackend.model;

public record PodStatus(
        String name,
        boolean ready,
        int restarts,
        String phase,
        String image,
        String reason
) {}
