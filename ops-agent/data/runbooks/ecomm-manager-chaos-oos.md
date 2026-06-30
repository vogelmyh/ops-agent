# 电商管理面混沌场景 C-②：morph 后超出运维能力范围

## 适用范围
- **仅适用于服务 `ecomm-manager`** 的混沌演练场景（`chaos-oos`）。
- 初始症状与 **限流误配** 相似；修复限流后暴露 **应用逻辑缺陷**。
- **关键约束**：morph 后 catalog 工具 **无法修复**（应 early `out_of_scope`）。

## 症状
### 阶段 A（表象：限流）
- `admin_api_qps` 低位，日志 `RateLimitFilter: threshold misconfigured max-qps=50`。

### 阶段 B（morph：逻辑缺陷）
- QPS 恢复，但 `order_amount_error_rate` 升高。
- 日志：`DiscountEngine` overflow、`order amount mismatch`。

## 诊断
1. 阶段 A：`patch_config` 恢复限流。
2. 重新采集后出现金额校验类 ERROR → 根因为 **代码逻辑 Bug**，非配置/开关问题。

## 根因
限流误配掩盖了 DiscountEngine 逻辑缺陷；属 **开发团队** 修复范畴。

## 处置
- 阶段 A 可尝试 `patch_config`（low risk）。
- 阶段 B：**无适用 write tool** → `out_of_scope`，移交开发。

## 验证
- morph 后 `order_amount_error_rate` 持续偏高；simulator `out_of_scope=true`。
- Agent 不应继续自动 write；`incident_resolved=false`。

## 勿用手段
- 不要 `toggle_feature_flag` / `restart_pods`（与根因无关）。
- 不要幻觉「已修复」。

## 后续与升级
- 升级 development team 发版修复 DiscountEngine。
