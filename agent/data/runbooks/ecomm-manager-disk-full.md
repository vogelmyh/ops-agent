# 电商管理面操作日志堆满磁盘

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于限流误配、功能开关、CrashLoop、应用逻辑 Bug。

## 症状
- Pod 磁盘使用率 **99%**，写操作返回 `ENOSPC` 或 `no space left on device`。
- 应用日志：
  - `failed to write audit log: no space left on device`
  - `disk usage 99% on /var/log/ecomm-manager`
- K8s Pod 仍为 Running，但健康检查可能开始失败。
- 指标 `disk_usage_percent` 持续 >95%。

## 诊断（先确认再动手）
1. **应用日志**：检索 `no space left`、`disk usage`。
2. **服务状态**：Pod Running 但 message 提示 *disk pressure*。
3. **K8s 事件**：可能有 `Evicted` 或 probe 超时（晚期）。
4. 确认路径为 **`/var/log/ecomm-manager`**（审计/操作日志目录）。

## 根因
操作审计日志长期未清理，占满 Pod 挂载磁盘。

## 处置（标准修复）
1. 确认根因为 **磁盘满**，且可安全清理 `/var/log/ecomm-manager` 下过期日志。
2. 执行 **`drain_node`**：
   - **service**: `ecomm-manager`
   - **node_name**: `node-ecomm-manager-0`
   - **force**: `false`
   - **delete_emptydir**: `false`
3. 低风险操作（policy risk=low）。

## 验证（修复后必须满足）
- `disk_usage_percent` 降至 **< 60%**。
- 应用日志不再出现 `no space left on device`。
- 审计写入恢复正常。

## 勿用手段
- **不要**在未确认路径时清理（可能误删需保留的合规审计数据）。
- **不要**执行 `rollback_deployment`（非版本问题）。

## 后续与升级
- 配置日志轮转策略，防止复发；合规保留期变更需安全团队确认。
