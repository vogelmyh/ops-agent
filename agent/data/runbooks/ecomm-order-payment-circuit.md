# 电商数据面支付网关依赖连续失败

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于 Pod CrashLoop、事件流暂停、内存泄漏、RDS 超时。

## 症状
- 支付环节 **5xx 占比 80%+**，下单链路在支付步骤失败。
- 应用日志：
  - `payment gateway timeout: upstream payment-gw unreachable`
  - `PaymentClient: 503 from payment-gw, circuit not open`
- K8s Pod **Running**，`replicas_ready == replicas_desired`。
- 指标 `payment_error_rate` 飙升；`payment-gw` 延迟极高。

## 诊断（先确认再动手）
1. **应用日志**：检索 `payment-gw`、`timeout`、`503`。
2. **服务状态**：ecomm-order Pod 健康，问题在上游依赖。
3. **K8s 事件**：ecomm-order 无 CrashLoop。
4. 确认上游为 **`payment-gw`**（外部/内部支付网关服务）。

## 根因
上游 **payment-gw** 不可用或响应超时，ecomm-order 持续重试导致错误率飙升；需打开熔断保护下游与用户体验。

## 处置（标准修复）
1. 确认根因为 **payment-gw 上游故障**。
2. 执行 **`enable_circuit_breaker`**：
   - **service**: `ecomm-order`
   - **upstream**: `payment-gw`
   - **state**: `open`
3. 中风险操作（policy risk=medium）；熔断后支付请求快速失败，避免线程/连接耗尽。

## 验证（修复后必须满足）
- `payment_error_rate` 从超时风暴转为可控的快速失败（或下降）。
- 应用日志出现 `circuit breaker OPEN for payment-gw`。
- 非支付链路（浏览、加购）不受影响。

## 勿用手段
- **不要**对 ecomm-order 执行 `rollback_deployment`（本地服务无版本问题）。
- **不要**`restart_pods`（无法修复上游网关）。
- payment-gw 本身修复属 **out_of_scope**（支付平台团队）。

## 后续与升级
- 通知支付平台 on-call 恢复 payment-gw；恢复后执行 `enable_circuit_breaker` state=`closed`。
- 若需永久降级策略，业务侧配置人工处理。
