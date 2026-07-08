# 电商通知邮件 SMTP 失败

## 适用范围
- **仅适用于服务 `ecomm-notification`**。
- 不适用于：webhook 积压；推送厂商故障。

## 症状
- 邮件通知失败率 100%。
- 日志：`SMTP connect failed`、`535 authentication failed`。

## 诊断（先确认再动手）
1. SMTP 错误。
2. webhook 正常。

## 根因
SMTP 凭证过期或端口被封。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-notification`，**config_key**: `smtp.relay-host`，**config_value**: `smtp-backup.internal`（policy risk=low）。

## 验证（修复后必须满足）
- 邮件发送成功。

## 勿用手段
- **不要** `purge_dead_letter_queue` 而不换 relay。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
