# Real LLM E2E 演示方案

> **定位**：现场 walkthrough 用的 **纯 real LLM** 旁白演示（CLI）。  
> **与测试的关系**：`run_scenarios.py` 做表征与硬断言；`run_demo.py` 做叙事与软检查（偏离预期时 warning，不中断演示）。

## 快速开始

```bash
cd ops-agent
# 标准五幕（默认；DEMO-02 处按 Enter 批准 HITL）
CHECKPOINTER=memory LLM_MODE=real BACKEND_MODE=real \
  python scripts/run_demo.py --profile standard

# 含高难度分层耗尽
python scripts/run_demo.py --profile full

# 完整版 + 熔断器非常规工具
python scripts/run_demo.py --profile full+

# 附录：知识写回（mock LLM，按需）
python scripts/run_demo.py --profile standard --appendix

# 列出所有 profile
python scripts/run_demo.py --list
```

报告写入 `data/demo_runs/run_demo_<utc>.json`（已 gitignore）。

## Profile 一览

| Profile | 幕次 | 约耗时 | 用途 |
|---------|------|--------|------|
| `short` | DEMO-01, 03, 04 | ~1 min | 电梯演讲 |
| `standard` | DEMO-01 … 05 | ~3 min | **默认推荐** |
| `full` | standard + DEMO-H1 | ~4.5 min | 能力 + 鲁棒性 |
| `full+` | full + DEMO-H2a | ~5 min | 完整版 |
| `appendix` | DEMO-KB-01/02 | ~5s | 仅知识写回（mock） |

## 标准五幕（standard）

| 幕 | ID | 路径 | Simulator | 展示要点 |
|----|-----|------|-----------|----------|
| 1 | DEMO-01 | P1 REM | `ecomm-order-stream-paused` | 低风险 auto-write → 恢复 |
| 2 | DEMO-02 | P2 REM+HITL | `ecomm-manager-crashloop` | **Enter 暂停** → rollback |
| 3 | DEMO-03 | P4 LOOP | `ecomm-manager-chaos-morph` | morph + 两轮工具恢复 |
| 4 | DEMO-04 | P3 DEC | `ecomm-manager-discount-bug` | 静态 out_of_scope |
| 5 | DEMO-05 | P3/P4 DEC | `ecomm-manager-chaos-oos` | morph 后 early OOS |

## 高难度幕

| 幕 | ID | Simulator | 展示要点 |
|----|-----|-----------|----------|
| H1 | DEMO-H1 | `ecomm-manager-cascade-exhaust` | 3 轮 react 耗尽，末态 CONN_LEAK |
| H2a | DEMO-H2a | `ecomm-order-payment-circuit` | `enable_circuit_breaker` 非常规工具 |

## 附录（mock LLM）

| 幕 | ID | 说明 |
|----|-----|------|
| KB-1 | DEMO-KB-01 | novel + 低置信 → runbook 写回 HITL |
| KB-2 | DEMO-KB-02 | novel + 高置信 → 修复后写回 |

附录会修改 `data/runbooks/`，演示后请 `git status` 检查。

## 与现有脚本分工

| 脚本 | LLM | 输出 | 用途 |
|------|-----|------|------|
| `scripts/demo.py` | mock | 简短打印 | 离线零 API 预热 |
| `scripts/run_demo.py` | **real**（附录 mock） | **旁白 + 软检查** | E2E 演示 |
| `scripts/run_scenarios.py` | DEC/LOOP real | JSON 报告 + 硬断言 | CI / 表征回归 |

## 演示前检查

1. `.env` 已配置 `OPENAI_*` / `EMBEDDINGS_PROVIDER`
2. 脚本会自动启动并复用单个 simulator（`:8081`）；结束时关闭自启进程。若端口已被外部 uvicorn 占用，将复用该实例且不强行杀进程
3. 预演：`python scripts/run_demo.py --profile standard`
4. LangSmith 可选：`LANGSMITH_TRACING=true`

## 变更记录

### 2026-07-07 · 初版 real LLM 演示脚本

- 新增 `scripts/run_demo.py`、`scripts/scenario_runtime.py`
- Profile：`short` / `standard` / `full` / `full+`；附录 `--appendix`
- DEMO-02 保留一次 Enter HITL 暂停；其余审批自动通过
