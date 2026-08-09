# 电商库存超卖竞态

## 适用范围
- **仅适用于服务 `ecomm-inventory`**。
- 不适用于：同步 lag；预占泄漏。

## 症状
- 库存为负或超卖告警。
- 日志：`oversell detected`、`negative stock`。

## 诊断（先确认再动手）
1. 超卖日志。
2. 非 sync lag。

## 根因
并发扣减竞态条件。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-inventory`，**config_key**: `stock.optimistic-lock-retry`，**config_value**: `5`（policy risk=low）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-inventory`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 负库存消失。
- 扣减成功。

## 勿用手段
- **不要**仅 `restart_deployment` 而不加乐观锁。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
