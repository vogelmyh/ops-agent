# 电商管理面 DNS 解析失败

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于：限流误配；磁盘满。

## 症状
- 调用下游失败，`UnknownHostException`。
- 管理 API 部分功能不可用。

## 诊断（先确认再动手）
1. UnknownHost 为主，非 rate limit。
2. Pod Running。

## 根因
DNS 解析异常或错误 service 名配置。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-manager`，**config_key**: `dns.cache-ttl-sec`，**config_value**: `60`（policy risk=low）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-manager`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- UnknownHost 消失。
- 下游调用恢复。

## 勿用手段
- **不要** `patch_config` rate-limit。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
