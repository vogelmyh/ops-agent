# 电商缓存 Redis 连接风暴

## 适用范围
- **仅适用于服务 `ecomm-cache`**。
- 不适用于：热 key；内存满。

## 症状
- Redis `max clients reached`。
- 应用连接超时；Pod 频繁重连。

## 诊断（先确认再动手）
1. max clients 日志。
2. 内存未满。

## 根因
客户端连接池配置过大或泄漏。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-cache`，**config_key**: `redis.max-clients`，**config_value**: `10000`（policy risk=low）。
2. 执行 **`restart_pods`**：**service**: `ecomm-cache`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 连接数稳定。
- 拒绝连接消失。

## 勿用手段
- **不要** `flush_cache`（非数据问题）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
