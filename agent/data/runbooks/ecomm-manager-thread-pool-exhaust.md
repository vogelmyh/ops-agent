# 电商管理面线程池耗尽

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于：限流误配；CrashLoop；磁盘满。

## 症状
- 管理 API 超时，线程池拒绝任务。
- 应用日志：`RejectedExecutionException`、`Thread pool is EXHAUSTED`。
- Pod Running；`admin_api_qps` 可能正常或下降。

## 诊断（先确认再动手）
1. 日志明确线程池耗尽，非 rate limit exceeded。
2. 核对 `rate-limit.max-qps` 正常（约 5000）。
3. 无 CrashLoopBackOff。

## 根因
异步任务堆积或线程池 max 配置过低。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-manager`，**config_key**: `executor.max-threads`，**config_value**: `200`（policy risk=low）。
2. 执行 **`restart_pods`**：**service**: `ecomm-manager`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- RejectedExecutionException 消失。
- API P99 恢复。

## 勿用手段
- **不要**仅 `patch_config` rate-limit（非限流问题）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
