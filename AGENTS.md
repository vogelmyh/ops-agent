# Agent 工作指引（ops Agent monorepo）

本仓库为 **拟真运维 Agent 演示** 的 Git monorepo，包含 Python Agent、Simulator、Java 后端与部署清单。

## 仓库布局

| 路径 | 说明 |
|------|------|
| `ops-agent/` | Python 3.12 + LangGraph + FastAPI（主工程） |
| `ops-backend-simulator/` | 有状态 HTTP 后端替身 |
| `ops-backend/` | Spring Boot 生产契约参考 |
| `deploy/` | docker-compose + K8s |
| `docs/change-workflow.md` | **每次改代码前必读** — 七步 SOP |
| `ops-agent/docs/` | 架构、测试、组件级「改动同步指南」 |

## 强制流程（不可跳过）

1. **`git status` / `git diff`** — 确认影响文件
2. **读 `docs/change-workflow.md`** — 分类改动、定位组件文档 §「Agent 改动同步指南」
3. **先输出「同步计划」**（必改/不必改的代码、测试、文档、验证命令）— **用户确认后再写代码**
4. 实现改动（小步、可回滚）
5. **跑同步计划中的 `make test-*`**，贴通过摘要
6. **更新版本注记 / 变更记录**（见各组件文档要求）
7. 合入前自检 `docs/change-workflow.md` 勾选清单

## 文档入口

- 索引：`ops-agent/docs/README.md`
- 总览：`ops-agent/docs/architecture.md`
- RAG：`ops-agent/docs/rag-architecture-and-tests.md` §5
- 场景目录（只列测什么）：`ops-agent/docs/test-scenario-trajectories.md`
- Simulator 实现细节：`ops-backend-simulator/README.md`（联调步骤见 `ops-agent/docs/backend-adapters-architecture.md` §5）

## 验证命令（monorepo 根目录）

```bash
make install-hooks   # 一次性：pre-commit 按路径跑 test-*
make test-rag-retrieval   # Track A — 纯检索
make test-rag-coverage    # Track B — coverage rubric
make test-rag             # 双轨合并
make test-graph
make test-api
make test
```

紧急跳过 pre-commit：`SKIP_HOOKS=1 git commit ...`

## 边界

- **不要**在未读同步指南的情况下跨组件大改
- **不要**把 simulator 实现细节复制进 ops-agent 文档
- **不要**提交 `.env`、checkpoint、审计日志、Chroma 索引标记
- Java 参考服务（`bcs-*`、`lts-*` 等）在 monorepo 外维护，不在本仓库
