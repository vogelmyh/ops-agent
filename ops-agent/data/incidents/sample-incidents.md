# 历史故障摘要

2025-03: ecomm-manager 因配置中心误推 max-qps=50，admin API QPS 从 8k 降至 400，patch_config 后恢复。

2025-01: ecomm-order 升级 3.3.0-bad 导致全副本 CrashLoop，rollback_deployment 至 3.2.1-stable 恢复。

2024-11: order-events 流被暂停 6 小时，resume_event_stream 后库存同步恢复。
