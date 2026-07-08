"""Tests for run_demo profiles and act resolution."""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

from run_demo import PROFILES, resolve_act_ids  # noqa: E402


def test_standard_profile_has_five_acts():
    assert PROFILES["standard"] == [
        "DEMO-01",
        "DEMO-02",
        "DEMO-03",
        "DEMO-04",
        "DEMO-05",
    ]


def test_demo_02_is_only_standard_pause_act():
    from run_demo import ACT_SPECS

    pausing = [aid for aid in PROFILES["standard"] if ACT_SPECS[aid].pause_before_approve]
    assert pausing == ["DEMO-02"]


def test_resolve_appendix_appends_kb_acts():
    ids = resolve_act_ids("short", acts=None, include_appendix=True)
    assert ids[:3] == PROFILES["short"]
    assert ids[-2:] == PROFILES["appendix"]


def test_run_demo_list_exits_zero():
    script = os.path.join(SCRIPTS, "run_demo.py")
    proc = subprocess.run(
        [sys.executable, script, "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "standard:" in proc.stdout
    assert "DEMO-02" in proc.stdout
