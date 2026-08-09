# 电商支付熔断器打开

## 适用范围
- **仅适用于服务 `ecomm-payment`**。
- 不适用于：渠道单次超时；结算对账。

## 症状
- 支付全部失败，快速失败。
- 日志：`circuit breaker open`、`bulkhead rejected`。

## 诊断（先确认再动手）
1. circuit open 明确。
2. 非单次 read timeout。

## 根因
下游渠道连续失败触发熔断。

## 处置（标准修复）
1. 执行 **`enable_circuit_breaker`**：**service**: `ecomm-payment`，**target**: `channel-primary`，**state**: `half-open`（policy risk=medium）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-payment`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 熔断关闭。
- 支付恢复。

## 勿用手段
- **不要**仅加长 timeout（熔断已 open）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
