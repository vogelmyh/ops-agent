# 电商缓存 Pipeline 批量超时

## 适用范围
- **仅适用于服务 `ecomm-cache`**。
- 不适用于：热 key；内存满；连接风暴。

## 症状
- 批量读超时，单 key 正常。
- 日志：`pipeline timeout`、`batch get timeout`。

## 诊断（先确认再动手）
1. pipeline/batch 超时。
2. 单 op 正常。

## 根因
pipeline 批次过大或网络抖动。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-cache`，**config_key**: `redis.pipeline-batch-size`，**config_value**: `50`（policy risk=low）。

## 验证（修复后必须满足）
- batch 超时消失。
- 批量读成功。

## 勿用手段
- **不要** `flush_cache` 全库。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
