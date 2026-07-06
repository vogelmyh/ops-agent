"""Diagnose node — coverage, RCA, confidence rubric, and routing gates."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.runbook_coverage import (
    evaluate_runbook_coverage,
)
from app.graph.diagnose_spec import (
    CONFIDENCE_SYSTEM_PROMPT,
    RCA_EXPLORE_SYSTEM_PROMPT,
    RCA_RUNBOOK_SYSTEM_PROMPT,
    DiagnosisConfidenceAssessment,
    RootCauseDraft,
    adopted_runbook_confidence_assessment,
    build_adopted_runbook_gate_reason,
    mock_confidence_assessment,
)
from app.graph.diagnosis_confidence_policy import (
    build_confidence_gate_reason,
    is_diagnostic_reliable,
    policy_from_settings as confidence_policy_from_settings,
)
from app.graph.eval_schemas import RunbookCandidate
from app.graph.remediation_context import RCA_RETRY_GUIDANCE, format_remediation_context
from app.graph.runbook_excerpt import excerpt_runbook
from app.graph.state import AgentState
from app.llm.provider import get_chat_model, invoke_structured
from app.schemas import Evidence, StreamStatus

SKIPPED_LOW_CONFIDENCE = "skipped_low_confidence"

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


def _candidates_from_state(state: AgentState) -> list[RunbookCandidate]:
    raw = state.get("runbook_candidates") or []
    return [RunbookCandidate.model_validate(item) for item in raw]


def _build_telemetry_context(service: str, description: str, data: dict) -> str:
    lines = [
        "## Incident",
        f"Service: {service}",
        f"Description: {description}",
    ]

    app_logs = data.get("app_logs")
    if app_logs:
        lines.append("\n## Application Logs")
        for entry in app_logs.get("entries", [])[:5]:
            lines.append(f"  [{entry['level']}] {entry['message']}")

    k8s_events = data.get("k8s_events")
    if k8s_events:
        lines.append("\n## K8s Events")
        for ev in k8s_events.get("events", [])[:4]:
            lines.append(
                f"  [{ev['type']}/{ev['reason']}] {ev['involved_object']}: {ev['message']}"
            )

    status = data.get("status")
    if status:
        lines.append("\n## Service Status")
        lines.append(
            f"  healthy={status['healthy']}, "
            f"{status['replicas_ready']}/{status['replicas_desired']} ready"
        )
        if status.get("message"):
            lines.append(f"  note: {status['message']}")

    metrics = data.get("metrics")
    if metrics:
        lines.append(f"\n## Metrics ({metrics['metric']})")
        for point in metrics.get("points", []):
            lines.append(f"  {point['timestamp']} → {point['value']} {metrics.get('unit', '')}")

    streams = data.get("streams")
    if streams:
        lines.append("\n## Event Streams")
        for stream in streams:
            lines.append(f"  {stream['project']}/{stream['stream']}: status={stream['status']}")

    op = data.get("operation")
    if op:
        lines.append("\n## Latest Operation")
        lines.append(f"  {op['action']}: {op['message']}")

    return "\n".join(lines)


def _citations_to_evidence(citations: list) -> list[Evidence]:
    return [
        Evidence(source=c.source, snippet=c.snippet, ref=c.ref)
        for c in citations
    ]


def _mock_root_cause(state: AgentState, service: str) -> str:
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
        return _MOCK_ROOT_CAUSES.get(phase_key, _MOCK_ROOT_CAUSES[key])
    return _MOCK_ROOT_CAUSES.get(key, f"Unknown root cause for service {service}")


def _build_evidence_from_data(service: str, data: dict, selected_doc_id: str | None) -> list[Evidence]:
    ev: list[Evidence] = []

    app_logs = data.get("app_logs")
    if app_logs and app_logs.get("entries"):
        ev.append(Evidence(
            source="app_logs",
            snippet=app_logs["entries"][0]["message"],
            ref=f"query_app_logs:{service}",
        ))

    k8s_events = data.get("k8s_events")
    if k8s_events and k8s_events.get("events"):
        first = k8s_events["events"][0]
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
    if metrics and metrics.get("points"):
        last = metrics["points"][-1]
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

    if selected_doc_id:
        ev.append(Evidence(
            source="runbook",
            snippet=f"Selected runbook {selected_doc_id}",
            ref=selected_doc_id,
        ))

    return ev


def _append_remediation_context(state: AgentState, context: str) -> str:
    prior_root = state.get("root_cause", "") if state.get("remediation_attempt", 0) >= 1 else None
    remediation_block = format_remediation_context(
        state,
        prior_root_cause=prior_root or None,
        extra_guidance=(
            RCA_RETRY_GUIDANCE if state.get("remediation_attempt", 0) >= 1 else None
        ),
    )
    if remediation_block:
        return f"{context}\n\n{remediation_block}"
    return context


def _run_rca_runbook_path(
    state: AgentState,
    *,
    service: str,
    incident_description: str,
    data: dict,
    relevant_runbook: str,
    settings,
) -> tuple[str, list[Evidence]]:
    if settings.llm_is_mock:
        root = _mock_root_cause(state, service)
        evidence = _build_evidence_from_data(
            service,
            data,
            state.get("selected_runbook_id"),
        )
        return root, evidence

    context = _build_telemetry_context(service, incident_description, data)
    context = (
        f"{context}\n\n## Validated Runbook Excerpt\n"
        f"{excerpt_runbook(relevant_runbook)}"
    )
    context = _append_remediation_context(state, context)

    draft = invoke_structured(
        get_chat_model(settings=settings),
        RootCauseDraft,
        [
            SystemMessage(content=RCA_RUNBOOK_SYSTEM_PROMPT),
            HumanMessage(content=context),
        ],
        settings=settings,
    )
    return draft.root_cause.strip(), _citations_to_evidence(draft.evidence)


def _run_rca_explore_path(
    state: AgentState,
    *,
    service: str,
    incident_description: str,
    data: dict,
    settings,
) -> tuple[str, list[Evidence]]:
    if settings.llm_is_mock:
        root = _mock_root_cause(state, service)
        evidence = _build_evidence_from_data(service, data, None)
        return root, evidence

    context = _build_telemetry_context(service, incident_description, data)
    context = _append_remediation_context(state, context)

    draft = invoke_structured(
        get_chat_model(settings=settings),
        RootCauseDraft,
        [
            SystemMessage(content=RCA_EXPLORE_SYSTEM_PROMPT),
            HumanMessage(content=context),
        ],
        settings=settings,
    )
    return draft.root_cause.strip(), _citations_to_evidence(draft.evidence)


def _run_confidence(
    *,
    service: str,
    root_cause: str,
    evidence: list[Evidence],
    settings,
) -> DiagnosisConfidenceAssessment:
    if settings.llm_is_mock:
        return mock_confidence_assessment(service)

    evidence_text = "\n".join(f"- [{e.source}] {e.snippet}" for e in evidence) or "(none)"
    return invoke_structured(
        get_chat_model(settings=settings),
        DiagnosisConfidenceAssessment,
        [
            SystemMessage(content=CONFIDENCE_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Service: {service}\n"
                f"Root cause:\n{root_cause}\n\n"
                f"Evidence:\n{evidence_text}"
            )),
        ],
        settings=settings,
    )


def diagnose_node(state: AgentState) -> dict:
    service = state["service"]
    incident = state["incident"]
    settings = get_settings()
    data = dict(state.get("collected_data") or {})
    coverage = evaluate_runbook_coverage(
        service,
        incident.description,
        collected_data=data,
        candidates=_candidates_from_state(state),
        settings=settings,
    )

    runbook_available = coverage["runbook_available"]
    relevant_runbook = coverage.get("relevant_runbook")
    selected_runbook_id = coverage.get("selected_runbook_id")

    if runbook_available and relevant_runbook:
        root_cause, evidence = _run_rca_runbook_path(
            state,
            service=service,
            incident_description=incident.description,
            data=data,
            relevant_runbook=relevant_runbook,
            settings=settings,
        )
        doc_id = selected_runbook_id or "unknown"
        confidence_assessment = adopted_runbook_confidence_assessment(doc_id)
        confidence_sufficient = True
        confidence_gate_reason = build_adopted_runbook_gate_reason(doc_id)
    else:
        root_cause, evidence = _run_rca_explore_path(
            state,
            service=service,
            incident_description=incident.description,
            data=data,
            settings=settings,
        )
        confidence_assessment = _run_confidence(
            service=service,
            root_cause=root_cause,
            evidence=evidence,
            settings=settings,
        )
        confidence_policy = confidence_policy_from_settings(settings)
        assessment_dict = confidence_assessment.as_dict()
        confidence_sufficient = is_diagnostic_reliable(
            assessment_dict,
            policy=confidence_policy,
        )
        confidence_gate_reason = build_confidence_gate_reason(
            assessment_dict,
            reliable=confidence_sufficient,
            policy=confidence_policy,
        )

    findings = []
    if data.get("app_logs"):
        findings.append({"source": "app_logs", "data": data["app_logs"]})
    if data.get("k8s_events"):
        findings.append({"source": "k8s_events", "data": data["k8s_events"]})
    if data.get("metrics"):
        findings.append({"source": "metrics", "data": data["metrics"]})

    out: dict = {
        **coverage,
        "root_cause": root_cause,
        "evidence": evidence,
        "findings": findings,
        "confidence_rubric": confidence_assessment.model_dump(),
        "confidence_gate_reason": confidence_gate_reason,
        "confidence_sufficient": confidence_sufficient,
        "status": "diagnosed",
    }

    if not confidence_sufficient:
        out["decide_outcome"] = SKIPPED_LOW_CONFIDENCE
        out["knowledge_gaps"] = [confidence_gate_reason]
        out["recommendations"] = [
            "Gather more telemetry or escalate to senior ops before automated remediation.",
        ]

    return out
