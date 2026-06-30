package com.example.opsbackend.model;

import java.util.List;

public record MetricSeries(String service, String metric, String unit, List<MetricPoint> points) {}
