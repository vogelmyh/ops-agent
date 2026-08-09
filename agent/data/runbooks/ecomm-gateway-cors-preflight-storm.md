# 电商网关 CORS 预检风暴

## 适用范围
- **仅适用于服务 `ecomm-gateway`**。
- 不适用于：502；鉴权误拦。

## 症状
- OPTIONS 流量打满，业务 GET/POST 下降。
- 日志：`CORS preflight storm`、`OPTIONS flood`。

## 诊断（先确认再动手）
1. OPTIONS 风暴。
2. 非 upstream timeout。

## 根因
浏览器预检缓存失效或错误 CORS 配置。

## 处置（标准修复）
1. 执行 **`patch_config`**：**service**: `ecomm-gateway`，**config_key**: `cors.max-age-sec`，**config_value**: `3600`（policy risk=low）。

## 验证（修复后必须满足）
- OPTIONS QPS 下降。
- 业务 QPS 恢复。

## 勿用手段
- **不要** `scale_deployment` 而不修 CORS。

## 后续与升级
若 24h 内复发，升级对应服务 on-call 与平台团队。
