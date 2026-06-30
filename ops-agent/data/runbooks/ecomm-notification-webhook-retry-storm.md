# 电商通知 Webhook 重试风暴

## 适用范围
- **仅适用于服务 `ecomm-notification`**。
- 不适用于：SMTP 故障；推送 down。

## 症状
- MQ 积压，webhook 延迟。
- 日志：`webhook retry storm`、`DLQ growing`。

## 诊断（先确认再动手）
1. webhook retry/DLQ。
2. SMTP 正常。

## 根因
下游 webhook 5xx 导致无限重试。

## 处置（标准修复）
1. 执行 **`purge_dead_letter_queue`**：**service**: `ecomm-notification`，**queue**: `webhook-dlq`（policy risk=medium）。
2. 执行 **`patch_config`**：**service**: `ecomm-notification`，**config_key**: `webhook.max-retries`，**config_value**: `5`（policy risk=low）。

## 验证（修复后必须满足）
- DLQ 清空。
- 投递延迟恢复。

## 勿用手段
- **不要** `patch_config` smtp。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
