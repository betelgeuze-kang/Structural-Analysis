#!/usr/bin/env python3
"""Build the Frame3D modal/buckling nine-surface evidence receipt."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"{name}_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STATEFUL = _load_module(
    "f3_stateful_runner",
    ROOT / "implementation/phase1/run_f3_frame3d_stateful_material_vertical_evidence.py",
)
EXPLORER = _load_module("f3_results_explorer", ROOT / "implementation/phase1/results_explorer.py")
LINEAR = STATEFUL.LINEAR

from structural_analysis.analyses.buckling import (  # noqa: E402
    AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
    run_authoritative_linear_buckling,
)
from structural_analysis.analyses.modal import (  # noqa: E402
    AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
    run_authoritative_modal,
)
from structural_analysis.engine_v2.contracts.spectral_result import (  # noqa: E402
    create_spectral_result_ir,
    validate_spectral_result_ir_manifest,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes  # noqa: E402
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification,
    F3Evidence,
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)


MODEL_PATH = Path("tests/fixtures/model_ir_v2/frame_cantilever_modal_buckling.json")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_modal_buckling_vertical_evidence.json"
)
STATEFUL_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/"
    "f3_frame3d_stateful_material_vertical_evidence.json"
)
SCHEMA_VERSION = "f3-modal-buckling-vertical-evidence.v1"
TOLERANCE = 1.0e-8
MODE_COUNT = 2
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
SOURCE_PATHS = (
    MODEL_PATH,
    Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/analyses/modal.py"),
    Path("src/structural_analysis/analyses/buckling.py"),
    Path("src/structural_analysis/assembly/modal.py"),
    Path("src/structural_analysis/assembly/buckling.py"),
    Path("src/structural_analysis/solvers/modal/solver.py"),
    Path("src/structural_analysis/solvers/buckling/solver.py"),
    Path("src/structural_analysis/engine_v2/contracts/spectral_result.py"),
    Path("src/structural_analysis/schemas/spectral_result_ir_v1.schema.json"),
    Path("implementation/phase1/results_explorer.py"),
    Path("implementation/phase1/run_f3_frame3d_stateful_material_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_modal_buckling_vertical_evidence.py"),
    Path("tests/test_f3_modal_buckling_vertical_evidence.py"),
)


def _canonical_model(document: Any) -> Any:
    payload = document.to_dict()
    material = payload["materials"][0]["parameters"]
    section = payload["sections"][0]["parameters"]
    pattern = payload["load_patterns"][0]
    nodal_load = pattern["nodal_loads"][0]
    components = nodal_load["components_si"]
    neutral = {
        "schema_version": "structural-analysis-canonical-model.v1",
        "units": {"length": "m", "force": "kN"},
        "coordinate_system": {"axis_order": ["X", "Y", "Z"], "up_axis": "Z"},
        "nodes": [
            {"id": row["id"], "coordinates": row["coordinates_m"]}
            for row in payload["nodes"]
        ],
        "elements": [
            {
                "id": row["id"],
                "type": "frame",
                "nodes": row["node_ids"],
                "section": row["section_id"],
                "material": row["material_id"],
            }
            for row in payload["elements"]
        ],
        "materials": [
            {
                "id": payload["materials"][0]["id"],
                "type": "elastic",
                "elastic_modulus": float(material["elastic_modulus_pa"]) / 1000.0,
                "poisson_ratio": material["poisson_ratio"],
                "density": material["density_kg_m3"],
            }
        ],
        "sections": [
            {
                "id": payload["sections"][0]["id"],
                "type": "frame",
                "area": section["area_m2"],
                "iy": section["iy_m4"],
                "iz": section["iz_m4"],
                "torsional_constant": section["torsional_constant_m4"],
            }
        ],
        "loads": [
            {
                "node": nodal_load["node_id"],
                "components": [
                    float(components[label]) / 1000.0
                    for label in ("FX", "FY", "FZ", "MX", "MY", "MZ")
                ],
            }
        ],
        "supports": [
            {"node": row["node_id"], "dofs": list(row["dofs"])}
            for row in payload["constraints"]
        ],
        "unsupported_features": [],
        "warnings": [],
        "metadata": {
            "model_ir_content_hash": document.content_hash,
            "model_ir_model_id": document.model_id,
        },
    }
    return load_neutral_json_bytes(
        json.dumps(neutral, allow_nan=False, sort_keys=True).encode("utf-8"),
        source_path="memory://f3-modal-buckling-model-ir-adapter.json",
    )


def _node_shapes(mode: dict[str, Any], node_ids: tuple[str, ...]) -> list[list[float]]:
    rows = {row["node_id"]: row["components"] for row in mode["max_component_normalized_node_shapes"]}
    return [[float(rows[node_id][label]) for label in DOF_LABELS] for node_id in node_ids]


def _spectral_result(
    *, document: Any, analysis_type: str, solver_id: str, metrics: dict[str, Any]
) -> Any:
    node_ids = tuple(row["id"] for row in document.to_dict()["nodes"])
    if analysis_type == "modal":
        secondary_hash = metrics["mass_matrix_hash"]
        mode_rows = [
            {
                "mode_number": row["mode_number"],
                "eigenvalue": row["eigenvalue_rad2_per_s2"],
                "frequency_hz": row["frequency_hz"],
                "load_factor": None,
                "residual_relative_inf": row["residual_relative_inf"],
                "node_shapes": _node_shapes(row, node_ids),
            }
            for row in metrics["modes"]
        ]
    else:
        secondary_hash = metrics["geometric_stiffness_matrix_hash"]
        mode_rows = [
            {
                "mode_number": row["mode_number"],
                "eigenvalue": row["load_factor"],
                "frequency_hz": None,
                "load_factor": row["load_factor"],
                "residual_relative_inf": row["residual_relative_inf"],
                "node_shapes": _node_shapes(row, node_ids),
            }
            for row in metrics["modes"]
        ]
    return create_spectral_result_ir(
        result_id=f"f3.frame3d.{analysis_type}",
        analysis_type=analysis_type,
        model_ir_content_hash=document.content_hash,
        solver_id=solver_id,
        solver_receipt_hash=metrics["raw_result_hash"],
        stiffness_matrix_hash=metrics["stiffness_matrix_hash"],
        secondary_matrix_hash=secondary_hash,
        free_dof_map_hash=metrics["free_dof_map_hash"],
        node_ids=node_ids,
        tolerance=TOLERANCE,
        modes=mode_rows,
    )


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = STATEFUL.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_stateful_material_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt.from_dict(stage)
    persisted = json.loads((ROOT / STATEFUL_RECEIPT).read_text(encoding="utf-8"))
    replay = {
        "source_receipt_path": STATEFUL_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(STATEFUL_RECEIPT),
        "persisted_source_commit_sha": persisted["source_commit_sha"],
        "current_source_replay_executed": True,
        "replayed_source_commit_sha": source_commit,
        "vertical_stage_contract_passed": receipt.vertical_stage_contract_passed,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }
    return receipt, LINEAR._sha_payload(current["stage_gate"]), replay


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    model = _canonical_model(document)
    modal = run_authoritative_modal(model, tolerance=TOLERANCE, mode_count=MODE_COUNT)
    buckling = run_authoritative_linear_buckling(model, tolerance=TOLERANCE, mode_count=MODE_COUNT)
    modal_repeat = run_authoritative_modal(model, tolerance=TOLERANCE, mode_count=MODE_COUNT)
    buckling_repeat = run_authoritative_linear_buckling(model, tolerance=TOLERANCE, mode_count=MODE_COUNT)
    if modal.status != "ready" or buckling.status != "ready":
        raise RuntimeError("f3_modal_buckling_solver_not_ready")
    modal_metrics = modal.metrics
    buckling_metrics = buckling.metrics
    modal_ir = _spectral_result(
        document=document,
        analysis_type="modal",
        solver_id=AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
        metrics=modal_metrics,
    )
    buckling_ir = _spectral_result(
        document=document,
        analysis_type="linear_buckling",
        solver_id=AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
        metrics=buckling_metrics,
    )
    modal_replayed_ir = _spectral_result(
        document=document,
        analysis_type="modal",
        solver_id=AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
        metrics=modal_repeat.metrics,
    )
    buckling_replayed_ir = _spectral_result(
        document=document,
        analysis_type="linear_buckling",
        solver_id=AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
        metrics=buckling_repeat.metrics,
    )
    modal_manifest = modal_ir.to_manifest()
    buckling_manifest = buckling_ir.to_manifest()
    validate_spectral_result_ir_manifest(modal_manifest)
    validate_spectral_result_ir_manifest(buckling_manifest)
    exact_restart = bool(
        modal_ir == modal_replayed_ir
        and buckling_ir == buckling_replayed_ir
        and modal_metrics["raw_result_hash"] == modal_repeat.metrics["raw_result_hash"]
        and buckling_metrics["raw_result_hash"] == buckling_repeat.metrics["raw_result_hash"]
    )

    payload = document.to_dict()
    material = payload["materials"][0]["parameters"]
    section = payload["sections"][0]["parameters"]
    length = float(payload["nodes"][1]["coordinates_m"][0])
    e_kn_m2 = float(material["elastic_modulus_pa"]) / 1000.0
    mass_kn_s2_m2 = float(material["density_kg_m3"]) * float(section["area_m2"]) / 1000.0
    modal_coefficient = 12.4801921537537
    expected_modal_eigenvalues = sorted(
        modal_coefficient * e_kn_m2 * float(section[key]) / (mass_kn_s2_m2 * length**4)
        for key in ("iy_m4", "iz_m4")
    )
    expected_modal_frequencies = [math.sqrt(value) / (2.0 * math.pi) for value in expected_modal_eigenvalues]
    observed_modal_frequencies = [row["frequency_hz"] for row in modal_metrics["modes"]]
    maximum_modal_error = max(
        abs(actual - expected) / expected
        for expected, actual in zip(expected_modal_frequencies, observed_modal_frequencies, strict=True)
    )
    reference_compression_kn = abs(
        float(payload["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"]) / 1000.0
    )
    expected_buckling_factors = sorted(
        math.pi**2 * e_kn_m2 * float(section[key]) / (4.0 * length**2 * reference_compression_kn)
        for key in ("iy_m4", "iz_m4")
    )
    observed_buckling_factors = [row["load_factor"] for row in buckling_metrics["modes"]]
    maximum_buckling_error = max(
        abs(actual - expected) / expected
        for expected, actual in zip(expected_buckling_factors, observed_buckling_factors, strict=True)
    )
    maximum_residual = max(
        row["residual_relative_inf"]
        for metrics in (modal_metrics, buckling_metrics)
        for row in metrics["modes"]
    )

    modal_cards = []
    for row in modal_metrics["modes"]:
        participation = row["directional_participation"]
        shapes = _node_shapes(row, tuple(node["id"] for node in payload["nodes"]))
        card = EXPLORER.evaluate_mode_shape(
            mode_number=row["mode_number"],
            frequency_hz=row["frequency_hz"],
            amplitudes=tuple(value for shape in shapes for value in shape),
            participation_factors=tuple(participation[label]["participation_factor"] for label in ("UX", "UY", "UZ")),
            modal_mass_ratios=tuple(participation[label]["effective_modal_mass_ratio"] for label in ("UX", "UY", "UZ")),
        )
        modal_cards.append(asdict(card))
    workbench = {
        "schema_version": "f3-spectral-workbench-payload.v1",
        "model_ir_content_hash": document.content_hash,
        "node_ids": [row["id"] for row in payload["nodes"]],
        "modal_cards": modal_cards,
        "modal_summary": EXPLORER.build_results_summary(
            mode_shapes=tuple(EXPLORER.ModeShapeResult(**row) for row in modal_cards)
        ),
        "buckling_mode_shapes": [row["max_component_normalized_node_shapes"] for row in buckling_metrics["modes"]],
        "buckling_load_factors": observed_buckling_factors,
    }
    all_pass = bool(
        document.analysis_ready
        and not modal.unsupported_features
        and not buckling.unsupported_features
        and modal_metrics["fallback_used"] is False
        and modal_metrics["regularization_used"] is False
        and buckling_metrics["fallback_used"] is False
        and buckling_metrics["regularization_used"] is False
        and exact_restart
        and maximum_residual <= TOLERANCE
        and maximum_modal_error <= 2.0e-12
        and maximum_buckling_error <= 0.01
    )
    surface_artifacts: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "capability_profile": document.capability_profile,
            "analysis_ready": document.analysis_ready,
            "canonical_adapter_checksum": model.canonical_model_checksum,
        },
        "solver": {
            "modal_solver_id": AUTHORITATIVE_CPU_MODAL_SOLVER_ID,
            "buckling_solver_id": AUTHORITATIVE_CPU_BUCKLING_SOLVER_ID,
            "modal_status": modal.status,
            "buckling_status": buckling.status,
            "mode_count_each": MODE_COUNT,
            "maximum_residual_relative_inf": maximum_residual,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "result_ir": {
            "modal": modal_manifest,
            "linear_buckling": buckling_manifest,
            "manifest_valid": True,
        },
        "recovery": {
            "modal_node_shapes": [row["max_component_normalized_node_shapes"] for row in modal_metrics["modes"]],
            "modal_directional_participation": [row["directional_participation"] for row in modal_metrics["modes"]],
            "buckling_node_shapes": [row["max_component_normalized_node_shapes"] for row in buckling_metrics["modes"]],
            "reference_member_compression_forces": buckling_metrics["reference_member_compression_forces"],
        },
        "checkpoint": {
            "schema_version": "f3-spectral-checkpoint-pair.v1",
            "modal_checkpoint_hash": modal_ir.checkpoint_hash,
            "buckling_checkpoint_hash": buckling_ir.checkpoint_hash,
            "replayed_modal_checkpoint_hash": modal_replayed_ir.checkpoint_hash,
            "replayed_buckling_checkpoint_hash": buckling_replayed_ir.checkpoint_hash,
            "exact_restart": exact_restart,
        },
        "workbench": workbench,
        "benchmark": {
            "benchmark_id": "frame3d-cantilever-modal-and-euler-buckling.v1",
            "expected_modal_frequencies_hz": expected_modal_frequencies,
            "observed_modal_frequencies_hz": observed_modal_frequencies,
            "maximum_modal_relative_error": maximum_modal_error,
            "expected_buckling_load_factors": expected_buckling_factors,
            "observed_buckling_load_factors": observed_buckling_factors,
            "maximum_buckling_relative_error": maximum_buckling_error,
            "deterministic_replay": exact_restart,
        },
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "modal_reference": "closed_form_consistent_mass_cantilever_bending.v1",
            "buckling_reference": "euler_fixed_free_column.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "maximum_modal_relative_error": maximum_modal_error,
            "maximum_buckling_relative_error": maximum_buckling_error,
            "signature_verifier_waived": True,
        },
    }
    evidence = [
        F3Evidence(
            surface=surface,
            status="verified" if all_pass else "blocked",
            artifact_sha256=LINEAR._sha_payload(artifact),
        )
        for surface, artifact in surface_artifacts.items()
    ]
    predecessor, predecessor_hash, predecessor_replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="modal_buckling",
        source_commit_sha=source_commit,
        evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(
            status="waived",
            authority="user_authorized_signature_verifier_waiver",
            waiver_reason="User authorized signature-verifier omission for F3 self-verification.",
        ),
        predecessor_receipt=predecessor,
        predecessor_receipt_sha256=predecessor_hash,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit,
        "source_input_checksums": {path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS},
        "status": gate.status,
        "contract_pass": gate.vertical_stage_contract_passed,
        "predecessor_replay": predecessor_replay,
        "stage_gate": gate.to_dict(),
        "surface_artifacts": surface_artifacts,
        "claim_boundary": (
            "Closes a bounded two-mode dense CPU Frame3D modal and linear-buckling "
            "stage for one ModelIR cantilever with authoritative Spectral ResultIR, "
            "exact replay checkpoint, node-shape recovery, Workbench cards, and "
            "closed-form V&V. Sparse/large-model spectral extraction, shell modes, "
            "nonlinear buckling, and imperfection sensitivity remain outside."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = ROOT / args.out
    if args.check:
        if not out.is_file():
            print("f3_modal_buckling_vertical_evidence_mismatch")
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=str(recorded["source_commit_sha"]))
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if recorded.get("source_input_checksums") != payload["source_input_checksums"] or out.read_text(encoding="utf-8") != text:
            print("f3_modal_buckling_vertical_evidence_mismatch")
            return 1
        print("f3_modal_buckling_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    benchmark = payload["surface_artifacts"]["benchmark"]
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | "
        f"f1={benchmark['observed_modal_frequencies_hz'][0]} | "
        f"lambda1={benchmark['observed_buckling_load_factors'][0]}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
