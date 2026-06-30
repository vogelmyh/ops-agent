# 电商缓存 Redis 内存打满

## 适用范围
- **仅适用于服务 `ecomm-cache`**。
- 不适用于：热 key；连接风暴。

## 症状
- 写入失败 `OOM command not allowed`。
- 日志：`maxmemory`、`eviction policy`。
- 读延迟升高。

## 诊断（先确认再动手）
1. maxmemory 相关日志。
2. 非 hot key cpu 单分片模式。

## 根因
缓存容量不足或 TTL 过长大面积堆积。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-cache`，**config_key**: `redis.maxmemory-policy`，**config_value**: `allkeys-lru`（policy risk=low）。
2. 执行 **`flush_cache`**：**service**: `ecomm-cache`，**scope**: `low-value-keys`（policy risk=medium）。

## 验证（修复后必须满足）
- 写入恢复。
- eviction 正常。

## 勿用手段
- **不要**无限 `scale_replicas` 而不调 policy。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
