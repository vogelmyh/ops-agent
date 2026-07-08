# ops-backend

自研 Spring Boot 3 / Java 17 后端，为 `ops-agent` 提供 **mock/real 统一契约** 的 real 数据源。

## 构建与运行

```bash
# 推荐：Docker 多阶段构建（规避本机 JDK8）
docker build -t ops-backend .
docker run --rm -p 8080:8080 ops-backend

# 本机需 JDK 17+
mvn spring-boot:run
```

## 契约接口

### 读接口

- `POST /api/v1/logs/query`
- `GET /api/v1/services/{service}/status`
- `GET /api/v1/services/{service}/streams`
- `GET /api/v1/services/{service}/metrics`
- `GET /api/v1/services/{service}/k8s-events`
- `GET /api/v1/services/{service}/operations/latest`
- `GET /actuator/health`、`/actuator/prometheus`

### 写接口（标准化 SaaS 运维工具）

`POST /api/v1/ops/{action}`，JSON body 含 `service` 及动作专属字段：

| action | 必填字段 | 可选字段 |
|--------|---------|---------|
| `rollback_deployment` | `service` | `target_version` |
| `scale_replicas` | `service`, `replicas` | — |
| `restart_pods` | `service` | `strategy` (`rolling` / `all`) |
| `enable_circuit_breaker` | `service`, `upstream`, `state` | — |
| `flush_cache` | `service` | `cache_key_pattern` |
| `purge_dead_letter_queue` | `service`, `queue_name` | — |
| `patch_config` | `service`, `config_key`, `config_value` | — |
| `toggle_feature_flag` | `service`, `flag_name`, `enabled` | — |
| `resume_event_stream` | `service`, `stream_id` | — |
| `cleanup_storage` | `service` | `path`, `retention_days` |

JSON 字段使用 **snake_case**，与 `agent/app/schemas.py` 对齐。
