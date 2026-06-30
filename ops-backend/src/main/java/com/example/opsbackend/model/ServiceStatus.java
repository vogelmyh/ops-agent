package com.example.opsbackend.model;

import java.util.List;

public record ServiceStatus(
        String service,
        boolean healthy,
        int replicasReady,
        int replicasDesired,
        List<PodStatus> pods,
        String message
) {}
