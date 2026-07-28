"""Demo script catalog (7 main acts for interactive presenter)."""

from __future__ import annotations

from dataclasses import dataclass

from demo_presenter import console, graph_art

PRESENT_ACT_IDS: tuple[str, ...] = (
    "DEMO-01",
    "DEMO-02",
    "DEMO-03",
    "DEMO-04",
    "DEMO-05",
    "DEMO-H1",
    "DEMO-H2a",
)


@dataclass(frozen=True)
class ActRuntime:
    act_id: str
    title: str
    subtitle: str
    path_shape: str
    simulator_id: str
    mock_service: str
    mock_scenario: str
    service: str
    description: str
    ops_story: str
    pause_before_approve: bool = False


ACT_RUNTIME: dict[str, ActRuntime] = {
    "DEMO-01": ActRuntime(
        "DEMO-01",
        "低风险直达修复",
        "订单事件流暂停 → resume_event_stream",
        "P1 · REM",
        "ecomm-order-stream-paused",
        "ecomm-order",
        "stream-paused",
        "ecomm-order",
        "【P1】订单事件流无数据，下游履约延迟",
        "Simulator 注入 stream-paused；Agent 应选 resume_event_stream 低风险工具。",
    ),
    "DEMO-02": ActRuntime(
        "DEMO-02",
        "高风险 HITL 审批",
        "CrashLoop → rollback_deployment",
        "P2 · REM + HITL",
        "ecomm-manager-crashloop",
        "ecomm-manager",
        "crashloop",
        "ecomm-manager",
        "【P1】ecomm-manager 0/2 Ready，Pod CrashLoopBackOff",
        "Deployment 异常；rollback_deployment 为高风险，演示人审断点。",
        pause_before_approve=True,
    ),
    "DEMO-03": ActRuntime(
        "DEMO-03",
        "Morph 两级修复",
        "限流表象 → 功能开关根因",
        "P4 · LOOP",
        "ecomm-manager-chaos-morph",
        "ecomm-manager",
        "chaos-morph",
        "ecomm-manager",
        "【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
        "第一层限流表象，修复后 morph 暴露 feature flag 根因。",
    ),
    "DEMO-04": ActRuntime(
        "DEMO-04",
        "静态诚实拒执",
        "应用逻辑缺陷 → out_of_scope",
        "P3 · DEC",
        "ecomm-manager-discount-bug",
        "ecomm-manager",
        "discount-bug",
        "ecomm-manager",
        "【P1】ecomm-manager 商家反馈订单金额异常，后台 5xx 与金额校验告警增多",
        "逻辑 bug 不可运维修复；应 out_of_scope，simulator 保持 BROKEN。",
    ),
    "DEMO-05": ActRuntime(
        "DEMO-05",
        "Morph 后拒执",
        "修复表象后暴露逻辑 bug",
        "P3/P4 · DEC",
        "ecomm-manager-chaos-oos",
        "ecomm-manager",
        "chaos-oos",
        "ecomm-manager",
        "【P1】ecomm-manager 商家后台 QPS 下降，修复后订单金额校验告警增多",
        "先执行一轮修复，morph 后 decide 应诚实拒执。",
    ),
    "DEMO-H1": ActRuntime(
        "DEMO-H1",
        "分层故障耗尽",
        "三层 write + 末态连接泄漏",
        "P4 · LOOP (hard)",
        "ecomm-manager-cascade-exhaust",
        "ecomm-manager",
        "cascade-exhaust",
        "ecomm-manager",
        "【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
        "多轮修复仍无法恢复；remediation_attempt 耗尽后以 summarize 收束。",
    ),
    "DEMO-H2a": ActRuntime(
        "DEMO-H2a",
        "熔断器非常规工具",
        "payment-gw → enable_circuit_breaker",
        "P1 · REM (hard)",
        "ecomm-order-payment-circuit",
        "ecomm-order",
        "payment-circuit",
        "ecomm-order",
        "【P1】ecomm-order 支付链路超时激增，下单成功率跌至 45%",
        "非常规 enable_circuit_breaker 工具；低风险直达修复。",
    ),
}


def menu_choices() -> dict[str, str]:
    return {aid: f"{aid} · {ACT_RUNTIME[aid].title}" for aid in PRESENT_ACT_IDS}


def pick_act() -> str | None:
    console.heading("剧本目录 (C)")
    choice = console.prompt_choice("选择剧本编号", menu_choices())
    return choice


def show_detail(act_id: str) -> None:
    spec = ACT_RUNTIME[act_id]
    console.heading(f"{spec.act_id} · {spec.title}")
    print(f"  {spec.subtitle}")
    print(f"  路径形态: {spec.path_shape}")
    print(f"  Simulator: {spec.simulator_id}")
    print(f"  告警: {spec.description}")
    print(f"  运维故事: {spec.ops_story}")
    expected = graph_art.EXPECTED_PATHS.get(act_id, [])
    print(f"\n  预期路径:\n    {graph_art.render_path(expected)}")


def confirm_start() -> bool:
    return console.prompt_yes_no("开始运行此剧本？", default=True)
