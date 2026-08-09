# 电商数据面下单服务 gRPC 超时级联

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于：支付熔断；RDS 超时；连接池耗尽。

## 症状
- 下单超时，P99 延迟飙升。
- 应用日志：`DEADLINE_EXCEEDED`、`grpc.StatusCode.DEADLINE_EXCEEDED`。
- 下游 inventory/payment 调用超时；Pod 正常。

## 诊断（先确认再动手）
1. 日志以 gRPC DEADLINE_EXCEEDED 为主，非 pool exhausted。
2. 非 payment circuit open 主导（无 bulkhead/circuit 日志）。
3. 指标延迟升但 error 可能未达熔断阈值。

## 根因
下游依赖响应慢导致 gRPC 客户端 deadline 超时级联。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-order`，**config_key**: `grpc.deadline-ms`，**config_value**: `8000`（policy risk=low）。
2. 执行 **`enable_circuit_breaker`**：**service**: `ecomm-order`，**target**: `ecomm-inventory`（policy risk=medium）。

## 验证（修复后必须满足）
- P99 延迟回落至 SLA 内。
- DEADLINE_EXCEEDED 日志减少。

## 勿用手段
- **不要** `restart_deployment` 作为首选（未缓解下游慢）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
