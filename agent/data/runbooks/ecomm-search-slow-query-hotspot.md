# 电商搜索慢查询热点

## 适用范围
- **仅适用于服务 `ecomm-search`**。
- 不适用于：索引损坏；OOM 索引重建。

## 症状
- 搜索 P99 延迟高但无索引损坏错误。
- 应用日志：`slow query`、`took_millis > 3000`、特定 query pattern。

## 诊断（先确认再动手）
1. 慢查询日志，无 corruption。
2. 副本同步正常。

## 根因
热点查询未命中缓存或缺少索引字段。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-search`，**config_key**: `query.slow-log-threshold-ms`，**config_value**: `2000`（policy risk=low）。
2. 执行 **`scale_deployment`**：**service**: `ecomm-search`，**replicas**: `4`（policy risk=low）。

## 验证（修复后必须满足）
- P99 < 1s。
- slow query 比例下降。

## 勿用手段
- **不要**全量 rebuild 索引（无损坏证据）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
