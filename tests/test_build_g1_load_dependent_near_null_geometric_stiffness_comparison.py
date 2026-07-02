from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_g1_load_dependent_near_null_geometric_stiffness_comparison.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

SPEC = importlib.util.spec_from_file_location(
    "build_g1_load_dependent_near_null_geometric_stiffness_comparison",
    SCRIPT_PATH,
)
assert SPEC and SPEC.loader
comparison_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison_module)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_base_inputs(tmp_path: Path) -> dict[str, Path]:
    f2h_status = tmp_path / "f2h_status.json"
    f2h_continuation = tmp_path / "f2h_continuation.json"
    f2g_audit = tmp_path / "f2g_audit.json"
    _write_json(
        f2h_status,
        {
            "status": "ready",
            "summary": {
                "required_sequence_proven": True,
                "all_steps_ready": True,
                "max_converged_load_scale": 0.4,
                "residual_trend_across_increasing_load": "nondecreasing",
            },
            "residual_history": [
                {"load_scale": 0.1, "residual_inf_n": 1.0e-6, "relative_increment": 1.0e-5},
                {"load_scale": 0.2, "residual_inf_n": 2.1e-6, "relative_increment": 2.0e-5},
                {"load_scale": 0.4, "residual_inf_n": 4.2e-6, "relative_increment": 2.5e-5},
            ],
        },
    )
    _write_json(
        f2h_continuation,
        {
            "step_results": [
                {
                    "load_step": 0.1,
                    "ready": True,
                    "converged": True,
                    "residual_inf_n": 1.0e-6,
                    "relative_increment": 1.0e-5,
                    "max_translation_m": 0.1,
                    "max_drift_ratio_pct": 1.0,
                    "iteration_count": 4,
                },
                {
                    "load_step": 0.2,
                    "ready": True,
                    "converged": True,
                    "residual_inf_n": 2.1e-6,
                    "relative_increment": 2.0e-5,
                    "max_translation_m": 0.23,
                    "max_drift_ratio_pct": 2.3,
                    "iteration_count": 9,
                },
                {
                    "load_step": 0.4,
                    "ready": True,
                    "converged": True,
                    "residual_inf_n": 4.2e-6,
                    "relative_increment": 2.5e-5,
                    "max_translation_m": 0.62,
                    "max_drift_ratio_pct": 6.2,
                    "iteration_count": 12,
                },
            ]
        },
    )
    _write_json(
        f2g_audit,
        {
            "status": "ready",
            "near_null_context": {"load_scale": 0.1, "near_null_mode_count": 8},
            "summary": {"dominant_dof_row_count": 64},
            "dominant_dof_rows": [
                {"node_id": 101, "dof": "UX"},
                {"node_id": 102, "dof": "UY"},
            ],
        },
    )
    return {
        "f2h_status": f2h_status,
        "f2h_continuation": f2h_continuation,
        "f2g_audit": f2g_audit,
        "near_null_0p2": tmp_path / "near_null_0p2.json",
        "near_null_0p4": tmp_path / "near_null_0p4.json",
    }


def _near_null_packet(load_scale: float, node_ids: list[int]) -> dict:
    return {
        "schema_version": comparison_module.NEAR_NULL_PACKET_SCHEMA_VERSION,
        "status": "ready",
        "contract_pass": True,
        "near_null_context": {"load_scale": load_scale, "near_null_mode_count": 8},
        "summary": {"dominant_dof_row_count": len(node_ids)},
        "dominant_dof_rows": [{"node_id": node_id, "dof": "UY"} for node_id in node_ids],
    }


