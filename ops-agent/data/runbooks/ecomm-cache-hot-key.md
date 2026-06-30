# 电商缓存 Redis 热 key 打满单分片

## 适用范围
- **仅适用于服务 `ecomm-cache`**。
- 不适用于：Redis 内存满；连接风暴；Pod OOM。

## 症状
- 单 key QPS 极高，延迟抖动。
- 日志：`hot key`、`single shard cpu 100%`。
- Redis 内存未满。

## 诊断（先确认再动手）
1. hot key 证据。
2. 非 OOMKilled。
3. 非 maxmemory 满。

## 根因
热点 key 分布不均。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-cache`，**config_key**: `redis.hot-key-split`，**config_value**: `enabled`（policy risk=low）。
2. 执行 **`flush_cache`**：**service**: `ecomm-cache`，**scope**: `hot-sku`（policy risk=low）。

## 验证（修复后必须满足）
- 单分片 CPU 回落。
- P99 正常。

## 勿用手段
- **不要** `restart_pods` 作为首选（丢热点预热）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
