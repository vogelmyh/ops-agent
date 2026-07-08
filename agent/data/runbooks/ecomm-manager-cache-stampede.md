# 电商管理面本地缓存击穿

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于：限流误配；Redis 故障。

## 症状
- 热点商家接口延迟飙升。
- 应用日志：`cache stampede`、`thundering herd on merchant-profile`。
- 下游 Redis 压力偶发升高。

## 诊断（先确认再动手）
1. 缓存击穿日志，非 rate limit。
2. 非 admin_api_qps 整体骤降模式。

## 根因
热点 key 过期瞬间大量回源。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-manager`，**config_key**: `cache.hot-key-ttl-jitter-sec`，**config_value**: `30`（policy risk=low）。
2. 执行 **`flush_cache`**：**service**: `ecomm-manager`，**scope**: `merchant-profile`（policy risk=low）。

## 验证（修复后必须满足）
- 热点接口 P99 恢复。
- stampede 日志消失。

## 勿用手段
- **不要** `rollback_deployment`。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
