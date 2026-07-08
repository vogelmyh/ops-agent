# 电商网关鉴权过滤器误拦截

## 适用范围
- **仅适用于服务 `ecomm-gateway`**。
- 不适用于：502；CORS preflight。

## 症状
- 合法请求 401/403 激增。
- 日志：`auth filter rejected`、`invalid token signature`。

## 诊断（先确认再动手）
1. auth filter 拒绝。
2. 上游未收到请求。

## 根因
鉴权配置或 JWKS 缓存过期。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-gateway`，**config_key**: `auth.jwks-cache-ttl-sec`，**config_value**: `300`（policy risk=low）。
2. 执行 **`restart_pods`**：**service**: `ecomm-gateway`，**strategy**: `rolling`（policy risk=low）。

## 验证（修复后必须满足）
- 401/403 恢复正常。
- 合法流量通过。

## 勿用手段
- **不要** `patch_config` proxy timeout。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
