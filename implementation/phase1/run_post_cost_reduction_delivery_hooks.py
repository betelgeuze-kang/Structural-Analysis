#!/usr/bin/env python3
"""Post cost-reduction delivery hooks: member alignment + evidence bundle."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


def run_delivery_hooks(
    *,
    repo_root: Path,
    changes_json: Path,
    baseline_json: Path,
    optimized_roundtrip_json: Path,
    bundle_output: Path,
    enrich: bool = True,
    sync_holdout: bool = True,
) -> dict[str, Any]:
    python = sys.executable
    steps: list[dict[str, Any]] = []

    if enrich:
        cmd = [
            python,
            str(repo_root / "scripts/enrich_optimization_changes_contract.py"),
            "--changes-json",
            str(changes_json),
            "--baseline-json",
            str(baseline_json),
            "--optimized-json",
            str(optimized_roundtrip_json),
        ]
        proc = subprocess.run(cmd, cwd=repo_root, check=False, capture_output=True, text=True)
        steps.append(
            {
                "step": "enrich_member_alignment",
                "exit_code": proc.returncode,
                "log": (proc.stdout or "") + (proc.stderr or ""),
            }
        )
        if proc.returncode != 0:
            return {"status": "failed", "steps": steps}

    bundle_cmd = [
        python,
        str(repo_root / "scripts/run_delivery_evidence_bundle.py"),
        "--output-json",
        str(bundle_output),
        "--changes-json",
        str(changes_json),
        "--roundtrip-json",
        str(optimized_roundtrip_json),
    ]
    proc = subprocess.run(bundle_cmd, cwd=repo_root, check=False, capture_output=True, text=True)
    steps.append(
        {
            "step": "delivery_evidence_bundle",
            "exit_code": proc.returncode,
            "log": (proc.stdout or "") + (proc.stderr or ""),
        }
    )
    status = "ready" if proc.returncode == 0 else "failed"
    if sync_holdout and proc.returncode == 0:
        rh_path = repo_root / "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
        sync_cmd = [
            python,
            str(repo_root / "scripts/sync_holdout_supplementary_evidence.py"),
            "--bundle-json",
            str(bundle_output),
            "--residual-holdout-json",
            str(rh_path),
            "--output-json",
            str(rh_path),
        ]
        sync_proc = subprocess.run(sync_cmd, cwd=repo_root, check=False, capture_output=True, text=True)
        steps.append(
            {
                "step": "sync_holdout_supplementary",
                "exit_code": sync_proc.returncode,
                "log": (sync_proc.stdout or "") + (sync_proc.stderr or ""),
            }
        )
        if sync_proc.returncode != 0:
            status = "failed"

    return {"status": status, "steps": steps, "bundle_output": str(bundle_output)}
