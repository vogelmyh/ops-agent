from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.graph.state import AgentState
from app.llm.provider import get_chat_model
from app.tools.policy import tool_execution_results

# Align with Type A runbooks under data/runbooks/ecomm-*.md (7-section template).
_RUNBOOK_TEMPLATE = """\
# {title}

## 适用范围
- **仅适用于服务 `{service}`**。
- 不适用于本服务其它已知故障场景；若症状不匹配应重新检索 runbook。

## 症状
{symptoms}

## 诊断（先确认再动手）
{diagnosis}

## 根因
{root_cause}

## 处置（标准修复）
{remediation}

## 验证（修复后必须满足）
{verification}

## 勿用手段（易误判或无效）
{anti_patterns}

## 后续与升级
{escalation}
"""

DRAFT_RUNBOOK_SYSTEM_PROMPT = """\
You are an ops documentation engineer. Given incident context and human remediation notes, \
produce a runbook in Markdown that **strictly follows the repository template below**.

Required structure (use these exact `##` headings in this order; do not omit or rename):

```
# <中文标题，概括故障场景>

## 适用范围
- **仅适用于服务 `<service>`**。
- 列出不适用的其它典型场景（避免误用）。

## 症状
- 可观测症状列表（日志关键词、指标、K8s 状态等）。

## 诊断（先确认再动手）
1. 编号步骤，说明如何从日志/指标/状态确认根因。

## 根因
简明根因说明（1–3 句）。

## 处置（标准修复）
- 人工处置步骤或「超出 agent 自动化范围」说明。
- 若涉及标准 write tool，写明 tool 名、service、关键参数与风险级别。

## 验证（修复后必须满足）
- 修复后必须满足的验收条件（指标/日志/状态）。

## 勿用手段（易误判或无效）
- **不要**执行哪些易误判或无效的 write tool 及原因。

## 后续与升级
- 升级对象（on-call / 开发 / DBA 等）与触发条件。
```

Rules:
- Write in Chinese; keep steps executable and specific to the service.
- Start with a single `#` title line (not `##`).
- Do not use emoji, mermaid, or extra top-level sections.
- Base content on provided evidence and human notes; do not invent tools outside the catalog.
"""


def _mock_draft(state: AgentState) -> str:
    service = state.get("service", "unknown")
    notes = state.get("runbook_notes") or "人工处置完成"
    root = state.get("root_cause", "待确认")
    reasoning = state.get("match_gate_reason", "见 incident 证据")
    return _RUNBOOK_TEMPLATE.format(
        title=f"{service} 新故障场景",
        service=service,
        symptoms=reasoning,
        diagnosis="1. 对照应用日志、服务状态与指标，确认与本次 incident 证据一致。",
        root_cause=root,
        remediation=notes,
        verification="人工确认核心指标与日志恢复正常；agent 无自动化验收路径时写明需人工验证项。",
        anti_patterns="- **不要**在未确认根因前执行高风险 write tool（如 rollback_deployment）。",
        escalation="- 若处置后仍异常，升级至 senior ops 或对应服务 on-call。",
    )


def draft_runbook_node(state: AgentState) -> dict:
    settings = get_settings()
    service = state.get("service", "")
    notes = state.get("runbook_notes") or ""
    root = state.get("root_cause", "")
    reasoning = state.get("match_gate_reason", "")
    exec_results = tool_execution_results(state.get("messages", []))
    evidence_lines = "\n".join(f"- [{e.source}] {e.snippet}" for e in state.get("evidence", []))

    if settings.llm_is_mock:
        draft = _mock_draft(state)
    else:
        llm = get_chat_model(settings=settings)
        messages = [
            SystemMessage(content=DRAFT_RUNBOOK_SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Service: {service}\n"
                f"Eval reasoning: {reasoning}\n"
                f"Diagnosed root cause: {root}\n"
                f"Evidence:\n{evidence_lines or '(none)'}\n"
                f"Execution results: {exec_results or '(none)'}\n"
                f"Human remediation notes: {notes}"
            )),
        ]
        draft = llm.invoke(messages).content.strip()

    return {
        "runbook_draft": draft,
        "status": "runbook_drafted",
    }
