# 电商数据面下单服务 TLS 证书过期

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于：坏镜像 CrashLoop；内存泄漏；RDS 超时。

## 症状
- 对外 HTTPS 调用失败，下单链路中断。
- 应用日志：`certificate expired`、`SSLHandshakeException`、` PKIX path validation failed`。
- Pod Running；近期可能有 cert 轮换变更。

## 诊断（先确认再动手）
1. 日志含 certificate expired / SSLHandshakeException。
2. 非 Application startup failed / BackOff。
3. 非 OOMKilled。
4. 检查最近 operation 是否含 cert/config 变更。

## 根因
服务端或出站 TLS 证书过期，握手失败。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-order`，**config_key**: `tls.trust-store-version`，**config_value**: `2026-06`（policy risk=low）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-order`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- SSL 握手错误日志消失。
- 下单成功率恢复。

## 勿用手段
- **不要** `rollback_deployment`（除非明确坏镜像）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
