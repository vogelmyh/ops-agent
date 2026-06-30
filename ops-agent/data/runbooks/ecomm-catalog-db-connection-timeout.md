# 电商目录服务数据库连接超时

## 适用范围
- **仅适用于服务 `ecomm-catalog`**。
- 不适用于：ES 集群红；搜索索引问题。

## 症状
- 目录 API 超时。
- 日志：`Communications link failure`、`catalog db timeout`。

## 诊断（先确认再动手）
1. DB 连接超时日志。
2. ES 集群正常。

## 根因
目录库连接池或网络到 catalog DB 异常。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-catalog`，**config_key**: `datasource.connection-timeout-ms`，**config_value**: `5000`（policy risk=low）。
2. 执行 **`restart_pods`**：**service**: `ecomm-catalog`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 目录 API 成功率恢复。

## 勿用手段
- **不要** `resume_event_stream`。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
