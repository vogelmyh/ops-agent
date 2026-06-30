# 电商搜索索引分片损坏

## 适用范围
- **仅适用于服务 `ecomm-search`**。
- 不适用于：OOM 导致索引重建中断；查询热点。

## 症状
- 搜索返回空结果或分片错误。
- 应用日志：`index corruption`、`shard failure`、`corrupt file`。
- 索引重建任务可能失败。

## 诊断（先确认再动手）
1. corruption / shard failure 日志。
2. 非单纯 heap OOM（可有损坏后续）。

## 根因
磁盘或异常关机导致 Lucene 分片损坏。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-search`，**config_key**: `index.rebuild-from-snapshot`，**config_value**: `true`（policy risk=medium）。
2. 执行 **`restart_pods`**：**service**: `ecomm-search`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 搜索可用率恢复。
- corruption 日志消失。

## 勿用手段
- **不要** `flush_cache` 代替索引重建。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
