# 电商网关上游连接拒绝 502

## 适用范围
- **仅适用于服务 `ecomm-gateway`**。
- 不适用于：上游慢超时；CORS。

## 症状
- 502 Bad Gateway 激增。
- 日志：`connection refused`、`no healthy upstream`。

## 诊断（先确认再动手）
1. connection refused / no healthy upstream。
2. 非 read timeout。

## 根因
上游实例全不可用或 service endpoints 空。

## 处置（标准修复）
1. 执行 **`scale_replicas`**：**service**: `ecomm-gateway`，**replicas**: `3`（policy risk=low）。
2. 执行 **`patch_config`**：**service**: `ecomm-gateway`，**config_key**: `loadbalancer.health-check-interval-sec`，**config_value**: `5`（policy risk=low）。

## 验证（修复后必须满足）
- 502 消失。
- upstream 健康。

## 勿用手段
- **不要**仅加长 read-timeout（连接被拒绝）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
