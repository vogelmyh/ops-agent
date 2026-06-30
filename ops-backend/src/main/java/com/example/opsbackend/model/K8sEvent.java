package com.example.opsbackend.model;

import java.time.Instant;

/**
 * A single event emitted by the K8s control plane (kubelet, scheduler, controller-manager).
 * This is distinct from application logs: K8s events describe infrastructure lifecycle
 * (pod scheduling, CrashLoop, probe failures), while app logs describe business/runtime behaviour.
 */
public record K8sEvent(
        Instant timestamp,
        String type,           // "Normal" | "Warning"
        String reason,         // e.g. "BackOff", "Failed", "Killing", "Pulled"
        String involvedObject, // e.g. "pod/bcs-agent-0", "deployment/bcs-agent"
        String message,
        String service
) {}
