from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DRIFT_SCRIPT = REPO_ROOT / "scripts" / "build_ml_surrogate_drift_guard_receipt.py"
CI_SCRIPT = REPO_ROOT / "scripts" / "check_ml_surrogate_drift_guard.py"
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/ml_surrogate_drift_guard_receipt.json"
)


def _build_drift_receipt(
    out: Path,
    *,
    live_max_dcr: float | None = None,
    live_drift: float | None = None,
    live_cost: float | None = None,
    drift_multiplier: float = 1.5,
) -> dict:
    cmd: list[str] = [sys.executable, str(DRIFT_SCRIPT), "--output-json", str(out)]
    if live_max_dcr is not None:
        cmd.extend(["--live-max-dcr", str(live_max_dcr)])
    if live_drift is not None:
        cmd.extend(["--live-drift-contribution", str(live_drift)])
    if live_cost is not None:
        cmd.extend(["--live-group-cost", str(live_cost)])
    cmd.extend(["--drift-multiplier", str(drift_multiplier)])
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode in {0, 1}, proc.stderr
    return json.loads(out.read_text(encoding="utf-8"))


def test_drift_guard_receipt_default_armed(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    payload = _build_drift_receipt(out)
    assert payload["schema_version"] == "ml-surrogate-drift-guard-receipt.v1"
    assert payload["status"] == "ready"
    assert payload["drift_guard_decision"] in {"armed", "not_wired"}
    assert payload["drift_breach_count"] == 0
    assert payload["env_recommendation"]["set_disable_env"] is False
    assert len(payload["drift_per_component"]) == 3


def test_drift_guard_receipt_breach_fires(tmp_path: Path) -> None:
    out = tmp_path / "receipt_breach.json"
    payload = _build_drift_receipt(
        out,
        live_max_dcr=1.0,
        live_drift=1.0e-3,
        live_cost=0.1,
    )
    assert payload["status"] == "guard_fired"
    assert payload["drift_guard_decision"] == "disarm_recommended"
    assert payload["drift_breach_count"] >= 1
    assert payload["env_recommendation"]["set_disable_env"] is True
    assert payload["env_recommendation"]["env_var"] == "PHASE1_ML_SURROGATE_DISABLE"


def test_drift_guard_receipt_breach_only_max_dcr(tmp_path: Path) -> None:
    out = tmp_path / "receipt_one_breach.json"
    payload = _build_drift_receipt(
        out,
        live_max_dcr=1.0,
        live_drift=0.0,
        live_cost=0.0,
    )
    assert payload["status"] == "guard_fired"
    assert payload["drift_breach_count"] == 1
    components = {row["component"]: row for row in payload["drift_per_component"]}
    assert components["max_dcr"]["drift_breach"] is True
    assert components["member_story_drift_contribution_pct"]["drift_breach"] is False


def test_drift_guard_receipt_forced_disabled(tmp_path: Path) -> None:
    out = tmp_path / "receipt_forced.json"
    env = os.environ.copy()
    env["PHASE1_ML_SURROGATE_DISABLE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(DRIFT_SCRIPT), "--output-json", str(out)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode in {0, 1}, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["drift_guard_decision"] == "forced_disabled"
    assert payload["production_ml_wired"] is False
    assert payload["status"] in {"ready", "guard_fired"}


def test_drift_guard_receipt_missing_live_data_keeps_armed(tmp_path: Path) -> None:
    out = tmp_path / "receipt_no_live.json"
    payload = _build_drift_receipt(out)
    for row in payload["drift_per_component"]:
        assert row["live_value"] is None
        assert row["drift_breach"] is False
    assert payload["drift_guard_decision"] in {"armed", "not_wired"}


def test_drift_guard_ci_check_passes(tmp_path: Path) -> None:
    out = tmp_path / "receipt.json"
    _build_drift_receipt(out)
    proc = subprocess.run(
        [sys.executable, str(CI_SCRIPT), "--receipt", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout


def test_drift_guard_ci_check_fails_on_breach(tmp_path: Path) -> None:
    out = tmp_path / "receipt_breach.json"
    _build_drift_receipt(out, live_max_dcr=1.0)
    proc = subprocess.run(
        [sys.executable, str(CI_SCRIPT), "--receipt", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "FAIL" in proc.stderr or "disarm_recommended" in proc.stderr
    smoke = subprocess.run(
        [sys.executable, str(CI_SCRIPT), "--receipt", str(out), "--no-fail-closed"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert smoke.returncode == 0
