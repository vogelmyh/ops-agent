from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.remediation_context import format_remediation_context
from app.graph.state import AgentState
from app.llm.provider import get_chat_model
from app.schemas import Evidence, StreamStatus


def _build_evidence(service: str, data: dict) -> list[Evidence]:
    ev: list[Evidence] = []

    app_logs = data.get("app_logs")
    if app_logs:
        entries = app_logs.get("entries", [])
        if entries:
            ev.append(Evidence(
                source="app_logs",
                snippet=entries[0]["message"],
                ref=f"query_app_logs:{service}",
            ))

    k8s_events = data.get("k8s_events")
    if k8s_events:
        events = k8s_events.get("events", [])
        if events:
            first = events[0]
            ev.append(Evidence(
                source="k8s_events",
                snippet=f"[{first['reason']}] {first['message']}",
                ref=f"query_k8s_events:{service}",
            ))

    status = data.get("status")
    if status:
        ev.append(Evidence(
            source="status",
            snippet=(
                f"{status['replicas_ready']}/{status['replicas_desired']} ready, "
                f"healthy={status['healthy']}"
            ),
            ref=f"get_service_status:{service}",
        ))

    metrics = data.get("metrics")
    if metrics:
        points = metrics.get("points", [])
        if points:
            last = points[-1]
            ev.append(Evidence(
                source="metrics",
                snippet=f"{metrics['metric']}={last['value']} {metrics['unit']}",
                ref=f"get_metrics:{service}",
            ))

    streams = data.get("streams")
    if streams:
        paused = [s for s in streams if s.get("status") == StreamStatus.PAUSED.value]
        if paused:
            ev.append(Evidence(
                source="streams",
                snippet=(
                    f"stream {paused[0]['project']}/{paused[0]['stream']} "
                    f"status={paused[0]['status']}"
                ),
                ref=f"get_stream_states:{service}",
            ))

    op = data.get("operation")
    if op:
        ev.append(Evidence(
            source="operation",
            snippet=op["message"],
            ref=f"operation:{op['operation_id']}",
        ))

    runbooks = data.get("runbooks", [])
    if runbooks:
        ev.append(Evidence(
            source="runbook",
            snippet=runbooks[0]["content"][:200],
            ref=runbooks[0]["doc_id"],
        ))

    return ev


def _build_context(service: str, description: str, data: dict, relevant_runbook: str | None) -> str:
    lines = [
        "## Incident",
        f"Service: {service}",
        f"Description: {description}",
    ]

    app_logs = data.get("app_logs")
    if app_logs:
        lines.append("\n## Application Logs (log platform — business/runtime layer)")
        for e in app_logs.get("entries", [])[:5]:
            lines.append(f"  [{e['level']}] {e['message']}")

    k8s_events = data.get("k8s_events")
    if k8s_events:
        lines.append("\n## K8s Infrastructure Events (K8s API — kubelet/scheduler/controller)")
        for ev in k8s_events.get("events", [])[:4]:
            lines.append(
                f"  [{ev['type']}/{ev['reason']}] {ev['involved_object']}: {ev['message']}"
            )

    status = data.get("status")
    if status:
        lines.append("\n## Service Status (K8s resource snapshot)")
        lines.append(
            f"  healthy={status['healthy']}, "
            f"{status['replicas_ready']}/{status['replicas_desired']} ready"
        )
        if status.get("message"):
            lines.append(f"  note: {status['message']}")
        for pod in status.get("pods", [])[:3]:
            lines.append(
                f"  pod {pod['name']}: phase={pod['phase']}, "
                f"restarts={pod['restarts']}, image={pod['image']}"
            )

    metrics = data.get("metrics")
    if metrics:
        lines.append(f"\n## Key Metrics ({metrics['metric']}, unit={metrics['unit']})")
        for p in metrics.get("points", []):
            lines.append(f"  {p['timestamp']} → {p['value']}")

    streams = data.get("streams")
    if streams:
        lines.append("\n## Event Streams")
        for s in streams:
            lines.append(
                f"  {s['project']}/{s['stream']}: status={s['status']}, "
                f"last_ingest={s.get('last_ingest_at')}"
            )

    op = data.get("operation")
    if op:
        lines.append("\n## Latest Platform Operation (audit record)")
        lines.append(f"  action={op['action']}, status={op['status']}: {op['message']}")

    if relevant_runbook:
        lines.append("\n## Runbook Reference (LLM-evaluated as relevant)")
        lines.append(relevant_runbook[:1200])
    else:
        runbooks = data.get("runbooks", [])
        if runbooks:
            lines.append("\n## Runbook Reference (retrieved, not validated)")
            for rb in runbooks[:2]:
                score_note = f" [score={rb.get('score', '?')}]" if rb.get("score") else ""
                lines.append(f"  [{rb.get('title', '')}]{score_note}\n  {rb['content'][:400]}")

    return "\n".join(lines)


