from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture_payload(*, rebar_ratio: float, peak_drift_ratio: float, rebar_sensitive: bool) -> dict:
    return {
        "contract_pass": True,
        "seed_id": "seed-01",
        "holdout_split": "holdout",
        "specimen_summary": {
            "longitudinal_rebar_ratio": rebar_ratio,
        },
        "hysteresis_summary": {
            "peak_abs_drift_ratio": peak_drift_ratio,
        },
        "hinge_refresh_targets": {
            "rebar_sensitive_expected": rebar_sensitive,
        },
    }


def test_peer_spd_hinge_refresh_alignment_passes_with_column_overlap_and_rebar_envelope(tmp_path: Path) -> None:
    fixture = tmp_path / "seed-01.hinge_fixture.json"
    registry = tmp_path / "registry.json"
    source = tmp_path / "hinge_refresh_source.json"
    out = tmp_path / "alignment.json"
    _write_json(fixture, _fixture_payload(rebar_ratio=0.06, peak_drift_ratio=0.04, rebar_sensitive=True))
    _write_json(
        registry,
        {
            "summary": {"holdout_count": 1},
            "rows": [
                {
                    "benchmark_ready": True,
                    "seed_id": "seed-01",
                    "holdout_split": "holdout",
                    "fixture_path": str(fixture),
                }
            ],
        },
    )
    _write_json(
        source,
        {
            "summary": {"source_artifact_kind": "hinge_refresh_source_json", "source_mode": "projected_refresh"},
            "hinge_refresh_rows": [
                {
                    "member_id": "C101",
                    "member_type": "column",
                    "yield_rotation": 0.0015,
                    "ultimate_rotation": 0.0053,
                    "before_rebar_ratio": 0.074,
                    "after_rebar_ratio": 0.064,
                    "rebar_sensitive": True,
                    "action_family": "rebar",
                }
            ],
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_peer_spd_hinge_refresh_alignment.py",
            "--asset-registry",
            str(registry),
            "--hinge-refresh-source",
            str(source),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["observed"]["refresh_column_row_count"] == 1
    assert payload["observed"]["refresh_rebar_sensitive_column_count"] == 1
    assert payload["observed"]["rebar_envelope_overlap_with_padding"] is True


def test_peer_spd_hinge_refresh_alignment_fails_without_rebar_sensitive_column_rows(tmp_path: Path) -> None:
    fixture = tmp_path / "seed-01.hinge_fixture.json"
    registry = tmp_path / "registry.json"
    source = tmp_path / "hinge_refresh_source.json"
    out = tmp_path / "alignment.json"
    _write_json(fixture, _fixture_payload(rebar_ratio=0.03, peak_drift_ratio=0.04, rebar_sensitive=True))
    _write_json(
        registry,
        {
            "summary": {"holdout_count": 1},
            "rows": [
                {
                    "benchmark_ready": True,
                    "seed_id": "seed-01",
                    "holdout_split": "holdout",
                    "fixture_path": str(fixture),
                }
            ],
        },
    )
    _write_json(
        source,
        {
            "hinge_refresh_rows": [
                {
                    "member_id": "C101",
                    "member_type": "column",
                    "yield_rotation": 0.0015,
                    "ultimate_rotation": 0.0053,
                    "before_rebar_ratio": 0.03,
                    "after_rebar_ratio": 0.03,
                    "rebar_sensitive": False,
                    "action_family": "beam_section",
                }
            ],
        },
    )
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/run_peer_spd_hinge_refresh_alignment.py",
            "--asset-registry",
            str(registry),
            "--hinge-refresh-source",
            str(source),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_REBAR_SENSITIVE_COLUMN_MISSING"
