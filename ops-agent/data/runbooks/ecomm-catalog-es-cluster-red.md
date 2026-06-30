# 电商目录 ES 集群不可用

## 适用范围
- **仅适用于服务 `ecomm-catalog`**。
- 不适用于：MySQL 连接超时。

## 症状
- 商品搜索/目录查询失败。
- 日志：`ElasticsearchException`、`cluster_block read-only`。

## 诊断（先确认再动手）
1. ES 异常为主。
2. MySQL 连接正常。

## 根因
ES 磁盘水位或分片异常导致集群 red。

## 处置（标准修复）
1. 执行 **`cleanup_storage`**：**service**: `ecomm-catalog`，**path**: `/data/es`（policy risk=medium）。
2. 执行 **`restart_pods`**：**service**: `ecomm-catalog`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- ES 集群 green。
- 目录查询恢复。

## 勿用手段
- **不要**仅调 MySQL 池（非 DB 根因）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
