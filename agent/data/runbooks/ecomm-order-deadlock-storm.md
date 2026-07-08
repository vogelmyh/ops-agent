# 电商数据面下单服务数据库死锁风暴

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于：RDS 网络超时；连接池耗尽；坏镜像。

## 症状
- 下单失败激增，延迟抖动。
- 应用日志：`Deadlock found when trying to get lock`、`MySQLTransactionRollbackException`。
- 指标 `order_error_rate` 突增；DB 连接数正常。

## 诊断（先确认再动手）
1. 日志明确 Deadlock / lock wait timeout。
2. 非 Communications link failure（RDS 网络类）。
3. 非 connection pool exhausted。
4. Pod 健康，镜像稳定。

## 根因
并发下单热点行竞争引发 InnoDB 死锁风暴。

## 处置（标准修复）
1. 执行 **`restart_pods`**：**service**: `ecomm-order`，**strategy**: `rolling`（清理僵死事务连接）（policy risk=medium）。

## 验证（修复后必须满足）
- `order_error_rate` 恢复。
- 死锁日志频率降至基线。

## 勿用手段
- **不要** `patch_config` 随意改池大小（非根因）。
- **不要** `rollback_deployment`。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
