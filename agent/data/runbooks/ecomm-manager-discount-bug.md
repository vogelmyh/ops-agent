# 电商管理面折扣计算逻辑缺陷

## 适用范围
- **仅适用于服务 `ecomm-manager`**。
- 不适用于限流、功能开关可关闭的灰度、CrashLoop、磁盘满。

## 症状
- 商家反馈订单金额计算异常（折扣叠加错误）。
- 应用日志出现：
  - `ArithmeticException: discount overflow in DiscountEngine`
  - `order amount mismatch: expected=99.00 actual=0.01`
- K8s Pod **Running**，`replicas_ready == replicas_desired`。
- 无近期镜像变更；功能开关均为已知稳定状态。

## 诊断（先确认再动手）
1. **应用日志**：检索 `ArithmeticException`、`DiscountEngine`、`amount mismatch`。
2. **服务状态**：基础设施层健康。
3. **K8s 事件**：无异常。
4. **最近操作**：无相关配置/发布变更可解释。

## 根因
**应用层折扣计算逻辑 Bug**（代码缺陷），非运维可修复的配置或部署问题。

## 处置
- **超出 ops-agent 自动化范围（out_of_scope）**。
- 通知 **开发团队** 修复 `DiscountEngine` 逻辑并发布 hotfix。
- 临时缓解（需人工决策）：是否紧急关闭相关促销活动（业务侧操作，非 agent 工具）。

## 验证
- 开发发布修复版本后，由发布流程验证订单金额正确性。
- agent 无自动化验证路径。

## 勿用手段
- **不要**执行 `rollback_deployment`（除非确认是近期坏版本引入，且日志指向启动/部署问题）。
- **不要**执行 `patch_config` / `toggle_feature_flag`（根因是代码逻辑，非配置）。
- **不要**执行 `restart_deployment`（无法修复逻辑 Bug）。

## 后续与升级
- escalation_hint: **development team**
- 若影响资金结算，同步财务/风控 on-call。
