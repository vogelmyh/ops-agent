#!/usr/bin/env python3
"""Real LLM E2E demo with CLI narration (walkthrough).

Profiles:
  short     — DEMO-01, DEMO-03, DEMO-04
  standard  — DEMO-01 … DEMO-05 (default; one Enter pause at DEMO-02 HITL)
  full      — standard + DEMO-H1 (cascade exhaust)
  full+     — full + DEMO-H2a (payment circuit breaker)

Appendix (mock LLM, on demand):
  appendix  — DEMO-KB-01, DEMO-KB-02
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "ops-backend-simulator"))

from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"), override=True)
os.environ.setdefault("LLM_MODE", "real")
os.environ.setdefault("CHECKPOINTER", "memory")

from app.config import get_settings
from app.graph.runner import resume_approval, start_diagnosis
from app.schemas import IncidentInput

import scenario_runtime as rt
from run_scenarios import check_dec_01_passed, run_kb_01, run_kb_02

DEMO_REPORT_DIR = Path(ROOT) / "data" / "demo_runs"

PROFILES: dict[str, list[str]] = {
    "short": ["DEMO-01", "DEMO-03", "DEMO-04"],
    "standard": ["DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05"],
    "full": ["DEMO-01", "DEMO-02", "DEMO-03", "DEMO-04", "DEMO-05", "DEMO-H1"],
    "full+": [
        "DEMO-01",
        "DEMO-02",
        "DEMO-03",
        "DEMO-04",
        "DEMO-05",
        "DEMO-H1",
        "DEMO-H2a",
    ],
    "appendix": ["DEMO-KB-01", "DEMO-KB-02"],
}

ALL_ACT_IDS = sorted({aid for acts in PROFILES.values() for aid in acts})


@dataclass(frozen=True)
class DemoActSpec:
    act_id: str
    title: str
    subtitle: str
    path_shape: str
    pause_before_approve: bool = False
    uses_mock_llm: bool = False


ACT_SPECS: dict[str, DemoActSpec] = {
    "DEMO-01": DemoActSpec(
        "DEMO-01",
        "低风险直达修复",
        "订单事件流暂停 → resume_event_stream",
        "P1 · REM",
    ),
    "DEMO-02": DemoActSpec(
        "DEMO-02",
        "高风险 HITL 审批",
        "CrashLoop → rollback_deployment",
        "P2 · REM + HITL",
        pause_before_approve=True,
    ),
    "DEMO-03": DemoActSpec(
        "DEMO-03",
        "Morph 两级修复",
        "限流表象 → 功能开关根因",
        "P4 · LOOP",
    ),
    "DEMO-04": DemoActSpec(
        "DEMO-04",
        "静态诚实拒执",
        "应用逻辑缺陷 → out_of_scope",
        "P3 · DEC",
    ),
    "DEMO-05": DemoActSpec(
        "DEMO-05",
        "Morph 后拒执",
        "修复表象后暴露逻辑 bug",
        "P3/P4 · DEC",
    ),
    "DEMO-H1": DemoActSpec(
        "DEMO-H1",
        "分层故障耗尽",
        "三层 write + 末态连接泄漏",
        "P4 · LOOP (hard)",
    ),
    "DEMO-H2a": DemoActSpec(
        "DEMO-H2a",
        "熔断器非常规工具",
        "payment-gw → enable_circuit_breaker",
        "P1 · REM (hard)",
    ),
    "DEMO-KB-01": DemoActSpec(
        "DEMO-KB-01",
        "附录 · 低置信写回",
        "novel + skipped_low_confidence → runbook HITL",
        "P5 · KB",
        uses_mock_llm=True,
    ),
    "DEMO-KB-02": DemoActSpec(
        "DEMO-KB-02",
        "附录 · 修复后写回",
        "novel + actionable → 写回 KB",
        "P5 · KB",
        uses_mock_llm=True,
    ),
}


@dataclass
class DemoActResult:
    act_id: str
    elapsed_s: float
    thread_id: str | None
    warnings: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


def _banner(act_index: int, act_total: int, spec: DemoActSpec, simulator_id: str | None) -> None:
    line = "═" * 39
    print(f"\n{line}")
    print(f"  Act {act_index}/{act_total} · {spec.act_id} · {spec.title}")
    if simulator_id:
        print(f"  Simulator: {simulator_id}")
    print(f"  {spec.subtitle}  ({spec.path_shape})")
    if spec.uses_mock_llm:
        print("  [附录] Mock LLM + Mock backend")
    print(line)


def _short(text: str | None, limit: int = 160) -> str:
    if not text:
        return "(none)"
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _narrate_response(resp, *, phase: str) -> None:
    print(f"[{phase}] status={resp.status}")
    if resp.selected_runbook_id:
        print(f"[{phase}] selected_runbook: {resp.selected_runbook_id}")
    if resp.root_cause:
        print(f"[{phase}] root_cause: {_short(resp.root_cause)}")
    if resp.decide_outcome:
        print(f"[{phase}] decide_outcome: {resp.decide_outcome}")
    for op in resp.execution_results or []:
        msg = op.get("message") if isinstance(op, dict) else getattr(op, "message", "")
        action = op.get("action") if isinstance(op, dict) else getattr(op, "action", "")
        status = op.get("status") if isinstance(op, dict) else getattr(op, "status", "")
        print(f"[{phase}] exec {action}: {status} — {_short(msg, 100)}")
    if resp.incident_resolved is not None:
        print(f"[{phase}] incident_resolved: {resp.incident_resolved}")
    for tc in resp.pending_tool_calls or []:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        risk = tc.get("risk_level") if isinstance(tc, dict) else getattr(tc, "risk_level", "")
        print(f"[{phase}] pending_tool: {name} (risk={risk})")


def _maybe_pause(spec: DemoActSpec, resp) -> None:
    if resp.status != "awaiting_approval":
        return
    pending = resp.pending_tool_calls or []
    tool = pending[0].get("name") if pending and isinstance(pending[0], dict) else "?"
    if spec.pause_before_approve:
        print(f"⏸  等待审批 — 建议工具: {tool}")
        input("   按 Enter 批准并继续… ")
    else:
        print(f"[HITL] 自动批准: {tool}")


def _finish_act(spec: DemoActSpec, t0: float, thread_id: str | None, warnings: list[str], **payload) -> DemoActResult:
    elapsed = round(time.time() - t0, 1)
    mark = "⚠" if warnings else "✓"
    print(f"{mark} 本幕完成 ({elapsed}s)")
    for w in warnings:
        print(f"   ⚠ {w}")
    return DemoActResult(
        act_id=spec.act_id,
        elapsed_s=elapsed,
        thread_id=thread_id,
        warnings=warnings,
        payload=payload,
    )


def _run_rem_stream_paused(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-order-stream-paused",
        mock_service="ecomm-order",
        mock_scenario="stream-paused",
    )
    incident = IncidentInput(
        service="ecomm-order",
        description="【P1】订单事件流无数据，下游履约延迟",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    _narrate_response(resp, phase="诊断")
    warnings: list[str] = []
    if resp.status == "awaiting_approval":
        _maybe_pause(spec, resp)
        resp = resume_approval(thread_id, approved=True)
        _narrate_response(resp, phase="审批后")
    sim = client.get("/admin/state").json()
    actions = [e.get("action") for e in (resp.execution_results or [])]
    if "resume_event_stream" not in actions:
        warnings.append(f"expected resume_event_stream in execution_results, got {actions}")
    if resp.incident_resolved is not True:
        warnings.append("expected incident_resolved=true")
    if sim.get("phase") != "RECOVERED":
        warnings.append(f"simulator phase={sim.get('phase')!r}, expected RECOVERED")
    return _finish_act(spec, t0, thread_id, warnings, simulator_final=sim, meta=meta)


def _run_rem_crashloop(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-manager-crashloop",
        mock_service="ecomm-manager",
        mock_scenario="crashloop",
    )
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 0/2 Ready，Pod CrashLoopBackOff",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    _narrate_response(resp, phase="诊断")
    warnings: list[str] = []
    if resp.status != "awaiting_approval":
        warnings.append(f"expected awaiting_approval, got {resp.status}")
    else:
        _maybe_pause(spec, resp)
        resp = resume_approval(thread_id, approved=True)
        _narrate_response(resp, phase="审批后")
    sim = client.get("/admin/state").json()
    actions = [e.get("action") for e in (resp.execution_results or [])]
    if "rollback_deployment" not in actions:
        warnings.append(f"expected rollback_deployment, got {actions}")
    if resp.incident_resolved is not True:
        warnings.append("expected incident_resolved=true after rollback")
    return _finish_act(spec, t0, thread_id, warnings, simulator_final=sim, meta=meta)


def _run_loop_morph(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-manager-chaos-morph",
        mock_service="ecomm-manager",
        mock_scenario="chaos-morph",
    )
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    _narrate_response(resp, phase="第1轮")
    warnings: list[str] = []
    guard = 0
    while resp.status == "awaiting_approval" and guard < 6:
        _maybe_pause(spec, resp)
        resp = resume_approval(thread_id, approved=True)
        _narrate_response(resp, phase=f"审批后-{guard + 1}")
        guard += 1
    sim = client.get("/admin/state").json()
    if resp.incident_resolved is not True:
        warnings.append("expected incident_resolved=true")
    if sim.get("phase") != "RECOVERED":
        warnings.append(f"simulator phase={sim.get('phase')!r}")
    return _finish_act(spec, t0, thread_id, warnings, simulator_final=sim, meta=meta)


def _run_dec_static_oos(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-manager-discount-bug",
        mock_service="ecomm-manager",
        mock_scenario="discount-bug",
    )
    sim_before = client.get("/admin/state").json()
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家反馈订单金额异常，后台 5xx 与金额校验告警增多",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    sim_after = client.get("/admin/state").json()
    _narrate_response(resp, phase="决策")
    warnings: list[str] = []
    if not check_dec_01_passed(resp, meta, sim_before=sim_before, sim_after=sim_after):
        warnings.append("DEC-01 soft-check failed (out_of_scope, no writes, simulator BROKEN)")
    return _finish_act(spec, t0, thread_id, warnings, simulator_after=sim_after, meta=meta)


def _run_dec_morph_oos(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-manager-chaos-oos",
        mock_service="ecomm-manager",
        mock_scenario="chaos-oos",
    )
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 QPS 下降，修复后订单金额校验告警增多",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    sim = client.get("/admin/state").json()
    _narrate_response(resp, phase="决策")
    warnings: list[str] = []
    if resp.decide_outcome != "out_of_scope":
        warnings.append(f"expected out_of_scope, got {resp.decide_outcome}")
    if len(resp.execution_results or []) != 1:
        warnings.append(f"expected exactly 1 execution, got {len(resp.execution_results or [])}")
    if sim.get("details", {}).get("fault_phase") != "REVEALED_LOGIC":
        warnings.append("expected fault_phase=REVEALED_LOGIC")
    return _finish_act(spec, t0, thread_id, warnings, simulator_after=sim, meta=meta)


def _run_cascade_exhaust(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-manager-cascade-exhaust",
        mock_service="ecomm-manager",
        mock_scenario="cascade-exhaust",
    )
    incident = IncidentInput(
        service="ecomm-manager",
        description="【P1】ecomm-manager 商家后台 admin_api_qps 较基线下降超 80%，持续 15 分钟",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    round_no = 1
    _narrate_response(resp, phase=f"第{round_no}轮")
    while resp.status == "awaiting_approval":
        _maybe_pause(spec, resp)
        resp = resume_approval(thread_id, approved=True)
        round_no += 1
        _narrate_response(resp, phase=f"第{round_no}轮")
    sim = client.get("/admin/state").json()
    warnings: list[str] = []
    if resp.incident_resolved is not False:
        warnings.append("expected incident_resolved=false")
    if resp.remediation_attempt != get_settings().max_remediation_attempts:
        warnings.append(f"expected remediation_attempt={get_settings().max_remediation_attempts}")
    if sim.get("details", {}).get("fault_layer") != "CONN_LEAK":
        warnings.append(f"fault_layer={sim.get('details', {}).get('fault_layer')!r}")
    return _finish_act(spec, t0, thread_id, warnings, simulator_final=sim, meta=meta)


def _run_payment_circuit(spec: DemoActSpec) -> DemoActResult:
    t0 = time.time()
    client = rt.prepare_simulator(
        "ecomm-order-payment-circuit",
        mock_service="ecomm-order",
        mock_scenario="payment-circuit",
    )
    incident = IncidentInput(
        service="ecomm-order",
        description="【P1】ecomm-order 支付链路超时激增，下单成功率跌至 45%",
    )
    thread_id, resp, meta = start_diagnosis(incident)
    _narrate_response(resp, phase="诊断")
    warnings: list[str] = []
    if resp.status == "awaiting_approval":
        _maybe_pause(spec, resp)
        resp = resume_approval(thread_id, approved=True)
        _narrate_response(resp, phase="审批后")
    sim = client.get("/admin/state").json()
    actions = [e.get("action") for e in (resp.execution_results or [])]
    if "enable_circuit_breaker" not in actions:
        warnings.append(f"expected enable_circuit_breaker, got {actions}")
    if resp.incident_resolved is not True:
        warnings.append("expected incident_resolved=true")
    if sim.get("phase") != "RECOVERED":
        warnings.append(f"simulator phase={sim.get('phase')!r}")
    return _finish_act(spec, t0, thread_id, warnings, simulator_final=sim, meta=meta)


def _run_kb_appendix(spec: DemoActSpec, runner: Callable[[], dict[str, Any]]) -> DemoActResult:
    t0 = time.time()
    result = runner()
    last = result["steps"][-1]["response"]
    thread_id = result.get("thread_id")
    warnings: list[str] = []
    if not result.get("passed"):
        warnings.append("KB appendix soft-check failed (see run_scenarios criteria)")
    print(f"[KB] runbook_available={last.get('runbook_available')}")
    print(f"[KB] decide_outcome={last.get('decide_outcome')}")
    saved = result["steps"][-1]["graph_state"].get("runbook_saved_path")
    if saved:
        print(f"[KB] runbook_saved_path: {saved}")
    print(f"[KB] summary: {_short(last.get('summary'))}")
    return _finish_act(
        spec,
        t0,
        thread_id,
        warnings,
        characterization=result,
    )


ACT_RUNNERS: dict[str, Callable[[DemoActSpec], DemoActResult]] = {
    "DEMO-01": _run_rem_stream_paused,
    "DEMO-02": _run_rem_crashloop,
    "DEMO-03": _run_loop_morph,
    "DEMO-04": _run_dec_static_oos,
    "DEMO-05": _run_dec_morph_oos,
    "DEMO-H1": _run_cascade_exhaust,
    "DEMO-H2a": _run_payment_circuit,
    "DEMO-KB-01": lambda spec: _run_kb_appendix(spec, run_kb_01),
    "DEMO-KB-02": lambda spec: _run_kb_appendix(spec, run_kb_02),
}

SIMULATOR_BY_ACT: dict[str, str | None] = {
    "DEMO-01": "ecomm-order-stream-paused",
    "DEMO-02": "ecomm-manager-crashloop",
    "DEMO-03": "ecomm-manager-chaos-morph",
    "DEMO-04": "ecomm-manager-discount-bug",
    "DEMO-05": "ecomm-manager-chaos-oos",
    "DEMO-H1": "ecomm-manager-cascade-exhaust",
    "DEMO-H2a": "ecomm-order-payment-circuit",
    "DEMO-KB-01": None,
    "DEMO-KB-02": None,
}

SIMULATOR_ACT_IDS = frozenset(aid for aid, sim in SIMULATOR_BY_ACT.items() if sim)


def resolve_act_ids(profile: str | None, acts: list[str] | None, include_appendix: bool) -> list[str]:
    if acts:
        ids = list(acts)
    elif profile:
        ids = list(PROFILES[profile])
    else:
        ids = list(PROFILES["standard"])
    if include_appendix:
        for aid in PROFILES["appendix"]:
            if aid not in ids:
                ids.append(aid)
    unknown = [a for a in ids if a not in ACT_SPECS]
    if unknown:
        raise SystemExit(f"Unknown act id(s): {unknown}")
    return ids


def _default_report_path() -> Path:
    DEMO_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEMO_REPORT_DIR / f"run_demo_{stamp}.json"


def _write_report(results: list[DemoActResult], report_path: Path, profile: str, act_ids: list[str]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile,
        "act_ids": act_ids,
        "llm": get_settings().llm_mode,
        "embeddings": get_settings().embeddings_provider,
        "all_clear": all(not r.warnings for r in results),
        "acts": [
            {
                "act_id": r.act_id,
                "elapsed_s": r.elapsed_s,
                "thread_id": r.thread_id,
                "warnings": r.warnings,
                **r.payload,
            }
            for r in results
        ],
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_RUN_DEMO_EPILOG = """\
Examples:
  # Standard 5-act demo (one Enter pause at DEMO-02)
  CHECKPOINTER=memory LLM_MODE=real BACKEND_MODE=real \\
    python scripts/run_demo.py --profile standard

  # Full demo + cascade exhaust
  python scripts/run_demo.py --profile full

  # Rehearse a single act
  python scripts/run_demo.py --acts DEMO-03

  # Add KB appendix (mock LLM writeback)
  python scripts/run_demo.py --profile standard --appendix

