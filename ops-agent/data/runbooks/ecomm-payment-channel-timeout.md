# 电商支付渠道响应超时

## 适用范围
- **仅适用于服务 `ecomm-payment`**。
- 不适用于：支付熔断已打开；对账失败。

## 症状
- 支付 pend 比例升高。
- 日志：`channel timeout`、`payment gateway read timed out`。
- 熔断器未 open。

## 诊断（先确认再动手）
1. channel timeout。
2. 无 circuit open 主导日志。

## 根因
外部支付渠道响应慢。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-payment`，**config_key**: `channel.timeout-ms`，**config_value**: `15000`（policy risk=low）。

## 验证（修复后必须满足）
- 支付成功率恢复。
- timeout 日志减少。

## 勿用手段
- **不要** `enable_circuit_breaker` 作为首选（渠道仍可用）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
