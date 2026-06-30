# 电商认证服务 JWT 密钥不一致

## 适用范围
- **仅适用于服务 `ecomm-auth`**。
- 不适用于：Redis session 故障；暴力破解锁号。

## 症状
- 全站登录失败。
- 日志：`JWT signature does not match`、`invalid signature`。

## 诊断（先确认再动手）
1. JWT signature 错误。
2. session store 正常。

## 根因
签发与验签密钥 rotation 不一致。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-auth`，**config_key**: `jwt.signing-key-version`，**config_value**: `v3`（policy risk=medium）。
2. 执行 **`restart_pods`**：**service**: `ecomm-auth`，**strategy**: `rolling`（policy risk=medium）。

## 验证（修复后必须满足）
- 登录成功率恢复。

## 勿用手段
- **不要** `flush_cache` session 作为首选。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
