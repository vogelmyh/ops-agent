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
| `scale_deployment` | `service`, `replicas` | — |
| `restart_deployment` | `service` | `strategy` (`rolling` / `all`) |
| `delete_pod` | `service`, `pod_name` | `grace_period_seconds` |
| `cordon_node` | `service`, `node_name` | — |
| `drain_node` | `service`, `node_name` | `force`, `delete_emptydir` |
| `enable_circuit_breaker` | `service`, `upstream`, `state` | — |
| `flush_cache` | `service` | `cache_key_pattern` |
| `patch_config` | `service`, `config_key`, `config_value` | — |
| `toggle_feature_flag` | `service`, `flag_name`, `enabled` | — |

JSON 字段使用 **snake_case**，与 `agent/app/schemas.py` 对齐。
