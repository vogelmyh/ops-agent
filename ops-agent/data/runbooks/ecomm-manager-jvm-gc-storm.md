# 电商管理面 JVM GC 风暴导致 STW

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于：限流误配；OOMKilled；磁盘满。

## 症状
- API 周期性卡顿，P99 尖刺。
- 应用日志：`GC overhead limit exceeded`、`Pause Full GC` 频繁。
- Pod 未 OOM；heap 使用率高。

## 诊断（先确认再动手）
1. GC 日志频繁 Full GC，非 rate limit。
2. 非 OOMKilled（进程仍在）。
3. 镜像稳定。

## 根因
堆内存压力大或 GC 参数不当导致 STW 过长。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-manager`，**config_key**: `jvm.gc.max-pause-ms`，**config_value**: `200`（policy risk=low）。
2. 执行 **`restart_pods`**：**service**: `ecomm-manager`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- Full GC 频率下降。
- P99 尖刺消失。

## 勿用手段
- **不要** `rollback_deployment`（非镜像问题）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
