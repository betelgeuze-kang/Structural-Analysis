from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "implementation/phase1/run_f3_frame3d_linear_vertical_evidence.py"
SPEC = importlib.util.spec_from_file_location("f3_frame3d_linear_evidence", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_frame3d_linear_evidence_closes_all_nine_surfaces() -> None:
    payload = MODULE.build_receipt(source_commit_sha="a" * 40)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["stage_gate"]["public_product_promotion_passed"] is True
    assert payload["stage_gate"]["external_vv_signature_status"] == "waived"
    assert payload["stage_gate"]["blockers"] == []
    assert len(payload["stage_gate"]["verified_surfaces"]) == 9


def test_four_independent_modes_have_equilibrium_result_and_restart_evidence() -> None:
    payload = MODULE.build_receipt(source_commit_sha="b" * 40)
    cases = payload["surface_artifacts"]["benchmark"]["cases"]

    assert [row["load_pattern_id"] for row in cases] == [
        "LC_AXIAL",
        "LC_WEAK",
        "LC_STRONG",
        "LC_TORSION",
    ]
    assert all(row["free_residual_inf_n"] <= 1.0e-7 for row in cases)
    assert all(row["analytic_relative_error"] <= 1.0e-12 for row in cases)
    assert all(row["checkpoint_exact_restart"] for row in cases)
    assert all(row["result_ir_hash"].startswith("sha256:") for row in cases)


def test_result_ir_and_workbench_surfaces_are_authority_bound() -> None:
    payload = MODULE.build_receipt(source_commit_sha="c" * 40)
    result_rows = payload["surface_artifacts"]["result_ir"]["manifests"]
    viewer_rows = payload["surface_artifacts"]["workbench"]["payloads"]

    assert len(result_rows) == len(viewer_rows) == 4
    assert all(row["authority"]["displacement"] == "authoritative" for row in result_rows)
    assert all(row["authority"]["reaction"] == "not_evaluated" for row in result_rows)
    assert all("model_identity" in row for row in viewer_rows)
    assert all(row["source"] == "authoritative_solver_result" for row in viewer_rows)


def test_check_replays_recorded_source_commit_after_evidence_commit(tmp_path: Path) -> None:
    target = tmp_path / "linear.json"
    payload = MODULE.build_receipt(source_commit_sha="d" * 40)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert MODULE.main(["--out", str(target), "--check"]) == 0