def test_comparison_blocks_missing_load_dependent_near_null_packets(tmp_path: Path) -> None:
    paths = _write_base_inputs(tmp_path)

    payload = comparison_module.build_comparison(
        repo_root=tmp_path,
        f2h_status_path=paths["f2h_status"],
        f2h_continuation_path=paths["f2h_continuation"],
        f2g_audit_path=paths["f2g_audit"],
        near_null_0p2_path=paths["near_null_0p2"],
        near_null_0p4_path=paths["near_null_0p4"],
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["promotes_g1_closure"] is False
    assert payload["summary"]["load_response_ready"] is True
    assert payload["summary"]["near_null_packet_comparison_ready"] is False
    assert payload["summary"]["geometric_softening_signal"] == "active_secondary"
    assert "load_dependent_near_null_packet_missing:0.2" in payload["blockers"]
    assert "load_dependent_near_null_packet_missing:0.4" in payload["blockers"]
    assert payload["root_cause_signal_update"]["primary_next_lane"] == (
        "consistent_residual_jacobian_newton_rocm_worker"
    )


def test_comparison_ready_when_0p2_0p4_near_null_packets_are_attached(tmp_path: Path) -> None:
    paths = _write_base_inputs(tmp_path)
    _write_json(paths["near_null_0p2"], _near_null_packet(0.2, [101, 103]))
    _write_json(paths["near_null_0p4"], _near_null_packet(0.4, [101, 104]))

    payload = comparison_module.build_comparison(
        repo_root=tmp_path,
        f2h_status_path=paths["f2h_status"],
        f2h_continuation_path=paths["f2h_continuation"],
        f2g_audit_path=paths["f2g_audit"],
        near_null_0p2_path=paths["near_null_0p2"],
        near_null_0p4_path=paths["near_null_0p4"],
    )

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["summary"]["near_null_packet_comparison_ready"] is True
    assert payload["summary"]["invalid_near_null_packet_count"] == 0
    assert payload["near_null_comparison"]["baseline_to_0p2_node_overlap"]["shared_count"] == 1
    assert payload["near_null_comparison"]["0p2_to_0p4_node_overlap"]["shared_count"] == 1


def test_comparison_rejects_shape_only_near_null_packets(tmp_path: Path) -> None:
    paths = _write_base_inputs(tmp_path)
    packet = _near_null_packet(0.4, [])
    packet.pop("schema_version")
    _write_json(paths["near_null_0p2"], packet)
    _write_json(paths["near_null_0p4"], _near_null_packet(0.4, [101, 104]))

    payload = comparison_module.build_comparison(
        repo_root=tmp_path,
        f2h_status_path=paths["f2h_status"],
        f2h_continuation_path=paths["f2h_continuation"],
        f2g_audit_path=paths["f2g_audit"],
        near_null_0p2_path=paths["near_null_0p2"],
        near_null_0p4_path=paths["near_null_0p4"],
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["summary"]["near_null_packet_comparison_ready"] is False
    assert payload["summary"]["invalid_near_null_packet_count"] == 1
    assert "load_dependent_near_null_packet_schema_mismatch:0.2" in payload["blockers"]
    assert "load_dependent_near_null_packet_load_scale_mismatch:0.2" in payload["blockers"]
    assert "load_dependent_near_null_packet_dominant_rows_missing:0.2" in payload["blockers"]
    assert payload["near_null_comparison"]["packet_validation_blockers"]["0.2"] == [
        "load_dependent_near_null_packet_schema_mismatch:0.2",
        "load_dependent_near_null_packet_load_scale_mismatch:0.2",
        "load_dependent_near_null_packet_dominant_rows_missing:0.2",
        "load_dependent_near_null_packet_dominant_nodes_missing:0.2",
    ]


def test_write_comparison_writes_markdown_and_json(tmp_path: Path) -> None:
    paths = _write_base_inputs(tmp_path)
    out = tmp_path / "comparison.json"
    out_md = tmp_path / "comparison.md"

    payload = comparison_module.write_comparison(
        repo_root=tmp_path,
        f2h_status_path=paths["f2h_status"],
        f2h_continuation_path=paths["f2h_continuation"],
        f2g_audit_path=paths["f2g_audit"],
        near_null_0p2_path=paths["near_null_0p2"],
        near_null_0p4_path=paths["near_null_0p4"],
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["schema_version"] == (
        comparison_module.SCHEMA_VERSION
    )
    assert "# G1 Load-Dependent Near-Null" in out_md.read_text(encoding="utf-8")
    assert payload["status"] == "blocked"
