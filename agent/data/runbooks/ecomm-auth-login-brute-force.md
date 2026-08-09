# 电商认证暴力破解锁号风暴

## 适用范围
- **仅适用于服务 `ecomm-auth`**。
- 不适用于：JWT 密钥；Redis 宕机。

## 症状
- 登录 QPS 极高，大量 lockout。
- 日志：`brute force detected`、`account locked`。

## 诊断（先确认再动手）
1. 暴力破解/锁号日志。
2. 基础设施正常。

## 根因
恶意登录尝试触发全站锁号策略。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-auth`，**config_key**: `login.rate-limit-per-ip`，**config_value**: `30`（policy risk=low）。
2. 执行 **`enable_circuit_breaker`**：**service**: `ecomm-auth`，**target**: `login-api`（policy risk=medium）。

## 验证（修复后必须满足）
- 锁号率下降。
- 正常用户可登录。

## 勿用手段
- **不要** `restart_deployment` 作为唯一手段。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
