# Interactive Demo Presenter（`make demo-real`）

> **定位**：现场 **交互式** real LLM 演示（五阶段 A–E），默认 `make demo-real`。  
> **批量旁白模式**（旧行为）：`make demo-real-auto` → `run_demo.py --profile standard --auto`。  
> **与测试的关系**：`run_scenarios.py` 硬断言；presenter 做流式旁白 + 路径 recap，软检查不阻断演示。

## 快速开始

```bash
# 交互式演示（默认推荐）
make demo-real

# 旧版连跑五幕（非交互）
make demo-real-auto

# 列出 batch profile（--auto 模式）
cd agent && python scripts/run_demo.py --list
```

前置：在 `agent/.env` 配置 `OPENAI_*` / `EMBEDDINGS_PROVIDER`；脚本自动在 `:8081` 启动或复用 simulator。

## 五阶段流程

| 阶段 | 名称 | 行为 |
|------|------|------|
| **A** | Bootstrap | 打印 LLM / embeddings / backend / checkpointer 配置 |
| **B** | Simulator Lab | 探查 health、admin state、手动 `POST /api/v1/ops/{action}` |
| **C** | Catalog | 7 个剧本菜单（DEMO-01…05、H1、H2a），展示预期 ASCII 路径 |
| **D** | Act Run | 告警 Y/N → `stream_mode=updates` 节点旁白 → 断点 Enter / HITL Y/N |
| **E** | Recap | 实际路径 vs 预期路径对比 |

每跑完一幕返回目录，可继续选下一幕或退出。

## 剧本目录（7 幕）

与 [`demo-scenarios.md`](demo-scenarios.md) 中 standard + 高难度幕一致，不含 KB 附录（附录仍用 `--auto --appendix`）。

| ID | 路径形态 | HITL 交互 |
|----|----------|-----------|
| DEMO-01 | P1 REM | 自动批准 |
| DEMO-02 | P2 REM+HITL | **Y/N 人审** |
| DEMO-03 | P4 LOOP | 自动批准 |
| DEMO-04 | P3 DEC | — |
| DEMO-05 | P3/P4 DEC | — |
| DEMO-H1 | P4 LOOP (hard) | 自动批准 |
| DEMO-H2a | P1 REM (hard) | 自动批准 |

## 旁白阶段标签

流式节点更新时打印：

`[采集]` `[RAG·检索]` `[诊断]` `[决策]` `[人审]` `[执行]` `[验收]` `[总结]`

实现：`scripts/demo_presenter/narrator.py` + `app/graph/runner.py` 的 `stream_diagnosis` / `stream_resume`（**不修改**图节点业务逻辑）。

## 代码布局

```
agent/scripts/
  run_demo.py              # CLI：默认 --present；--auto 保留 batch
  scenario_runtime.py      # SimulatorSession + lab HTTP helpers
  demo_presenter/
    present.py             # 主循环 A–E
    bootstrap.py           # Phase A
    simulator_lab.py       # Phase B
    catalog.py             # Phase C
    act_runner.py          # Phase D/E
    narrator.py            # stream 旁白
    graph_art.py           # 预期/实际路径 ASCII
    breakpoints.py         # Enter / HITL 断点
```

## 与 batch 模式分工

| 命令 | 模式 | 输出 |
|------|------|------|
| `make demo-real` | `--present` 交互 | 单幕 + 目录循环 |
| `make demo-real-auto` | `--auto --profile standard` | 五幕连跑 + JSON 报告 |
| `run_demo.py --profile full --auto` | batch | 含 H1 等扩展幕 |

Batch 报告仍写入 `data/demo_runs/run_demo_<utc>.json`。

## 变更记录

### 2026-07-08 · 交互式 demo presenter

- 新增 `scripts/demo_presenter/` 与 `stream_diagnosis` / `stream_resume`
- `make demo-real` 改为交互式；`make demo-real-auto` 保留旧连跑
- `scenario_runtime` 增加 lab HTTP helpers
