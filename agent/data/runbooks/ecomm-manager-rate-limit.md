# 电商管理面 API 限流误配

## 适用范围
- **仅适用于服务 `ecomm-manager`**（商家/运营后台 API）。
- 不适用于 Pod CrashLoop、功能开关、磁盘满等其它故障；应匹配对应 runbook。

## 症状
- 管理 API **QPS 骤降**（典型：从约 8000 降至 400 附近）。
- 应用日志出现：
  - `rate limit exceeded for merchant-api`
  - `RateLimitFilter: threshold misconfigured max-qps=50 expected=5000`
  - `admin api qps dropped after config reload`
- **K8s 层通常正常**：`replicas_ready == replicas_desired`，Pod 为 Running。
- 指标 `admin_api_qps` 持续低位；商家后台操作超时增多。

## 诊断（先确认再动手）
1. **应用日志**：检索 `rate limit`、`max-qps`，确认是否出现 `50` vs `5000` 误配。
2. **指标** `admin_api_qps`：确认是否从 ~8000 跌至 ~400。
3. **服务状态**：Pod 就绪但 message 提示 *rate limit / admin api degraded*。
4. **K8s 事件**：本场景通常无 BackOff/CrashLoop。
5. **配置项**：核对 `rate-limit.max-qps` 当前生效值。

## 根因
`rate-limit.max-qps` 被误配为过低值（**50**，基线应为 **5000**），导致管理 API 快速触顶限流。

常见触发：配置中心误推送、变更单填错数量级。

## 处置（标准修复）
1. 确认根因为 **max-qps 误配**，且服务为 `ecomm-manager`。
2. 执行 **`patch_config`**：
   - **service**: `ecomm-manager`
   - **config_key**: `rate-limit.max-qps`
   - **config_value**: `5000`
3. 低风险配置补丁（policy risk=low），无需回滚或重启 Pod。

## 验证（修复后必须满足）
- `admin_api_qps` 回升至 **≥ 3000 req/s**（完全恢复时约 8000）。
- 应用日志不再持续出现 `rate limit exceeded`。
- 服务 status message 不再提示 admin api degraded。

## 勿用手段（易误判或无效）
- **不要**对 ecomm-manager 执行 `rollback_deployment`（非镜像问题）。
- **不要**仅扩容 Pod 而不修正限流阈值。
- **不要**在 K8s 事件为空时按 CrashLoop 流程回滚。

## 后续与升级
- 若阈值已恢复但 QPS 仍低：升级配置平台 / ecomm-manager 开发 on-call。
