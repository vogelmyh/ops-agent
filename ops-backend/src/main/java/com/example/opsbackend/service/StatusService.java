package com.example.opsbackend.service;

import com.example.opsbackend.model.K8sEventResult;
import com.example.opsbackend.model.MetricSeries;
import com.example.opsbackend.model.OperationResult;
import com.example.opsbackend.model.ServiceStatus;
import com.example.opsbackend.model.StreamState;
import com.example.opsbackend.seed.SeedData;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class StatusService {

    private final SeedData seedData;

    public StatusService(SeedData seedData) {
        this.seedData = seedData;
    }

    public ServiceStatus status(String service) {
        return seedData.serviceStatus(service);
    }

    public List<StreamState> streams(String service) {
        return seedData.streamStates(service);
    }

    public MetricSeries metrics(String service) {
        return seedData.metrics(service);
    }

    public OperationResult latestOperation(String service) {
        return seedData.latestOperation(service);
    }

    public K8sEventResult k8sEvents(String service) {
        return seedData.k8sEvents(service);
    }
}
