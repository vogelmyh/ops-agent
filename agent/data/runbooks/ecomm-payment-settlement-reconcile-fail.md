# 电商支付结算对账不平

## 适用范围
- **仅适用于服务 `ecomm-payment`**。
- 不适用于：渠道超时；熔断。

## 症状
- 结算 job 失败告警。
- 日志：`reconcile mismatch`、`settlement delta non-zero`。

## 诊断（先确认再动手）
1. 对账不平日志。
2. 支付通道调用正常。

## 根因
批次结算文件与渠道账单不一致。

## 处置（标准修复）
1. 执行 **`purge_dead_letter_queue`**：**service**: `ecomm-payment`，**queue**: `settlement-retry`（policy risk=medium）。

## 验证（修复后必须满足）
- 对账 job 成功。
- delta 归零。

## 勿用手段
- **不要** `restart_pods` 作为首选。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
