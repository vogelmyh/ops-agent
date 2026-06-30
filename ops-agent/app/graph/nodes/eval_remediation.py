"""Post-remediation verification: collect fresh telemetry and decide if incident is resolved."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.adapters.mock_remediation import is_remediated, mark_remediated
from app.config import get_settings
from app.graph.collection import collect, serialize_collected
from app.graph.eval_schemas import RemediationEvalAssessment
from app.graph.state import AgentState
from app.llm.provider import get_chat_model
from app.schemas import StreamStatus
from app.tools.policy import pending_tool_calls, tool_execution_results

REMEDIATION_EVAL_SYSTEM_PROMPT = """\
You are the post-remediation verification module of an ops agent.
Given pre-remediation context, executed write tools, and fresh post-remediation telemetry, \
decide whether the incident is resolved.

Set resolved=true only when telemetry clearly shows recovery (healthy status, metrics recovered, \
no ongoing ERROR symptoms aligned with the original root cause).

Set resolved=false when symptoms persist or recovery is ambiguous; list residual_symptoms.
"""


def _exec_succeeded(exec_results: list[dict]) -> bool:
    if not exec_results:
        return False
    last = exec_results[-1]
    status = str(last.get("status", "")).upper()
    if status in ("SUCCEEDED", "RUNNING"):
        return True
    return "mock" in str(last.get("message", "")).lower() or "recover" in str(last.get("message", "")).lower()


def _apply_mock_remediation(service: str, exec_results: list[dict]) -> None:
    if _exec_succeeded(exec_results):
        mark_remediated(service)


def _rule_based_resolved(service: str, data: dict) -> RemediationEvalAssessment | None:
    from app.adapters.mock_data import get_mock_scenario

    scenario = get_mock_scenario(service)
    status = data.get("status") or {}
    healthy = status.get("healthy", False)

    if service == "ecomm-manager" and scenario == "rate-limit":
        metrics = data.get("metrics") or {}
        points = metrics.get("points") or []
        last_qps = points[-1]["value"] if points else 0
        if healthy and last_qps >= 3000:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning=f"Admin API QPS recovered to {last_qps}; service healthy.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning=f"Rate limit issue persists; QPS still low ({last_qps}).",
            residual_symptoms=["admin API QPS degraded"],
        )

    if service == "ecomm-manager" and scenario == "feature-flag":
        metrics = data.get("metrics") or {}
        points = metrics.get("points") or []
        error_rate = points[-1]["value"] if points else 1.0
        if healthy and error_rate < 0.02:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning=f"Error rate normalized to {error_rate}.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning="Feature flag issue persists; error rate still elevated.",
            residual_symptoms=["elevated error rate"],
        )

    if service == "ecomm-manager" and scenario == "crashloop":
        ready = status.get("replicas_ready", 0)
        desired = status.get("replicas_desired", 0)
        if healthy and ready >= desired and ready > 0:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning=f"All {ready}/{desired} replicas ready after rollback.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning=f"Replicas not ready ({ready}/{desired}); CrashLoop may persist.",
            residual_symptoms=["pods not ready"],
        )

    if service == "ecomm-manager" and scenario == "disk-full":
        metrics = data.get("metrics") or {}
        points = metrics.get("points") or []
        disk = points[-1]["value"] if points else 100
        if healthy and disk < 60:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning=f"Disk usage dropped to {disk}%.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning="Disk pressure persists after cleanup attempt.",
            residual_symptoms=["disk usage high"],
        )

    if service == "ecomm-manager" and scenario == "chaos-exhaust":
        metrics = data.get("metrics") or {}
        metric_name = metrics.get("metric", "")
        points = metrics.get("points") or []
        value = points[-1]["value"] if points else 0
        if metric_name == "error_rate":
            return RemediationEvalAssessment(
                resolved=False,
                reasoning=(
                    f"Chaos exhaust: error_rate still {value}; "
                    "feature-flag remediation did not resolve incident."
                ),
                residual_symptoms=["elevated error rate", "PromotionService NPE"],
            )
        if metric_name == "admin_api_qps":
            return RemediationEvalAssessment(
                resolved=False,
                reasoning=(
                    f"Chaos exhaust phase A: admin_api_qps still {value}; "
                    "rate-limit patch required or ineffective."
                ),
                residual_symptoms=["admin API QPS degraded"],
            )

    if service == "ecomm-manager" and scenario == "chaos-oos":
        metrics = data.get("metrics") or {}
        metric_name = metrics.get("metric", "")
        points = metrics.get("points") or []
        value = points[-1]["value"] if points else 0
        if metric_name == "order_amount_error_rate":
            return RemediationEvalAssessment(
                resolved=False,
                reasoning=(
                    f"Chaos OOS: order_amount_error_rate still {value}; "
                    "application logic defect requires dev team."
                ),
                residual_symptoms=["order amount validation failures"],
            )
        if metric_name == "admin_api_qps":
            return RemediationEvalAssessment(
                resolved=False,
                reasoning=(
                    f"Chaos OOS phase A: admin_api_qps still {value}; "
                    "rate-limit patch required before logic-bug assessment."
                ),
                residual_symptoms=["admin API QPS degraded"],
            )

    if service == "ecomm-manager" and scenario == "chaos-morph":
        metrics = data.get("metrics") or {}
        metric_name = metrics.get("metric", "")
        points = metrics.get("points") or []
        value = points[-1]["value"] if points else 0
        if metric_name == "error_rate":
            if healthy and value < 0.02:
                return RemediationEvalAssessment(
                    resolved=True,
                    reasoning=f"Error rate normalized to {value} after feature-flag fix.",
                    residual_symptoms=[],
                )
            return RemediationEvalAssessment(
                resolved=False,
                reasoning=(
                    f"Chaos morph phase B: error_rate still {value}; "
                    "feature flag remediation required."
                ),
                residual_symptoms=["elevated error rate", "PromotionService NPE"],
            )
        if metric_name == "admin_api_qps":
            return RemediationEvalAssessment(
                resolved=False,
                reasoning=(
                    f"Chaos morph phase A: admin_api_qps still {value}; "
                    "rate-limit patch required or ineffective."
                ),
                residual_symptoms=["admin API QPS degraded"],
            )

    if service == "ecomm-order" and scenario == "crashloop":
        ready = status.get("replicas_ready", 0)
        desired = status.get("replicas_desired", 0)
        if healthy and ready >= desired and ready > 0:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning=f"All {ready}/{desired} replicas ready after rollback.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning=f"Replicas not ready ({ready}/{desired}); CrashLoop may persist.",
            residual_symptoms=["pods not ready"],
        )

    if service == "ecomm-order" and scenario == "stream-paused":
        streams = data.get("streams") or []
        paused = [s for s in streams if s.get("status") in (StreamStatus.PAUSED.value, "PAUSED")]
        metrics = data.get("metrics") or {}
        points = metrics.get("points") or []
        last_ingest = points[-1]["value"] if points else 0
        if not paused and last_ingest > 0:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning="Stream resumed and ingest bytes/sec recovered.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning="Stream still paused or zero ingest.",
            residual_symptoms=["stream paused or zero ingest"],
        )

    if service == "ecomm-order" and scenario == "memory-leak":
        metrics = data.get("metrics") or {}
        points = metrics.get("points") or []
        success = points[-1]["value"] if points else 0
        if healthy and success > 0.99:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning=f"Order success rate recovered to {success}.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning="OOM / connection pool symptoms persist.",
            residual_symptoms=["order success rate low"],
        )

    if service == "ecomm-order" and scenario == "payment-circuit":
        if is_remediated(service) or healthy:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning="Circuit breaker opened; payment storm contained.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning="Payment upstream errors persist.",
            residual_symptoms=["payment errors elevated"],
        )

    if service == "ecomm-cache":
        if is_remediated(service) or healthy:
            return RemediationEvalAssessment(
                resolved=True,
                reasoning="Rolling restart cleared OOMKilled pod; cache connections recovered.",
                residual_symptoms=[],
            )
        return RemediationEvalAssessment(
            resolved=False,
            reasoning="OOM / cache connection symptoms persist.",
            residual_symptoms=["cache read latency elevated"],
        )

    if healthy:
        return RemediationEvalAssessment(
            resolved=True,
            reasoning="Service status reports healthy after remediation.",
            residual_symptoms=[],
        )
    return RemediationEvalAssessment(
        resolved=False,
        reasoning="Service still unhealthy after remediation.",
        residual_symptoms=[status.get("message") or "service unhealthy"],
    )


def _format_post_context(service: str, data: dict, exec_results: list[dict], root_cause: str) -> str:
    status = data.get("status") or {}
    lines = [
        f"Service: {service}",
        f"Pre-remediation root cause: {root_cause}",
        f"Execution results: {exec_results}",
        f"Post-remediation healthy: {status.get('healthy')}",
        f"Post-remediation status message: {status.get('message')}",
    ]
    metrics = data.get("metrics")
    if metrics:
        points = metrics.get("points") or []
        if points:
            lines.append(f"Latest metric: {metrics.get('metric')}={points[-1].get('value')}")
    streams = data.get("streams")
    if streams:
        lines.append(f"Streams: {streams}")
    app_logs = data.get("app_logs") or {}
    entries = app_logs.get("entries") or []
    if entries:
        lines.append(f"Latest app log: [{entries[0].get('level')}] {entries[0].get('message')}")
    return "\n".join(lines)


def eval_remediation_node(state: AgentState) -> dict:
    settings = get_settings()
    service = state["service"]
    attempt = state.get("remediation_attempt", 0) + 1
    exec_results = tool_execution_results(state.get("messages", []))
    root_cause = state.get("root_cause", "")

    if settings.llm_is_mock and settings.backend_is_mock:
        _apply_mock_remediation(service, exec_results)

    post_data = collect(service)
    serialized_post = serialize_collected(post_data)

    if settings.llm_is_mock:
        assessment = _rule_based_resolved(service, serialized_post)
    else:
        llm = get_chat_model(settings=settings).with_structured_output(RemediationEvalAssessment)
        context = _format_post_context(service, serialized_post, exec_results, root_cause)
        assessment = llm.invoke([
            SystemMessage(content=REMEDIATION_EVAL_SYSTEM_PROMPT),
            HumanMessage(content=context),
        ])

    tools_attempted = [
        tc.get("name", "") for tc in pending_tool_calls(state.get("messages", [])) if tc.get("name")
    ]
    history_entry = {
        "attempt": attempt,
        "root_cause": root_cause,
        "tools_attempted": tools_attempted,
        "exec_results": exec_results,
        "resolved": assessment.resolved,
        "reasoning": assessment.reasoning,
        "residual_symptoms": assessment.residual_symptoms,
    }
    history = list(state.get("remediation_history", []))
    history.append(history_entry)

    return {
        "remediation_attempt": attempt,
        "incident_resolved": assessment.resolved,
        "remediation_eval_reasoning": assessment.reasoning,
        "remediation_history": history,
        "collected_data": serialized_post,
        "status": "remediation_evaluated",
    }
