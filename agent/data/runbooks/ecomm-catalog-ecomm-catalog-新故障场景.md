# ecomm-catalog 新故障场景

## 适用范围
- **仅适用于服务 `ecomm-catalog`**。
- 不适用于本服务其它已知故障场景；若症状不匹配应重新检索 runbook。

## 症状
Top candidate 'ecomm-catalog-ecomm-catalog-新故障场景' not selectable: symptom_match=FAIL (oracle: weak match for ecomm-catalog-ecomm-catalog-新故障场景); telemetry_match=FAIL (Telemetry does not align with this runbook.); symptom_match=FAIL (required PASS; oracle: weak match for ecomm-catalog-ecomm-catalog-新故障场景); PASS count 1 < min 2

## 诊断（先确认再动手）
1. 对照应用日志、服务状态与指标，确认与本次 incident 证据一致。

## 根因
Unknown root cause for service ecomm-catalog

## 处置（标准修复）
Identified large logs under /var/log; retention policy applied.

## 验证（修复后必须满足）
人工确认核心指标与日志恢复正常；agent 无自动化验收路径时写明需人工验证项。

## 勿用手段（易误判或无效）
- **不要**在未确认根因前执行高风险 write tool（如 rollback_deployment）。

## 后续与升级
- 若处置后仍异常，升级至 senior ops 或对应服务 on-call。
