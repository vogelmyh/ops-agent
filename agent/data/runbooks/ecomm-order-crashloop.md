# 电商数据面下单服务升级后 CrashLoop

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于事件流暂停、内存泄漏（同版本 OOM）、支付熔断、RDS 超时。

## 症状
- Deployment **0/3 Ready**，Pod `CrashLoopBackOff`。
- K8s 事件：BackOff、readiness probe `connection refused`。
- 应用日志：`Application startup failed`、`Back-off restarting failed container`。
- 指标 `ready_replicas` 从 3 降至 0。
- 近期升级至 **`ecomm-order:3.3.0-bad`**。

## 诊断（先确认再动手）
1. **K8s 事件**：BackOff / Unhealthy。
2. **服务状态**：Pod image 为坏版本。
3. **最近操作**：升级记录可见。
4. 区分于内存泄漏：本场景为**新版本无法启动**，非同版本 OOM。

## 根因
镜像 **`ecomm-order:3.3.0-bad`** 启动失败，全部副本 CrashLoop。

## 处置（标准修复）
1. 确认坏镜像升级。
2. 执行 **`rollback_deployment`**（高风险，需审批）：
   - **service**: `ecomm-order`
   - **target_version**: `ecomm-order:3.2.1-stable`
3. policy risk=high。

## 验证（修复后必须满足）
- `ready_replicas` 恢复 **3/3**。
- 下单 API 可用，错误率正常。

## 勿用手段
- **不要**`restart_deployment`（坏镜像重启仍失败）。
- **不要**`patch_config`（非配置问题）。

## 后续与升级
- 回滚后通知发布团队；若回滚后仍 OOM 循环，见内存泄漏 runbook 或 Type C 混沌测试。
