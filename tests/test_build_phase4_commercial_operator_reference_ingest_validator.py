from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts/build_phase4_commercial_operator_reference_ingest_validator.py"
)
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT / "scripts", SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

spec = importlib.util.spec_from_file_location(
    "build_phase4_commercial_operator_reference_ingest_validator",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _complete_package(tmp_path: Path) -> Path:
    raw_input = tmp_path / "operator_refs" / "case-a" / "model.etabs"
    solver_a_raw = tmp_path / "operator_refs" / "case-a" / "solver-a.csv"
    solver_b_raw = tmp_path / "operator_refs" / "case-a" / "solver-b.csv"
    solver_a_normalized = (
        tmp_path / "operator_refs" / "case-a" / "solver-a.normalized.json"
    )
    solver_b_normalized = (
        tmp_path / "operator_refs" / "case-a" / "solver-b.normalized.json"
    )
    solver_a_receipt = (
        tmp_path / "operator_refs" / "case-a" / "solver-a.normalization.json"
    )
    solver_b_receipt = (
        tmp_path / "operator_refs" / "case-a" / "solver-b.normalization.json"
    )
    permission_receipt = tmp_path / "operator_refs" / "case-a" / "permission.json"
    for path, text in [
        (raw_input, "model"),
        (solver_a_raw, "solver-a"),
        (solver_b_raw, "solver-b"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    model_hash = _sha256(raw_input)

    def reference(*, reference_id: str, tool: str, version: str, raw: Path) -> dict:
        zeros = [0.0] * 6
        return {
            "schema_version": "structural-external-linear-frame3d-reference.v1",
            "reference_id": reference_id,
            "source": {
                "tool": tool,
                "version": version,
                "origin": "operator_attached_external",
                "export_sha256": _sha256(raw),
            },
            "bindings": {
                "model_content_hash": model_hash,
                "load_pattern_id": "LP1",
                "load_combination_id": None,
            },
            "axes": {
                "node_displacement": "global_ux_uy_uz_rx_ry_rz",
                "node_reaction": "global_fx_fy_fz_mx_my_mz",
                "member_end_force": "member_local_fx_fy_fz_mx_my_mz_i_then_j",
                "sign_convention": "native_result_ir_compatible",
            },
            "units": {
                "translation": "m",
                "rotation": "rad",
                "force": "kN",
                "moment": "kN*m",
            },
            "nodes": [
                {"node_id": "N1", "displacement": zeros, "reaction": zeros},
                {"node_id": "N2", "displacement": zeros, "reaction": zeros},
            ],
            "members": [
                {"member_id": "M1", "end_i_force": zeros, "end_j_force": zeros}
            ],
            "claim_boundary": (
                "operator_declared_mapping_and_units_not_independent_validation_or_release_authority"
            ),
        }

    solver_rows = [
        {
            "engine_name": "MIDAS",
            "engine_version": "v1",
            "operator_id": "operator-1",
            "run_id": "run-midas-1",
            "raw_result_file": "operator_refs/case-a/solver-a.csv",
            "normalized_result_file": "operator_refs/case-a/solver-a.normalized.json",
            "normalization_receipt_file": "operator_refs/case-a/solver-a.normalization.json",
            "normalized_path": solver_a_normalized,
            "receipt_path": solver_a_receipt,
            "raw_path": solver_a_raw,
            "tool": "midas_gen",
            "reference_id": "MidasRef1",
        },
        {
            "engine_name": "SAP2000",
            "engine_version": "v2",
            "operator_id": "operator-1",
            "run_id": "run-sap-1",
            "raw_result_file": "operator_refs/case-a/solver-b.csv",
            "normalized_result_file": "operator_refs/case-a/solver-b.normalized.json",
            "normalization_receipt_file": "operator_refs/case-a/solver-b.normalization.json",
            "normalized_path": solver_b_normalized,
            "receipt_path": solver_b_receipt,
            "raw_path": solver_b_raw,
            "tool": "sap2000",
            "reference_id": "SapRef1",
        },
    ]
    for row in solver_rows:
        row["normalized_path"].write_text(
            json.dumps(
                reference(
                    reference_id=row["reference_id"],
                    tool=row["tool"],
                    version=row["engine_version"],
                    raw=row["raw_path"],
                ),
                allow_nan=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        row["receipt_path"].write_text(
            json.dumps(
                {
                    "schema_version": "commercial-reference-normalization-receipt.v1",
                    "case_id": "case-a",
                    "operator_id": row["operator_id"],
                    "run_id": row["run_id"],
                    "engine_name": row["engine_name"],
                    "engine_version": row["engine_version"],
                    "raw_result_file": row["raw_result_file"],
                    "raw_result_file_sha256": _sha256(row["raw_path"]),
                    "normalized_result_file": row["normalized_result_file"],
                    "normalized_result_file_sha256": _sha256(row["normalized_path"]),
                    "model_content_hash": model_hash,
                    "operator_attested": False,
                    "legal_use_approved": False,
                    "promotion_eligible": False,
                },
                allow_nan=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    permission_receipt.write_text(
        json.dumps(
            {
                "schema_version": "commercial-reference-permission-declaration.v1",
                "operator_id": "operator-1",
                "case_id": "case-a",
                "comparison_use_allowed": True,
                "legal_use_approved": False,
                "signature_verified": False,
            },
            allow_nan=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    package = {
        "case_id": "case-a",
        "modeling_convention_id": "convention-a",
        "permission_scope": {
            "comparison_use_allowed": True,
            "redistribution_allowed": False,
            "approval_receipt": {
                "path": "operator_refs/case-a/permission.json",
                "file_sha256": _sha256(permission_receipt),
                "operator_id": "operator-1",
                "approved_at": "2026-08-28T00:00:00Z",
                "comparison_scope": "non_released_internal_comparison",
            },
        },
        "reference_solvers": [
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "engine_name",
                    "engine_version",
                    "operator_id",
                    "run_id",
                    "raw_result_file",
                    "normalized_result_file",
                    "normalization_receipt_file",
                }
            }
            for row in solver_rows
        ],
        "raw_input_files": ["operator_refs/case-a/model.etabs"],
        "raw_result_files": [
            "operator_refs/case-a/solver-a.csv",
            "operator_refs/case-a/solver-b.csv",
        ],
        "file_checksums": {
            "operator_refs/case-a/model.etabs": _sha256(raw_input),
            "operator_refs/case-a/solver-a.csv": _sha256(solver_a_raw),
            "operator_refs/case-a/solver-b.csv": _sha256(solver_b_raw),
            "operator_refs/case-a/solver-a.normalized.json": _sha256(
                solver_a_normalized
            ),
            "operator_refs/case-a/solver-b.normalized.json": _sha256(
                solver_b_normalized
            ),
            "operator_refs/case-a/solver-a.normalization.json": _sha256(
                solver_a_receipt
            ),
            "operator_refs/case-a/solver-b.normalization.json": _sha256(
                solver_b_receipt
            ),
            "operator_refs/case-a/permission.json": _sha256(permission_receipt),
        },
        "modeling_convention": {
            "unit_system": "kN-m",
            "local_axis_convention": "operator-declared",
            "rigid_offset_policy": "operator-declared",
            "end_release_policy": "operator-declared",
            "diaphragm_policy": "operator-declared",
            "mass_source_policy": "operator-declared",
            "self_weight_policy": "operator-declared",
            "material_modulus_convention": "operator-declared",
            "shell_formulation": "operator-declared",
            "mesh_density": "operator-declared",
            "damping_policy": "operator-declared",
            "p_delta_policy": "operator-declared",
            "eigen_solver": "operator-declared",
            "load_combinations": ["LC1"],
            "convergence_tolerance": "operator-declared",
        },
        "unsupported_features": [],
        "warnings": [],
    }
    package_path = tmp_path / "operator_package.json"
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return package_path


def test_operator_reference_ingest_validator_blocks_without_package() -> None:
    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT
    )

    assert (
        payload["schema_version"]
        == "phase4-commercial-operator-reference-ingest-preflight.v2"
    )
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["validation_result"]["blockers"] == [
        "operator_reference_package_missing"
    ]
    assert payload["remaining_blockers"] == ["operator_reference_package_missing"]
    assert "non-authoritative ingest preflight" in payload["claim_boundary"]


def test_operator_reference_ingest_validator_blocks_incomplete_package(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package.json"
    package.write_text(
        json.dumps(
            {
                "case_id": "case-a",
                "modeling_convention_id": "convention-a",
                "permission_scope": {"comparison_use_allowed": False},
                "reference_solvers": [{"engine_name": "ETABS"}],
                "raw_input_files": ["missing.etabs"],
                "raw_result_files": [],
                "file_checksums": {},
                "modeling_convention": {},
                "unsupported_features": [],
                "warnings": [],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package,
    )

    blockers = payload["validation_result"]["blockers"]
    assert payload["status"] == "blocked"
    assert "comparison_use_permission_missing" in blockers
    assert "permission_approval_receipt_descriptor_missing" in blockers
    assert "two_reference_solver_comparison_not_available" in blockers
    assert "checksum_missing:missing.etabs" in blockers
    assert "modeling_convention_missing:unit_system" in blockers


def test_operator_reference_ingest_validator_accepts_complete_package_as_preflight_only(
    tmp_path: Path,
) -> None:
    package = _complete_package(tmp_path)

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package,
    )

    assert payload["status"] == "preflight_pass_non_authoritative"
    assert payload["contract_pass"] is False
    assert payload["preflight_contract_pass"] is True
    assert payload["external_vv_credit"] is False
    assert payload["trusted_rust_comparison_verified"] is False
    assert payload["operator_attestation_verified"] is False
    assert payload["legal_use_approved"] is False
    assert payload["promotion_eligible"] is False
    assert payload["phase3_closure_claim"] is False
    assert payload["phase4_closure_claim"] is False
    assert payload["developer_preview_release_candidate_claim"] is False
    assert payload["validation_result"]["distinct_reference_solver_count"] == 2
    assert payload["validation_result"]["checked_file_count"] == 8
    assert payload["validation_result"]["checksum_declared_count"] == 8
    assert payload["remaining_blockers"] == [
        "commercial_cross_solver_execution_missing",
        "trusted_rust_comparison_receipt_missing",
        "operator_comparison_trace_rows_missing",
        "phase4_two_solver_comparison_metrics_not_recorded",
        *module.SEMANTIC_AUTHORITY_BLOCKERS,
    ]


def test_operator_reference_ingest_validator_check_detects_drift(
    tmp_path: Path,
) -> None:
    out = tmp_path / "validator.json"
    module.write_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT, out_path=out
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    payload["contract_pass"] = True
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message = module.check_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        out_path=out,
    )

    assert ok is False
    assert message == "phase4_commercial_operator_reference_ingest_validator_mismatch"


@pytest.mark.parametrize(
    "payload",
    [
        '{"case_id":"a","case_id":"b"}',
        '{"case_id":"a","value":NaN}',
        '{"case_id":"a","value":Infinity}',
        '{"case_id":"a","value":1e9999}',
    ],
)
def test_operator_reference_ingest_rejects_ambiguous_or_nonfinite_json(
    tmp_path: Path, payload: str
) -> None:
    package = tmp_path / "package.json"
    package.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="strict JSON"):
        module.build_phase4_commercial_operator_reference_ingest_validator(
            repo_root=REPO_ROOT,
            package_path=package,
        )


def test_operator_reference_ingest_rejects_empty_normalized_placeholders(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    normalized = tmp_path / package["reference_solvers"][0]["normalized_result_file"]
    normalized.write_text("{}\n", encoding="utf-8")
    package["file_checksums"][
        package["reference_solvers"][0]["normalized_result_file"]
    ] = _sha256(normalized)
    package_path.write_text(
        json.dumps(package, allow_nan=False, sort_keys=True) + "\n", encoding="utf-8"
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["external_vv_credit"] is False
    assert any(
        blocker.startswith("normalized_reference_or_receipt_invalid:")
        for blocker in payload["validation_result"]["blockers"]
    )


def test_operator_reference_ingest_rejects_duplicate_reference_entity_ids(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    normalized_rel = package["reference_solvers"][0]["normalized_result_file"]
    normalized = tmp_path / normalized_rel
    reference = json.loads(normalized.read_text(encoding="utf-8"))
    reference["nodes"][1]["node_id"] = reference["nodes"][0]["node_id"]
    normalized.write_text(
        json.dumps(reference, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    package["file_checksums"][normalized_rel] = _sha256(normalized)
    receipt_rel = package["reference_solvers"][0]["normalization_receipt_file"]
    receipt = tmp_path / receipt_rel
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_payload["normalized_result_file_sha256"] = _sha256(normalized)
    receipt.write_text(
        json.dumps(receipt_payload, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    package["file_checksums"][receipt_rel] = _sha256(receipt)
    package_path.write_text(
        json.dumps(package, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    assert payload["status"] == "blocked"
    assert any(
        blocker.startswith("normalized_reference_entity_id_duplicate:")
        for blocker in payload["validation_result"]["blockers"]
    )


def test_operator_reference_ingest_rejects_intermediate_symlink(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    reference_root = tmp_path / "operator_refs"
    actual_root = tmp_path / "operator_refs_real"
    reference_root.rename(actual_root)
    reference_root.symlink_to(actual_root, target_is_directory=True)

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    assert payload["status"] == "blocked"
    assert any(
        blocker.startswith("operator_file_missing_or_outside_package:")
        for blocker in payload["validation_result"]["blockers"]
    )


def test_operator_reference_ingest_rejects_embedded_authority_claims(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["promotion_eligible"] = True
    package["permission_scope"]["legal_use_approved"] = True
    package["reference_solvers"][0]["operator_attested"] = True
    package_path.write_text(
        json.dumps(package, sort_keys=True) + "\n", encoding="utf-8"
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    assert payload["status"] == "blocked"
    assert payload["external_vv_credit"] is False
    assert payload["legal_use_approved"] is False
    assert payload["promotion_eligible"] is False
    assert {
        "forbidden_authority_claim:package:promotion_eligible",
        "forbidden_authority_claim:permission_scope:legal_use_approved",
        "forbidden_authority_claim:reference_solver:operator_attested",
    }.issubset(payload["validation_result"]["blockers"])


def test_synthetic_reference_cannot_impersonate_operator_export(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    solver = package["reference_solvers"][0]
    normalized_path = tmp_path / solver["normalized_result_file"]
    reference = json.loads(normalized_path.read_text(encoding="utf-8"))
    reference["source"]["tool"] = "synthetic_fixture"
    reference["source"]["origin"] = "synthetic_contract_fixture"
    normalized_path.write_text(
        json.dumps(reference, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    normalized_hash = _sha256(normalized_path)
    normalization_path = tmp_path / solver["normalization_receipt_file"]
    normalization = json.loads(normalization_path.read_text(encoding="utf-8"))
    normalization["normalized_result_file_sha256"] = normalized_hash
    normalization_path.write_text(
        json.dumps(normalization, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    package["file_checksums"][solver["normalized_result_file"]] = normalized_hash
    package["file_checksums"][solver["normalization_receipt_file"]] = _sha256(
        normalization_path
    )
    package_path.write_text(
        json.dumps(package, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    assert payload["status"] == "blocked"
    assert (
        "normalized_reference_raw_binding_invalid:" + solver["normalized_result_file"]
        in payload["validation_result"]["blockers"]
    )


def test_preflight_cannot_pass_when_file_hash_verification_is_disabled(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
        verify_file_hashes=False,
    )

    assert payload["status"] == "blocked"
    assert payload["preflight_contract_pass"] is False
    assert "file_hash_verification_disabled" in payload["validation_result"]["blockers"]


def test_one_solver_raw_adapter_preflight_creates_no_vv_credit(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["reference_solvers"] = package["reference_solvers"][:1]
    package["raw_result_files"] = [package["reference_solvers"][0]["raw_result_file"]]

    result = module.validate_operator_reference_package(
        package,
        package_root=tmp_path,
        require_normalized_results=False,
        require_two_reference_solvers=False,
    )

    assert result["status"] == "raw_preflight_pass_non_authoritative"
    assert result["preflight_contract_pass"] is True
    assert result["contract_pass"] is False
    assert result["normalization_only"] is True
    assert result["external_vv_credit"] is False
    assert result["trusted_rust_comparison_verified"] is False
    assert result["operator_attestation_verified"] is False
    assert result["legal_use_approved"] is False
    assert result["promotion_eligible"] is False


def test_solver_aliases_cannot_fake_two_distinct_reference_engines(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["reference_solvers"][1]["engine_name"] = "MIDAS GEN NX"
    package_path.write_text(
        json.dumps(package, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    blockers = payload["validation_result"]["blockers"]
    assert payload["status"] == "blocked"
    assert "reference_solver_name_duplicate" in blockers
    assert "two_reference_solver_comparison_not_available" in blockers


def test_normalized_references_must_bind_the_declared_raw_model(
    tmp_path: Path,
) -> None:
    package_path = _complete_package(tmp_path)
    package = json.loads(package_path.read_text(encoding="utf-8"))
    unrelated_model = tmp_path / "operator_refs" / "case-a" / "other-model.etabs"
    unrelated_model.write_text("unrelated-model", encoding="utf-8")
    unrelated_path = "operator_refs/case-a/other-model.etabs"
    package["raw_input_files"] = [unrelated_path]
    package["file_checksums"][unrelated_path] = _sha256(unrelated_model)
    package_path.write_text(
        json.dumps(package, allow_nan=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = module.build_phase4_commercial_operator_reference_ingest_validator(
        repo_root=REPO_ROOT,
        package_path=package_path,
    )

    assert payload["status"] == "blocked"
    assert (
        "normalized_reference_raw_model_binding_missing"
        in payload["validation_result"]["blockers"]
    )
