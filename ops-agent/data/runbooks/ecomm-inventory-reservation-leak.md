# 电商库存预占泄漏

## 适用范围
- **仅适用于服务 `ecomm-inventory`**。
- 不适用于：超卖；同步 lag。

## 症状
- 可售库存长期偏低。
- 日志：`reservation leak`、`unreleased hold`。

## 诊断（先确认再动手）
1. 预占未释放。
2. 无 oversell。

## 根因
订单取消未释放预占。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-inventory`，**config_key**: `reservation.ttl-sec`，**config_value**: `900`（policy risk=low）。
2. 执行 **`purge_dead_letter_queue`**：**service**: `ecomm-inventory`，**queue**: `reservation-cleanup`（policy risk=low）。

## 验证（修复后必须满足）
- 可售库存恢复。
- hold 数量下降。

## 勿用手段
- **不要** `scale_replicas`  alone。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
