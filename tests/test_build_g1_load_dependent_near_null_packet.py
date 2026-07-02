from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_g1_load_dependent_near_null_packet.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(REPO_ROOT / "implementation" / "phase1") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

SPEC = importlib.util.spec_from_file_location(
    "build_g1_load_dependent_near_null_packet",
    SCRIPT_PATH,
)
assert SPEC and SPEC.loader
packet_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packet_module)


def _raw_near_null(*, load_scale: float = 0.2, mode_count: int = 2) -> dict:
    return {
        "schema_version": "g1-null-space-mode-audit.v1",
        "status": "ready",
        "reason_code": "PASS",
        "load_scale": load_scale,
        "frame_service_tangent_source": "real_per_element",
        "singularity_indicators": {
            "singular": True,
            "smallest_eigenvalues": [1.0e-7, 2.0e-7],
            "near_null_mode_count": mode_count,
            "near_null_eigenvalue_tolerance_relative": 1.0e-3,
        },
        "assembled_tangent": {"free_dof_count": 12, "nnz": 24},
        "mode_rows": [
            {
                "mode_index": 0,
                "eigenvalue": 1.0e-7,
                "near_null": True,
                "dominant_dof_types": {"UY": 1.0},
                "dominant_nodes": [{"node_id": 101, "dof": "UY", "amplitude": 1.0}],
            }
        ],
        "pinning_candidates": [{"target_dof_type": "UY"}],
    }


def _reconciliation(*, status: str = "ready", dominant_rows: list[dict] | None = None) -> dict:
    dominant_rows = dominant_rows if dominant_rows is not None else [
        {"node_id": 101, "dof": "UY", "mode_index": 0},
        {"node_id": 102, "dof": "UY", "mode_index": 0},
    ]
    return {
        "schema_version": "g1-support-elastic-link-reconciliation-audit.v1",
        "status": status,
        "reason_code": "PASS" if status == "ready" else "ERR",
        "summary": {
            "dominant_dof_row_count": len(dominant_rows),
            "direct_support_member_count": 0,
            "direct_elastic_link_endpoint_count": 0,
            "elastic_link_reachable_to_support_count": 0,
        },
        "dominant_dof_rows": dominant_rows,
        "ranked_findings": [],
        "blockers": [] if status == "ready" else ["audit_blocked"],
    }


def test_packet_ready_when_raw_audit_and_reconciliation_are_ready(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(packet_module, "run_null_space_audit", lambda **kwargs: _raw_near_null())
    monkeypatch.setattr(packet_module, "build_reconciliation_audit", lambda **kwargs: _reconciliation())

    payload = packet_module.build_packet(
        repo_root=tmp_path,
        load_scale=0.2,
        raw_near_null_json=tmp_path / "raw.local.json",
    )

    assert payload["schema_version"] == packet_module.SCHEMA_VERSION
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["summary"]["near_null_mode_count"] == 2
    assert payload["summary"]["dominant_dof_row_count"] == 2
    assert payload["dominant_node_ids"] == [101, 102]
    assert payload["blockers"] == []


def test_packet_blocks_load_mismatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        packet_module,
        "run_null_space_audit",
        lambda **kwargs: _raw_near_null(load_scale=0.1),
    )
    monkeypatch.setattr(packet_module, "build_reconciliation_audit", lambda **kwargs: _reconciliation())

    payload = packet_module.build_packet(
        repo_root=tmp_path,
        load_scale=0.2,
        raw_near_null_json=tmp_path / "raw.local.json",
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "load_dependent_near_null_packet_load_scale_mismatch:0.2" in payload["blockers"]


def test_packet_blocks_missing_modes_and_dominant_rows(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        packet_module,
        "run_null_space_audit",
        lambda **kwargs: {**_raw_near_null(mode_count=0), "mode_rows": []},
    )
    monkeypatch.setattr(
        packet_module,
        "build_reconciliation_audit",
        lambda **kwargs: _reconciliation(dominant_rows=[]),
    )

    payload = packet_module.build_packet(
        repo_root=tmp_path,
        load_scale=0.2,
        raw_near_null_json=tmp_path / "raw.local.json",
    )

    assert payload["status"] == "blocked"
    assert "load_dependent_near_null_packet_mode_count_missing:0.2" in payload["blockers"]
    assert "load_dependent_near_null_packet_mode_rows_missing:0.2" in payload["blockers"]
    assert "load_dependent_near_null_packet_dominant_rows_missing:0.2" in payload["blockers"]


def test_write_packet_writes_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(packet_module, "run_null_space_audit", lambda **kwargs: _raw_near_null())
    monkeypatch.setattr(packet_module, "build_reconciliation_audit", lambda **kwargs: _reconciliation())
    out = tmp_path / "packet.local.json"

    payload = packet_module.write_packet(
        repo_root=tmp_path,
        load_scale=0.2,
        raw_near_null_json=tmp_path / "raw.local.json",
        out=out,
    )

    assert payload["status"] == "ready"
    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        packet_module.SCHEMA_VERSION
    )
