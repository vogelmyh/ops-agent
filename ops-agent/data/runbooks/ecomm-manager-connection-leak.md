# 电商管理面 HTTP 连接泄漏

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于：限流误配；线程池耗尽。

## 症状
- 管理 API 变慢，文件句柄或连接数接近上限。
- 应用日志：`too many open files`、`Connection leak detection`。

## 诊断（先确认再动手）
1. 连接泄漏日志，非 rate limit exceeded。
2. Pod 仍 Ready。

## 根因
HTTP 客户端未释放连接导致泄漏。

## 处置（标准修复）
1. 执行 **`restart_pods`**：**service**: `ecomm-manager`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- too many open files 告警消失。
- API 延迟恢复。

## 勿用手段
- **不要** `patch_config` rate-limit。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
