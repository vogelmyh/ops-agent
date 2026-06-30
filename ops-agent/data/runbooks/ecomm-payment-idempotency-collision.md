# 电商支付幂等键冲突风暴

## 适用范围
- **仅适用于服务 `ecomm-payment`**。
- 不适用于：渠道超时；熔断。

## 症状
- 重复支付拒绝激增。
- 日志：`idempotency key collision`、`duplicate payment rejected`。

## 诊断（先确认再动手）
1. 幂等冲突日志。
2. 渠道正常。

## 根因
客户端重试未更换幂等键。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-payment`，**config_key**: `idempotency.ttl-sec`，**config_value**: `86400`（policy risk=low）。

## 验证（修复后必须满足）
- 冲突率下降。
- 支付成功恢复。

## 勿用手段
- **不要** `enable_circuit_breaker`。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
