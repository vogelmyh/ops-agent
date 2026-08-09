# 电商数据面订单事件流暂停

## 适用范围
- **仅适用于服务 `ecomm-order`**（下单/交易链路）。
- 不适用于 CrashLoop、内存泄漏、支付熔断、RDS 超时等其它故障。

## 症状
- 库存长时间未更新，订单状态同步停滞。
- 流状态 **`PAUSED`**（`get_stream_states` 或指标可见）。
- 应用日志：
  - `stream order-events paused by operator`
  - `no ingest heartbeat for stream order-events`
- 指标 `ingest_bytes_per_sec` 从 ~2000000 降至 **0**。
- K8s Pod 通常 Running。

## 诊断（先确认再动手）
1. **流状态**：确认 `order-events` 为 PAUSED。
2. **应用日志**：检索 `paused`、`order-events`。
3. **指标** `ingest_bytes_per_sec`：是否为 0。
4. **K8s 事件**：通常无 CrashLoop。

## 根因
订单事件流 **`order-events`** 被手动或误操作暂停，消费者停止处理，库存/订单状态不同步。

## 处置（标准修复）
1. 确认流为 PAUSED 且业务允许恢复。
2. 执行 **`restart_deployment`**：
   - **service**: `ecomm-order`
   - **strategy**: `rolling`
3. 低风险操作（policy risk=low）。

## 验证（修复后必须满足）
- 流状态变为 **RUNNING**。
- `ingest_bytes_per_sec` 恢复至 **> 100000**。
- 库存更新延迟回落至正常范围。

## 勿用手段
- **不要**执行 `rollback_deployment`（非镜像问题）。
- **不要**在未确认暂停原因时盲目恢复（若因数据修复故意暂停，需人工确认）。

## 后续与升级
- 恢复后检查消费者 lag；若积压严重，考虑临时扩容（`scale_deployment`，高风险，需审批）。
