# 电商管理面混沌场景：限流假象掩盖功能开关故障

## 适用范围
- **仅适用于服务 `ecomm-manager`** 的混沌演练场景（`chaos-morph`）。
- 初始症状与 **限流误配** 高度相似；修复限流后可能暴露 **功能开关** 根因。
- 不适用于单纯的 rate-limit、单纯的 feature-flag、CrashLoop 等单根因场景。

## 症状
### 阶段 A（表象：限流）
- 管理 API **QPS 骤降**（`admin_api_qps` 约 400）。
- 日志：`rate limit exceeded`、`RateLimitFilter: threshold misconfigured max-qps=50`。
- Pod Running，K8s 无 CrashLoop。

### 阶段 B（修复限流后暴露）
- QPS 恢复，但 **`error_rate` 升至 ≥ 0.10**。
- 日志出现：`NullPointerException in PromotionService.applyDiscount`、`feature flag promotion-v2 enabled`。
- 状态 message：*QPS recovered but elevated error rate*。

## 诊断（先确认再动手）
1. 若 `admin_api_qps` 低位且日志含 `max-qps=50`，先按限流场景处理。
2. 执行 `patch_config` 将 `rate-limit.max-qps` 恢复为 `5000` 后，**重新采集**日志与指标。
3. 若 `error_rate` 仍高且出现 `PromotionService` NPE，根因转为 **promotion-v2 功能开关**。

## 根因
两阶段复合故障：限流阈值误配（50 vs 5000）掩盖了已启用的不稳定灰度开关 `promotion-v2` 导致的 NPE。

## 处置（标准修复）
1. **`patch_config`**（service: `ecomm-manager`，`config_key`: `rate-limit.max-qps`，`config_value`: `5000`），风险 **low**。
2. 验证后若 error_rate 仍高，执行 **`toggle_feature_flag`**（`flag_name`: `promotion-v2`，`enabled`: `false`），风险 **low**。

## 验证（修复后必须满足）
- `admin_api_qps` ≥ 3000（阶段 A 修复后）。
- 最终 `error_rate` < 0.02，无持续 `PromotionService` NPE。

## 勿用手段（易误判或无效）
- **不要**在阶段 A 仅 `restart_pods` 而不修正限流阈值。
- **不要**在阶段 B 重复 `patch_config`（限流已恢复）。
- **不要** `rollback_deployment`（镜像未变更）。

## 后续与升级
- 若两阶段修复后仍异常，升级 ecomm-manager 开发 on-call。
