# 电商认证 Session Redis 不可用

## 适用范围
- **仅适用于服务 `ecomm-auth`**。
- 不适用于：JWT 密钥问题；暴力破解。

## 症状
- 登录后立即掉线。
- 日志：`session redis connection refused`、`NOAUTH`。

## 诊断（先确认再动手）
1. Redis session 错误。
2. JWT 签发可能成功。

## 根因
Session Redis 宕机或密码轮换。

## 处置（标准修复）
1. 执行 **`restart_pods`**：**service**: `ecomm-auth`，**strategy**: `rolling`（policy risk=medium）。
2. 执行 **`flush_cache`**：**service**: `ecomm-auth`，**scope**: `session`（policy risk=low）。

## 验证（修复后必须满足）
- 会话保持正常。

## 勿用手段
- **不要** `patch_config` jwt key（非 JWT 根因）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
