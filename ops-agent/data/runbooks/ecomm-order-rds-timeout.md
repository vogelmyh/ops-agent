# 电商数据面云数据库 RDS 超时导致下单失败

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于 Pod CrashLoop、事件流暂停、内存泄漏、支付网关熔断（日志可区分）。

## 症状
- 下单接口 **5xx 突增**，错误集中在写库路径。
- 应用日志：
  - `SQLException: Connection timed out waiting for RDS`
  - `HikariPool: Connection is not available, request timed out`
  - `order persist failed: database unreachable`
- K8s Pod **Running**，`replicas_ready == replicas_desired`。
- 无应用 NPE/逻辑异常栈；基础设施指标显示 RDS 延迟/连接数异常。

## 诊断（先确认再动手）
1. **应用日志**：检索 `RDS`、`HikariPool`、`Connection timed out`。
2. **服务状态**：ecomm-order Pod 健康。
3. **K8s 事件**：无 ecomm-order CrashLoop。
4. 确认根因指向 **云厂商 RDS**（托管 MySQL），非应用代码。

## 根因
**托管 RDS 实例**响应超时或连接池耗尽（PaaS 层问题），ecomm-order 无法完成订单持久化。

## 处置
- **超出 ops-agent 自动化范围（out_of_scope）**。
- 通知 **DBA / 云数据库 on-call** 排查 RDS 实例（连接数、慢查询、主从延迟、实例规格）。
- agent 侧可选临时缓解（需人工决策，非默认自动）：`enable_circuit_breaker` 对下单写路径降级（业务影响大，通常不自动执行）。

## 验证
- RDS 恢复后，`order_success_rate` 回升；HikariPool 连接可用。
- agent 无直接修复 RDS 的 write tool。

## 勿用手段
- **不要**`rollback_deployment` / `restart_pods`（应用层无版本/进程问题）。
- **不要**`patch_config` 除非明确有错误的数据源连接串配置（且需 DBA 确认）。

## 后续与升级
- escalation_hint: **DBA / cloud RDS on-call**
- 记录故障时段与受影响订单量，供事后对账。
