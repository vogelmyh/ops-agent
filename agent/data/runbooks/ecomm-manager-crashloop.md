# 电商管理面升级后 CrashLoop

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于限流误配、功能开关、磁盘满等其它故障。

## 症状
- Deployment **0/2 Ready**，Pod 处于 `CrashLoopBackOff`。
- K8s 事件：`BackOff`、`Failed`、`Unhealthy`（readiness probe connection refused）。
- 应用日志（崩溃前）：`Application startup failed`、`Health check server failed to start`。
- 指标 `ready_replicas` 从 2 骤降至 0。
- 近期有镜像升级操作（`get_latest_operation` 可见 bad release）。

## 诊断（先确认再动手）
1. **K8s 事件**：确认 BackOff / probe failed。
2. **服务状态**：`replicas_ready == 0`，Pod image 为异常版本（如 `ecomm-manager:2.1.0-bad`）。
3. **最近操作**：确认升级记录及目标镜像 tag。
4. **应用日志**：启动失败类错误，非限流/开关问题。

## 根因
镜像 **`ecomm-manager:2.1.0-bad`** 存在启动缺陷，所有副本无法通过健康检查。

## 处置（标准修复）
1. 确认根因为 **坏镜像升级**。
2. 执行 **`rollback_deployment`**（高风险，需审批）：
   - **service**: `ecomm-manager`
   - **target_version**: `ecomm-manager:2.0.8-stable`（或省略以回滚至上一稳定版）
3. policy risk=high，需人工审批后执行。

## 验证（修复后必须满足）
- `ready_replicas` 恢复至 **2/2**。
- K8s 事件不再新增 BackOff。
- 管理 API 可正常访问。

## 勿用手段（易误判或无效）
- **不要**使用 `patch_config` 或 `toggle_feature_flag`（非配置/开关问题）。
- **不要**在未确认镜像版本时盲目 `restart_deployment`（坏镜像重启仍会崩溃）。

## 后续与升级
- 回滚成功后通知发布团队排查 2.1.0-bad 镜像构建问题。
