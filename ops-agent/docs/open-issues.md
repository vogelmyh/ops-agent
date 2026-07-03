# 遗留问题（Open Issues）

> **用途**：记录已知但未关闭的问题。当你对 Agent 说 **「继续遗留问题」** 时，应读本文件并复述下列条目，供你规划处理方式。  
> **维护**：关闭某项后删除或标为已解决，并在对应组件文档变更记录中注明。

---

## 1. Real LLM 场景表征轨迹不稳定（`run_scenarios.py`）

**状态**：未解决（schema / env 硬崩已修，轨迹断言仍常失败）

**现象**（2026-07-03 联跑 `KB-01 KB-02 DEC-01 LOOP-02 LOOP-03 DEC-02`，`LLM_MODE=real`）：

| 场景 | 崩溃 | `passed` | 典型原因 |
|------|------|----------|----------|
| KB-01/02 | 否 | ✅ | 设计为 mock LLM，非 real 表征 |
| DEC-01 | 否 | ❌ | `decide_outcome=skipped_low_confidence`，非预期 `out_of_scope` |
| LOOP-02/03 | 否 | ❌ | 置信度 rubric `alternative_excluded=FAIL` → 跳过 decide，未进入修复环 |
| DEC-02 | 否 | ❌ | 同上或轨迹未满足断言 |

**根因方向**：

- Real LLM 置信度 rubric（尤其 `alternative_excluded`）偏严，与 mock oracle 行为不一致
- chaos-morph 场景 Phase A telemetry 与 rate-limit runbook 高度相似，LLM 易给出「足够具体」的 RCA 但 rubric 仍 FAIL
- DEC-01 discount-bug 静态 OOS 在 real LLM 下可能先被低置信门槛拦截

**可选处理方向**（待你决策）：

1. 调 `CONFIDENCE_SYSTEM_PROMPT`：runbook 四维 PASS 时放宽 `alternative_excluded`
2. 调 `diagnosis_confidence_threshold` / policy 权重
3. 为 DEC/LOOP 场景强化 simulator telemetry 区分度
4. 将 real LLM 表征改为「软断言 + 人工抽检」，与 mock graph_paths 契约分离

**相关文档**：`test-scenario-trajectories.md`、`graph-agent-architecture.md`、`decide-remediation-architecture.md`

---

## 2. KB 场景不参与 real LLM 表征

**状态**：已文档化（2026-07-03，方案 A）

`run_kb_01` / `run_kb_02` 在 `_isolated_mock_backend_env()` 内强制 mock LLM + mock backend，**设计为 mock smoke**，不随 `LLM_MODE=real` 改变。

**权威说明**：[`test-scenario-trajectories.md`](test-scenario-trajectories.md) §测试分层、§KB · run_scenarios 定位；`python scripts/run_scenarios.py --help`。

**若需 real KB**：另开 `--real-kb` 或隔离写回目录（未实现）。

---

## 3. Simulator 端口占用（本地并发）

**状态**：环境类，未代码修复

`make test-graph` / `run_scenarios` 时 8081、8083 若已被占用，uvicorn 线程报错但常复用已有实例。干净环境需先释放端口。

---

## 4. LangGraph checkpoint 反序列化警告

**状态**：低优先级

运行中出现 `Deserializing unregistered type app.schemas.IncidentInput/Evidence` 警告；未来 LangGraph 版本可能阻断。需配置 `allowed_msgpack_modules` 或 `LANGGRAPH_STRICT_MSGPACK`。

---

## 5. 工作区脏数据（勿提交）

**状态**：已清理（2026-07-03）

- `ops-agent/data/runbooks/*新故障场景.md` — `git restore` 恢复
- `ops-agent/data/repro_DEC-02.json` / `.stderr` — 已删除

KB 测试写回仍会改 runbook 文件；跑 `run_scenarios` KB 场景后注意 `git status`。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-03 | 初版：记录 real LLM 场景表征、KB mock 设计、端口占用、checkpoint 警告、脏数据 |
| 2026-07-03 | #5 脏数据已清理（restore runbooks + 删除 repro 产物） |
| 2026-07-03 | #2 KB mock smoke 分工已写入 test-scenario-trajectories / run_scenarios --help |
