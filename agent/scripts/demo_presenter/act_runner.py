"""Phase D/E: run one act with stream narration and recap."""

from __future__ import annotations

import time
from typing import Any

from app.graph.runner import stream_diagnosis, stream_resume
from app.schemas import IncidentInput

import scenario_runtime as rt
from demo_presenter import breakpoints, catalog, console, graph_art
from demo_presenter.narrator import StreamNarrator


from run_demo import DemoActResult


def _tool_name(resp) -> str:
    pending = resp.pending_tool_calls or []
    if not pending:
        return "?"
    tc = pending[0]
    return tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "?")


def _auto_approve_loop(
    thread_id: str,
    resp,
    meta: dict,
    narrator: StreamNarrator,
    *,
    interactive_hitl: bool,
    max_rounds: int = 16,
) -> tuple[Any, dict]:
    from app.graph.runner import resume_approval

    guard = 0
    while guard < max_rounds:
        if resp.status == "awaiting_approval":
            tool = _tool_name(resp)
            if interactive_hitl:
                if not breakpoints.confirm_hitl(tool):
                    resp = resume_approval(thread_id, approved=False)
                    narrator.visited.append("approve")
                    break
            else:
                print(f"  [HITL] 自动批准: {tool}")
            resp, meta, _ = stream_resume(
                thread_id,
                {"approved": True},
                on_node_update=narrator.on_node,
            )
        elif meta.get("pending_interrupt"):
            resp, meta, _ = stream_resume(
                thread_id,
                {"approved": True},
                on_node_update=narrator.on_node,
            )
        else:
            break
        guard += 1
    return resp, meta


def run_act(session: rt.SimulatorSession, act_id: str) -> DemoActResult:
    spec = catalog.ACT_RUNTIME[act_id]
    t0 = time.time()
    console.heading(f"Act · {spec.act_id} · {spec.title}")
    print(f"  Simulator: {spec.simulator_id}")

    session.prepare_act(
        spec.simulator_id,
        mock_service=spec.mock_service,
        mock_scenario=spec.mock_scenario,
    )
    client = session.client

    if not breakpoints.confirm_alert(spec.description):
        return DemoActResult(act_id=act_id, elapsed_s=0.0, thread_id=None, warnings=["用户取消"])

    incident = IncidentInput(service=spec.service, description=spec.description)
    narrator = StreamNarrator(interactive=True)
    thread_id, resp, meta, _ = stream_diagnosis(incident, on_node_update=narrator.on_node)

    interactive_hitl = spec.pause_before_approve
    resp, meta = _auto_approve_loop(
        thread_id,
        resp,
        meta,
        narrator,
        interactive_hitl=interactive_hitl,
    )

    sim = client.get("/admin/state").json()
    warnings: list[str] = []
    expected = graph_art.EXPECTED_PATHS.get(act_id, [])

    console.heading("Recap (E)")
    print(graph_art.render_compare(expected, narrator.visited))

    elapsed = round(time.time() - t0, 1)
    mark = "✓" if not warnings else "⚠"
    print(f"\n{mark} 本幕完成 ({elapsed}s) · status={resp.status}")
    if resp.decide_outcome:
        print(f"   decide_outcome={resp.decide_outcome}")
    if resp.incident_resolved is not None:
        print(f"   incident_resolved={resp.incident_resolved}")
    print(f"   simulator phase={sim.get('phase')}")

    return DemoActResult(
        act_id=act_id,
        elapsed_s=elapsed,
        thread_id=thread_id,
        warnings=warnings,
        payload={"simulator_final": sim, "meta": meta, "visited": narrator.visited},
    )
