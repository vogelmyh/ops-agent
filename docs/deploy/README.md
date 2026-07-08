# 部署清单

本目录为 **monorepo 根** 下的 `deploy/` 清单，与文档分离存放。

| 路径 | 说明 |
|------|------|
| [`docker-compose.yml`](../../deploy/docker-compose.yml) | 本地多服务编排（agent + Java backend + Redis） |
| [`k8s/`](../../deploy/k8s/) | Kubernetes Deployment / Service / HPA / ConfigMap / Secret 模板 |

## 常用命令

```bash
# monorepo 根目录
make build    # docker compose build
make up       # docker compose up -d
make down
make k8s-dry-run
```

Agent 运行时环境变量与联调步骤见 [`docs/agent/architecture.md`](../agent/architecture.md) §4 与 [`docs/agent/backend-adapters-architecture.md`](../agent/backend-adapters-architecture.md) §5。

## 变更记录

### 2026-07-08 · 文档目录重组

- 部署说明迁入 `docs/deploy/`；清单文件仍位于仓库根 `deploy/`。
