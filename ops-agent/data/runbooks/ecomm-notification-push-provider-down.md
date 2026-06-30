# 电商通知推送厂商不可用

## 适用范围
- **仅适用于服务 `ecomm-notification`**。
- 不适用于：SMTP；webhook。

## 症状
- App push 全失败。
- 日志：`push provider 503`、`FCM unavailable`。

## 诊断（先确认再动手）
1. push provider 错误。
2. 邮件/webhook 正常。

## 根因
第三方推送服务故障。

## 处置（标准修复）
1. 执行 **`enable_circuit_breaker`**：**service**: `ecomm-notification`，**target**: `push-provider`（policy risk=medium）。
2. 执行 **`patch_config`**：**service**: `ecomm-notification`，**config_key**: `push.fallback-channel`，**config_value**: `sms`（policy risk=low）。

## 验证（修复后必须满足）
- 推送或 fallback 恢复。

## 勿用手段
- **不要** `purge_dead_letter_queue` webhook 队列。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
