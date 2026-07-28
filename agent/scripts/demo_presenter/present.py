"""Main interactive presenter loop (phases A–E)."""

from __future__ import annotations

import scenario_runtime as rt
from demo_presenter import bootstrap, catalog, console, simulator_lab
from demo_presenter.act_runner import run_act


def run_present_loop(port: int = rt.SIM_PORT) -> None:
    with rt.SimulatorSession(port=port) as session:
        bootstrap.print_bootstrap(port=port)
        simulator_lab.run_lab(session.client)
        while True:
            act_id = catalog.pick_act()
            if act_id is None:
                console.heading("演示结束")
                print("  感谢观看。")
                break
            catalog.show_detail(act_id)
            if not catalog.confirm_start():
                continue
            run_act(session, act_id)
            console.pause_enter("按 Enter 返回剧本目录…")