See ops-agent/docs/demo-scenarios.md
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Real LLM E2E demo with CLI narration.",
        epilog=_RUN_DEMO_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        choices=sorted(k for k in PROFILES if k != "appendix"),
        default="standard",
        help="Demo profile (default: standard)",
    )
    parser.add_argument(
        "--acts",
        nargs="*",
        choices=ALL_ACT_IDS,
        help="Run specific act IDs instead of a profile",
    )
    parser.add_argument(
        "--appendix",
        action="store_true",
        help="Append DEMO-KB-01/02 (mock LLM) after the selected profile/acts",
    )
    parser.add_argument(
        "--report",
        metavar="PATH",
        default=None,
        help=f"Write JSON report (default: {DEMO_REPORT_DIR}/run_demo_<utc>.json)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List profiles and acts, then exit",
    )
    args = parser.parse_args()

    if args.list:
        for name, acts in PROFILES.items():
            print(f"{name}: {', '.join(acts)}")
        return

    act_ids = resolve_act_ids(
        profile=None if args.acts else args.profile,
        acts=args.acts,
        include_appendix=args.appendix,
    )
    profile_label = args.profile if not args.acts else "custom"

    cfg = get_settings()
    print(
        f"[demo] profile={profile_label}  acts={len(act_ids)}  "
        f"llm={cfg.llm_mode}  embeddings={cfg.embeddings_provider}"
    )

    results: list[DemoActResult] = []
    needs_simulator = any(aid in SIMULATOR_ACT_IDS for aid in act_ids)

    def _run_acts() -> None:
        nonlocal results
        for i, act_id in enumerate(act_ids, start=1):
            spec = ACT_SPECS[act_id]
            _banner(i, len(act_ids), spec, SIMULATOR_BY_ACT.get(act_id))
            results.append(ACT_RUNNERS[act_id](spec))

    if needs_simulator:
        with rt.SimulatorSession():
            _run_acts()
    else:
        _run_acts()

    report_path = Path(args.report) if args.report else _default_report_path()
    _write_report(results, report_path, profile_label, act_ids)

    total_s = round(sum(r.elapsed_s for r in results), 1)
    warn_count = sum(len(r.warnings) for r in results)
    print(f"\n{'═' * 39}")
    print(f"  Demo 完成 · {len(results)} 幕 · {total_s}s")
    print(f"  report: {report_path.resolve()}")
    if warn_count:
        print(f"  ⚠ {warn_count} soft-check warning(s) — 演示可继续，详见报告")
    else:
        print("  ✓ 全部 soft-check 通过")
    print(f"{'═' * 39}\n")


if __name__ == "__main__":
    main()
