# 电商数据面下单服务内存泄漏 Pod 僵死

## 适用范围
- **仅适用于服务 `ecomm-order`**。
- 不适用于坏镜像升级（CrashLoop）、事件流暂停、支付熔断、RDS 超时。

## 症状
- 下单请求超时增多，连接池耗尽。
- K8s 事件：`OOMKilled`、Pod 频繁重启但**镜像版本未变**。
- 应用日志：
  - `java.lang.OutOfMemoryError: Java heap space`
  - `connection pool exhausted, cannot acquire connection`
- 指标 `pod_restart_count` 持续上升，`ready_replicas` 可能波动。
- `get_latest_operation` **无**近期镜像变更。

## 诊断（先确认再动手）
1. **K8s 事件**：确认 OOMKilled，非 BackOff 坏镜像模式。
2. **服务状态**：Pod image 为当前稳定版本（如 `ecomm-order:3.2.1`）。
3. **最近操作**：无 upgrade/rollback 记录。
4. **应用日志**：OOM / heap space / connection pool。

## 根因
进程内存泄漏或连接未释放，Pod 进入僵死/反复 OOM 状态；**非版本问题**，滚动重启可临时恢复。

## 处置（标准修复）
1. 确认根因为 **内存泄漏/僵死**（非坏镜像）。
2. 执行 **`restart_deployment`**：
   - **service**: `ecomm-order`
   - **strategy**: `rolling`
3. 中风险操作（policy risk=medium）。

## 验证（修复后必须满足）
- `pod_restart_count` 停止异常增长。
- 下单成功率恢复至 **> 99%**。
- 应用日志不再持续 OOM（短期内；若复发需升级开发排查泄漏根因）。

## 勿用手段
- **不要**执行 `rollback_deployment`（版本未变更，回滚无效或回退到更旧版本）。
- **不要**仅 `scale_deployment` 而不重启（新副本可能同样泄漏）。

## 后续与升级
- 若 24h 内复发：升级开发团队排查内存泄漏；考虑 Type C 混沌场景（重启后再次 OOM）。
