#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pareto_research_archive_builds_front() -> None:
    changes = REPO_ROOT / "implementation/phase1/release_evidence/productization/design_optimization_cost_reduction_changes.json"
    out = REPO_ROOT / "implementation/phase1/release_evidence/productization/optimization_pareto_research_archive_test.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_optimization_pareto_research_archive.py"),
            "--changes-json",
            str(changes),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "research_archive_ready"
    assert payload["pareto_front_count"] >= 1
    assert payload["production_pareto_wired"] is False
