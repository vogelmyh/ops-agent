# 电商库存同步延迟

## 适用范围
- **仅适用于服务 `ecomm-inventory`**。
- 不适用于：超卖竞态；预占泄漏。

## 症状
- 各渠道库存不一致。
- 日志：`inventory sync lag`、`warehouse delta pending`。

## 诊断（先确认再动手）
1. sync lag 日志。
2. 无 negative stock。

## 根因
仓配同步 worker 堆积。

## 处置（标准修复）
1. 执行 **`scale_deployment`**：**service**: `ecomm-inventory`，**replicas**: `4`（policy risk=medium）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-inventory`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- lag 指标正常。
- 渠道库存一致。

## 勿用手段
- **不要**改 optimistic-lock（非竞态根因）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
