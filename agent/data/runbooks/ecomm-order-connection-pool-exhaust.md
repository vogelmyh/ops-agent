# 电商数据面下单服务连接池耗尽

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于：坏镜像 CrashLoop；OOMKilled 内存泄漏；RDS 实例故障；支付熔断；事件流暂停。

## 症状
- 下单 API 超时，错误率升高，Pod 仍为 Running 且镜像版本稳定。
- 应用日志：`connection pool exhausted, cannot acquire connection`、`HikariPool - Connection is not available`。
- K8s 事件通常无 BackOff；`get_latest_operation` 无近期 upgrade。
- 指标 `order_error_rate` 上升，`ready_replicas` 正常。

## 诊断（先确认再动手）
1. 应用日志确认 connection pool exhausted，而非 OOM 或 startup failed。
2. 服务状态：Pod image 为当前稳定版本，非 bad 镜像。
3. 最近操作：无 rollback/upgrade 记录。
4. 区分于 RDS 超时：日志无 `Communications link failure` / RDS 连接拒绝为主因。

## 根因
应用侧数据库连接池配置过小或连接泄漏，导致 acquire 超时；非数据库实例宕机。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-order`，**config_key**: `datasource.max-pool-size`，**config_value**: `80`（policy risk=low）。
2. 执行 **`restart_deployment`**：**service**: `ecomm-order`，**strategy**: `rolling`（池配置生效后仍僵死时）（policy risk=medium）。

## 验证（修复后必须满足）
- `order_error_rate` 降至基线（< 1%）。
- 日志不再持续 `connection pool exhausted`。

## 勿用手段
- **不要** `rollback_deployment`（镜像未变更）。
- **不要** `scale_deployment` 代替池配置修复（新副本同样耗尽）。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