_MOCK_ROOT_CAUSES: dict[tuple[str, str], str] = {
    ("ecomm-manager", "rate-limit"): (
        "管理 API 限流阈值误配（max-qps=50 应为 5000），导致 admin API QPS 从约 8000 降至约 400。"
    ),
    ("ecomm-manager", "feature-flag"): (
        "功能开关 promotion-v2 灰度启用后触发 PromotionService NPE，管理 API 错误率升高。"
    ),
    ("ecomm-manager", "crashloop"): (
        "管理面升级到坏镜像 ecomm-manager:2.1.0-bad 导致全部 Pod CrashLoopBackOff，0/2 副本就绪。"
    ),
    ("ecomm-manager", "discount-bug"): (
        "DiscountEngine 折扣计算逻辑缺陷导致订单金额异常，属应用代码 Bug，非运维可修复问题。"
    ),
    ("ecomm-manager", "disk-full"): (
        "操作审计日志占满 /var/log/ecomm-manager，磁盘使用率 99%，写入失败。"
    ),
    ("ecomm-manager", "chaos-morph"): (
        "两阶段故障：限流误配掩盖 promotion-v2 功能开关 NPE（修复限流后暴露）。"
    ),
    ("ecomm-manager", "chaos-exhaust"): (
        "两阶段混沌：限流误配后暴露功能开关故障；catalog 工具无法彻底恢复 incident。"
    ),
    ("ecomm-manager", "chaos-oos"): (
        "两阶段混沌：限流误配后暴露 DiscountEngine 逻辑缺陷，超出运维工具能力。"
    ),
    ("ecomm-order", "crashloop"): (
        "数据面升级到坏镜像 ecomm-order:3.3.0-bad 导致全部 Pod CrashLoopBackOff，0/3 副本就绪。"
    ),
    ("ecomm-order", "stream-paused"): (
        "订单事件流 order-events 被人工暂停，控制面健康但库存同步停滞。"
    ),
    ("ecomm-order", "memory-leak"): (
        "下单服务在稳定镜像上出现 OOM 与连接池耗尽，需滚动重启恢复。"
    ),
    ("ecomm-order", "payment-circuit"): (
        "上游 payment-gw 连续超时导致支付 5xx 飙升，需打开熔断保护。"
    ),
    ("ecomm-order", "rds-timeout"): (
        "托管 RDS 连接超时导致订单持久化失败，属 PaaS 层问题，需 DBA 介入。"
    ),
    ("ecomm-cache", "default"): (
        "Redis 缓存 Pod 内存超限触发 OOMKilled，频繁重启导致缓存连接失败与读延迟飙升。"
    ),
}


def diagnose_node(state: AgentState) -> dict:
    service = state["service"]
    incident = state["incident"]
    settings = get_settings()
    data = dict(state.get("collected_data") or {})
    relevant_runbook = state.get("relevant_runbook")

    evidence = _build_evidence(service, data)

    if settings.llm_is_mock:
        from app.adapters.mock_data import get_mock_scenario

        key = (service, get_mock_scenario(service))
        scenario = get_mock_scenario(service)
        if key in (
            ("ecomm-manager", "chaos-morph"),
            ("ecomm-manager", "chaos-exhaust"),
            ("ecomm-manager", "chaos-oos"),
        ):
            if scenario == "chaos-oos" and state.get("remediation_attempt", 0) >= 1:
                phase_key = ("ecomm-manager", "discount-bug")
            elif state.get("remediation_attempt", 0) >= 1:
                phase_key = ("ecomm-manager", "feature-flag")
            else:
                phase_key = ("ecomm-manager", "rate-limit")
            root = _MOCK_ROOT_CAUSES.get(phase_key, _MOCK_ROOT_CAUSES[key])
        else:
            root = _MOCK_ROOT_CAUSES.get(key, f"Unknown root cause for service {service}")
    else:
        context = _build_context(service, incident.description, data, relevant_runbook)
        prior_root = state.get("root_cause", "") if state.get("remediation_attempt", 0) >= 1 else None
        remediation_block = format_remediation_context(state, prior_root_cause=prior_root or None)
        if remediation_block:
            context = f"{context}\n\n{remediation_block}"
        llm = get_chat_model(settings=settings)
        messages = [
            SystemMessage(content=(
                "You are a senior cloud operations engineer. "
                "You are given multi-source incident context: "
                "application logs (business/runtime layer), "
                "K8s infrastructure events (kubelet/scheduler/controller layer), "
                "service status, metrics, platform operation records, and runbooks. "
                "Write a concise root cause analysis in Chinese. "
                "Be specific: cite the exact error message, metric value, or misconfiguration. "
                "Use 2–4 sentences. Do not add remediation steps."
            )),
            HumanMessage(content=context),
        ]
        response = llm.invoke(messages)
        root = response.content.strip()

    findings = []
    if data.get("app_logs"):
        findings.append({"source": "app_logs", "data": data["app_logs"]})
    if data.get("k8s_events"):
        findings.append({"source": "k8s_events", "data": data["k8s_events"]})
    if data.get("metrics"):
        findings.append({"source": "metrics", "data": data["metrics"]})

    return {
        "root_cause": root,
        "evidence": evidence,
        "findings": findings,
        "status": "diagnosed",
    }
