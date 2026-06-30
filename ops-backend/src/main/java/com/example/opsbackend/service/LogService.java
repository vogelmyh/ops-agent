package com.example.opsbackend.service;

import com.example.opsbackend.model.LogQueryRequest;
import com.example.opsbackend.model.LogQueryResult;
import com.example.opsbackend.seed.SeedData;
import org.springframework.stereotype.Service;

@Service
public class LogService {

    private final SeedData seedData;

    public LogService(SeedData seedData) {
        this.seedData = seedData;
    }

    public LogQueryResult query(LogQueryRequest request) {
        return seedData.queryLogs(request);
    }
}
