package com.example.opsbackend.api;

import com.example.opsbackend.model.OperationResult;
import com.example.opsbackend.model.OpsRequest;
import com.example.opsbackend.service.OperationService;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import java.util.Set;

@RestController
@RequestMapping("/api/v1/ops")
public class OpsController {

    private static final Set<String> ALLOWED_ACTIONS = Set.of(
            "rollback_deployment",
            "scale_deployment",
            "restart_deployment",
            "delete_pod",
            "cordon_node",
            "drain_node",
            "enable_circuit_breaker",
            "flush_cache",
            "patch_config",
            "toggle_feature_flag");

    private final OperationService operationService;

    public OpsController(OperationService operationService) {
        this.operationService = operationService;
    }

    @PostMapping("/{action}")
    public OperationResult execute(@PathVariable String action, @RequestBody OpsRequest request) {
        if (!ALLOWED_ACTIONS.contains(action)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "unknown ops action: " + action);
        }
        if (request.service() == null || request.service().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "service is required");
        }
        return operationService.execute(action, request);
    }
}
