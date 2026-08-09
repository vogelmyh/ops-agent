# 电商搜索分片未分配

## 适用范围
- **仅适用于服务 `ecomm-search`**。
- 不适用于：慢查询热点；索引逻辑损坏。

## 症状
- 集群 red/yellow，部分分片 UNASSIGNED。
- 日志：`unassigned shard`、`cluster_block`。

## 诊断（先确认再动手）
1. 分片 UNASSIGNED。
2. 非 slow query 主导。

## 根因
节点宕机或磁盘水位导致分片无法分配。

## 处置（标准修复）
1. 执行 **`scale_deployment`**：**service**: `ecomm-search`，**replicas**: `3`（policy risk=medium）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-search`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 集群 green。
- UNASSIGNED 为 0。

## 勿用手段
- **不要**仅调慢查询阈值。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
