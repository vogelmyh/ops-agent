package com.example.opsbackend.service;

import com.example.opsbackend.model.OperationResult;
import com.example.opsbackend.model.OpsRequest;
import com.example.opsbackend.seed.SeedData;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class OperationService {

    private final SeedData seedData;

    public OperationService(SeedData seedData) {
        this.seedData = seedData;
    }

    public OperationResult execute(String action, OpsRequest request) {
        validateRequiredFields(action, request);
        return seedData.executeOps(action, request);
    }

    private void validateRequiredFields(String action, OpsRequest request) {
        switch (action) {
            case "rollback_deployment" -> {
                // target_version optional — defaults to previous stable
            }
            case "scale_replicas" -> require(request.replicas() != null, "replicas is required for scale_replicas");
            case "restart_pods" -> {
                // strategy optional — defaults to rolling
            }
            case "enable_circuit_breaker" -> {
                require(request.upstream() != null && !request.upstream().isBlank(),
                        "upstream is required for enable_circuit_breaker");
                require(request.state() != null && !request.state().isBlank(),
                        "state is required for enable_circuit_breaker");
            }
            case "flush_cache" -> {
                // cache_key_pattern optional — defaults to *
            }
            case "purge_dead_letter_queue" -> require(
                    request.queueName() != null && !request.queueName().isBlank(),
                    "queue_name is required for purge_dead_letter_queue");
            case "patch_config" -> {
                require(request.configKey() != null && !request.configKey().isBlank(),
                        "config_key is required for patch_config");
                require(request.configValue() != null,
                        "config_value is required for patch_config");
            }
            case "toggle_feature_flag" -> {
                require(request.flagName() != null && !request.flagName().isBlank(),
                        "flag_name is required for toggle_feature_flag");
                require(request.enabled() != null,
                        "enabled is required for toggle_feature_flag");
            }
            case "resume_event_stream" -> require(
                    request.streamId() != null && !request.streamId().isBlank(),
                    "stream_id is required for resume_event_stream");
            case "cleanup_storage" -> {
                // path and retention_days optional — defaults applied by agent
            }
            default -> throw new ResponseStatusException(HttpStatus.NOT_FOUND, "unknown ops action: " + action);
        }
    }

    private void require(boolean condition, String message) {
        if (!condition) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
        }
    }
}
