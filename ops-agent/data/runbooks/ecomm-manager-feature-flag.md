# 电商管理面功能开关灰度引发异常

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于限流误配、CrashLoop、磁盘满等其它故障。

## 症状
- 近期开启功能开关后，部分商家访问管理 API 返回 **500**。
- 应用日志出现：
  - `NullPointerException in PromotionService.applyDiscount`
  - `feature flag promotion-v2 enabled, code path unstable`
  - `error rate spiked after flag promotion-v2 rollout`
- K8s Pod 为 Running，`replicas_ready == replicas_desired`。
- 指标 `error_rate` 从 <1% 升至 15%+。

## 诊断（先确认再动手）
1. **应用日志**：检索 `promotion-v2`、`NullPointerException`。
2. **最近操作**：`get_latest_operation` 是否有 feature flag 变更记录。
3. **服务状态**：Pod 健康但 message 提示 *elevated error rate after feature rollout*。
4. **K8s 事件**：通常无 CrashLoop。

## 根因
功能开关 **`promotion-v2`** 被启用，新代码路径存在缺陷，导致促销计算 NPE。

## 处置（标准修复）
1. 确认根因为 **promotion-v2 灰度缺陷**。
2. 执行 **`toggle_feature_flag`**：
   - **service**: `ecomm-manager`
   - **flag_name**: `promotion-v2`
   - **enabled**: `false`
3. 低风险操作（policy risk=low）。

## 验证（修复后必须满足）
- `error_rate` 回落至 **< 2%**。
- 应用日志不再持续出现 `NullPointerException in PromotionService`。
- 商家后台 500 错误消失。

## 勿用手段（易误判或无效）
- **不要**执行 `rollback_deployment`（版本本身可能正常，问题在开关）。
- **不要**重启 Pod 而不关闭开关（重启后开关仍 enabled，问题复现）。

## 后续与升级
- 关闭开关后通知开发团队修复 promotion-v2 代码路径，再重新灰度。
