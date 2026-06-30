package com.example.opsbackend.api;

import com.example.opsbackend.model.LogQueryRequest;
import com.example.opsbackend.model.LogQueryResult;
import com.example.opsbackend.service.LogService;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/logs")
public class LogQueryController {

    private final LogService logService;

    public LogQueryController(LogService logService) {
        this.logService = logService;
    }

    @PostMapping("/query")
    public LogQueryResult query(@RequestBody LogQueryRequest request) {
        return logService.query(request);
    }
}
