# 电商搜索副本同步延迟

## 适用范围
- **仅适用于服务 `ecomm-search`**。
- 不适用于：索引损坏；分片 unassigned。

## 症状
- 搜索结果不一致，新商品不可见。
- 日志：`replica lag`、`sync delayed`。

## 诊断（先确认再动手）
1. replica lag 日志。
2. 主分片健康。

## 根因
副本同步落后主分片。

## 处置（标准修复）
1. 执行 **`restart_pods`**：**service**: `ecomm-search`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- lag 指标回落。
- 新数据可搜索。

## 勿用手段
- **不要** `flush_cache` 作为唯一手段。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
