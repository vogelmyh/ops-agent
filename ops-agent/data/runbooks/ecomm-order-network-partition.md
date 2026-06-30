# 电商数据面下单服务网络分区 DNS 故障

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于：RDS 实例故障；证书过期；CrashLoop。

## 症状
- 大量 `UnknownHostException`、`no such host` 日志。
- 跨服务调用全部失败；Pod Running。
- K8s 事件偶发 `FailedMount` / DNS 相关 warning。

## 诊断（先确认再动手）
1. 日志含 UnknownHostException / no such host。
2. 非 SSL/certificate 错误。
3. 非数据库 Communications link failure 单独主导。

## 根因
集群 DNS 或 CoreDNS 异常导致服务发现失败。

## 处置（标准修复）
1. 执行 **`restart_pods`**：**service**: `ecomm-order`，**strategy**: `rolling`（policy risk=medium）。
2. 执行 **`scale_replicas`**：**service**: `ecomm-order`，**replicas**: `3`（policy risk=low）。

## 验证（修复后必须满足）
- UnknownHost 日志消失。
- 跨服务调用恢复。

## 勿用手段
- **不要** `patch_config` 改数据源（非配置项根因）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
