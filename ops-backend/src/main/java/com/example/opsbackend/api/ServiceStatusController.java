package com.example.opsbackend.api;

import com.example.opsbackend.model.K8sEventResult;
import com.example.opsbackend.model.MetricSeries;
import com.example.opsbackend.model.OperationResult;
import com.example.opsbackend.model.ServiceStatus;
import com.example.opsbackend.model.StreamState;
import com.example.opsbackend.service.StatusService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/services")
public class ServiceStatusController {

    private final StatusService statusService;

    public ServiceStatusController(StatusService statusService) {
        this.statusService = statusService;
    }

    @GetMapping("/{service}/status")
    public ServiceStatus status(@PathVariable String service) {
        return statusService.status(service);
    }

    @GetMapping("/{service}/streams")
    public List<StreamState> streams(@PathVariable String service) {
        return statusService.streams(service);
    }

    @GetMapping("/{service}/metrics")
    public MetricSeries metrics(@PathVariable String service) {
        return statusService.metrics(service);
    }

    @GetMapping("/{service}/operations/latest")
    public OperationResult latestOperation(@PathVariable String service) {
        return statusService.latestOperation(service);
    }

    @GetMapping("/{service}/k8s-events")
    public K8sEventResult k8sEvents(@PathVariable String service) {
        return statusService.k8sEvents(service);
    }
}
