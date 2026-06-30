package com.example.opsbackend.model;

import java.util.List;

public record K8sEventResult(
        String service,
        int total,
        List<K8sEvent> events
) {}
