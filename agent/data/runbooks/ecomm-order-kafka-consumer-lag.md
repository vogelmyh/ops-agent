# 电商数据面下单服务 Kafka 消费积压

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于：事件流 ingest 暂停（stream paused）；CrashLoop；支付熔断。

## 症状
- 订单状态同步延迟，下游看到 pending 订单堆积。
- 指标 `kafka_consumer_lag` 持续升高（> 10000）。
- 应用日志：`consumer poll timeout`、`lag behind offset`。
- Stream 状态为 RUNNING（非 PAUSED）。

## 诊断（先确认再动手）
1. 确认 `kafka_consumer_lag` 异常升高。
2. 检查 stream 状态：consumer group 活跃，非 ingest 暂停。
3. 区分 stream-paused：无 `stream paused` / ingest stopped 日志。
4. 最近无坏镜像升级记录。

## 根因
消费者处理变慢或分区热点导致 lag 堆积；ingest 通道正常。

## 处置（标准修复）
1. 执行 **`scale_deployment`**：**service**: `ecomm-order`，**replicas**: `5`（扩展消费者实例）（policy risk=medium）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-order`，**strategy**: `rolling`（单消费者僵死时）（policy risk=medium）。

## 验证（修复后必须满足）
- `kafka_consumer_lag` 回落至 < 1000。
- 订单状态同步延迟恢复正常。

## 勿用手段
- **不要** `restart_deployment`（stream 未 paused）。
- **不要** `rollback_deployment`（非版本问题）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
