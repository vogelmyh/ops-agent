# 电商网关上游服务超时

## 适用范围
- **仅适用于服务 `ecomm-gateway`**。
- 不适用于：502 坏网关；CORS 风暴；鉴权拦截。

## 症状
- 网关 504 增多。
- 日志：`upstream timed out`、`504 Gateway Timeout`。

## 诊断（先确认再动手）
1. 504/upstream timeout。
2. 上游 pod 可能健康。

## 根因
上游响应超过网关 proxy timeout。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-gateway`，**config_key**: `proxy.read-timeout-ms`，**config_value**: `10000`（policy risk=low）。

## 验证（修复后必须满足）
- 504 下降。
- 路由成功。

## 勿用手段
- **不要** `restart_deployment` 网关而不调 timeout。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
