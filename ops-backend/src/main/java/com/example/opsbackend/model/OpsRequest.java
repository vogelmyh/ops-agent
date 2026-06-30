package com.example.opsbackend.model;

/**
 * Unified request body for standardized SaaS ops write actions.
 * Fields are optional; each action validates its required subset.
 */
public record OpsRequest(
        String service,
        String targetVersion,
        Integer replicas,
        String strategy,
        String upstream,
        String state,
        String cacheKeyPattern,
        String queueName,
        String configKey,
        String configValue,
        String flagName,
        Boolean enabled,
        String streamId,
        String path,
        Integer retentionDays) {
}
