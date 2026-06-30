# 后端适配层 — 架构与测试

> **读者**：开发者 + Cursor Agent。  
> **总览**：[`architecture.md`](architecture.md)  
> **Simulator 实现细节**：[`ops-backend-simulator/README.md`](../../ops-backend-simulator/README.md)（单一事实来源，本文不复制场景表与 `apply_ops` 实现）

---

## 1. 职责

为 Agent 提供 **统一的遥测读取与写操作 HTTP 契约**，屏蔽 mock / Java 后端 / Python simulator：

- **读路径**：logs、metrics、status、k8s_events、deployments 等（供 `collection.collect`）
- **写路径**：运维写工具 → `OperationResult`
- **mock 数据**：离线 CI 与 `graph_paths` 默认依赖 `mock_data` / `mock_remediation`

---

## 2. 流程

```text
collection.collect / write_tools
        │
        ▼
  backend_client (按 BACKEND_MODE 分支)
        │
   ┌────┴────┐
   ▼         ▼
 mock      real HTTP
(mock_data) (BACKEND_BASE_URL)
```

### 2.1 模式

| `BACKEND_MODE` | 行为 |
|----------------|------|
| `mock` | 内存/文件型 `mock_data`，与 `set_mock_scenario(service, key)` 联动 |
| `real` | HTTP 调用 `BACKEND_BASE_URL`（Java ops-backend 或 **ops-backend-simulator**） |

### 2.2 mock 与 simulator 分工

| 用途 | 推荐 |
|------|------|
| `tests/graph_paths/`、快速 CI | `mock` + `mock_data` |
| write → read 闭环、混沌场景、真实 LLM 表征 | `real` + **simulator** |
| 生产契约验证 | `real` + Java `ops-backend` |

**注意**：simulator 的 `SCENARIO_ID`（如 `ecomm-manager-chaos-exhaust`）与 ops-agent 测试 ID（如 `LOOP-03`）不是同一命名空间；mock LLM 联调 simulator 时还需 `set_mock_scenario(service, "<short-key>")`。详见 simulator README § Relationship to ops-agent tests。

---

## 3. 代码映射

| 模块 | 路径 |
|------|------|
| 客户端入口 | `app/adapters/backend_client.py` |
| 遥测 schema | `app/adapters/schemas.py`（或 `app/schemas` 中相关模型） |
| mock 读 | `app/adapters/mock_data.py` |
| mock 写后状态 | `app/adapters/mock_remediation.py` |
| 采集聚合 | `app/graph/collection.py` |

---

## 4. 配置

| 变量 | 默认 | 说明 |
|------|------|------|
| `BACKEND_MODE` | `mock` | `mock` \| `real` |
| `BACKEND_BASE_URL` | `http://localhost:8080` | real 模式基址 |

Simulator 本地常用：`http://127.0.0.1:8081`（以 simulator 启动端口为准）。

---

## 5. Simulator 联调（ops-agent 视角）

> 场景脚本、故障类型、`apply_ops` 契约、新增 scenario 清单 → **[ops-backend-simulator/README.md](../../ops-backend-simulator/README.md)**

### 5.1 启动顺序

```bash
# 终端 1 — simulator
cd ops-backend-simulator
pip install -e ".[dev]"
SCENARIO_ID=ecomm-manager-rate-limit uvicorn simulator.main:app --port 8081

# 终端 2 — ops-agent
cd ops-agent
export BACKEND_MODE=real
export BACKEND_BASE_URL=http://127.0.0.1:8081
export LLM_MODE=real   # 或 mock + set_mock_scenario
uvicorn app.main:app --port 8000
```

### 5.2 切换场景

在 simulator 侧设置 `SCENARIO_ID` 或调用其 `/admin/reset`（见 simulator README）。ops-agent 侧：

- **real LLM 表征**：`scripts/run_scenarios.py` 按场景配置 service / description
- **mock LLM**：除 `BACKEND_MODE=real` 外，在测试或脚本中 `set_mock_scenario("ecomm-manager", "rate-limit")` 等与 simulator 世界对齐

### 5.3 联调验收点

1. **写前读**：`/diagnose` 后 `collected_data` 呈 BROKEN 态证据  
2. **写工具**：`execution_results` 含 `SUCCEEDED` / `FAILED`  
3. **写后读**：`eval_remediation` 所用遥测反映新状态（recoverable 场景应可 `incident_resolved=true`）

### 5.4 何时不需要 simulator

以下在 ops-agent **mock 后端**即可覆盖，无需起 simulator：

- 纯 RAG / KB / HITL 闸门 / `block_remediation` 图路径  
- 仅需 decide 路由、不验证写后遥测变化的用例  

与 simulator README「Decide if you need Simulator at all」一致。

---

## 6. 测试

### 6.1 本组件测什么

- **mock_data** 与 `collection` 字段完整性（各 service 投影一致）
- **mock_remediation** 写后状态是否与 `eval_remediation` 预期一致
- **real 模式**：通常通过 integration / `run_scenarios` + 运行中的 simulator 间接验证，不在 ops-agent 内复制 simulator 单测

### 6.2 测试入口

| 位置 | 说明 |
|------|------|
| `tests/graph_paths/` | 默认 `BACKEND_MODE=mock` |
| `tests/test_integration*.py` | 可选 real 后端 |
| `ops-backend-simulator/tests/` | simulator 自身契约与场景 |

---

## 7. Agent 改动同步指南

**通用要求**：每次合入修改后，在本文 **§10 版本注记** 追加一条修改摘要（日期 + 改动范围 + 关键行为变化）。

| 改动 | 必做 |
|------|------|
| **新读 API 字段** | `schemas` + `backend_client` + `mock_data` 投影 + `collection` |
| **新写工具 action** | `write_tools` + `mock_remediation`；若需 stateful E2E → simulator 新 scenario 模块（README 清单） |
| **新 service** | `mock_data` 键；是否加入 simulator 按「是否需要 write→read」决定 |
| **文档** | 联调步骤只维护本文 §5；实现细节只改 simulator README |

---

## 8. 验证命令

```bash
# mock 路径（CI）
.venv/bin/pytest tests/graph_paths/ -q

# simulator 冒烟（需先起 simulator）
BACKEND_MODE=real BACKEND_BASE_URL=http://127.0.0.1:8081 \
  CHECKPOINTER=memory .venv/bin/python scripts/run_scenarios.py --scenarios REM-01
```

---

## 9. 交叉引用

- 写工具与验收：[`decide-remediation-architecture.md`](decide-remediation-architecture.md)
- 采集调用方：[`graph-agent-architecture.md`](graph-agent-architecture.md)
- Simulator 实现：[`ops-backend-simulator/README.md`](../../ops-backend-simulator/README.md)
- 场景目录：[`test-scenario-trajectories.md`](test-scenario-trajectories.md)

---

## 10. 版本注记

（暂无组件级变更；合入 mock/adapter/simulator 联调相关修改时在此追加摘要。）
