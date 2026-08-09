#!/usr/bin/env python3
"""Build the bounded linear shell nine-surface evidence receipt."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"{name}_import_failed")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


NONLINEAR = _load("f3_nonlinear_mdof_runner_for_shell", ROOT / "implementation/phase1/run_f3_nonlinear_mdof_vertical_evidence.py")
LINEAR, EXPLORER = NONLINEAR.LINEAR, NONLINEAR.EXPLORER

from structural_analysis.elements.shell_triangle import shell_triangle_matrices  # noqa: E402
from structural_analysis.engine_v2.contracts.shell_static_result import (  # noqa: E402
    create_shell_result_ir, validate_shell_result_ir_manifest,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.solvers.linear.shell_static import (  # noqa: E402
    ShellStaticModel, resume_shell_static, solve_shell_static,
)
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification, F3Evidence, F3StageGateReceipt,
    evaluate_f3_stage_gate,
)

MODEL_PATH = Path("tests/fixtures/model_ir_v2/shell_square_linear_static.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/f3_shell_vertical_evidence.json")
PREDECESSOR_RECEIPT = Path("implementation/phase1/release_evidence/productization/f3_nonlinear_mdof_vertical_evidence.json")
SOLVER_ID = "dense.direct.cst-mindlin-shell3.v1"
SOURCE_PATHS = (
    MODEL_PATH, Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/model_ir/validation.py"),
    Path("src/structural_analysis/elements/shell_triangle.py"),
    Path("src/structural_analysis/solvers/linear/shell_static.py"),
    Path("src/structural_analysis/engine_v2/contracts/shell_static_result.py"),
    Path("src/structural_analysis/schemas/shell_static_result_ir_v1.schema.json"),
    Path("implementation/phase1/results_explorer.py"),
    Path("implementation/phase1/run_f3_nonlinear_mdof_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_shell_vertical_evidence.py"),
    Path("tests/test_shell_triangle_element.py"), Path("tests/test_shell_static_solver.py"),
    Path("tests/test_shell_model_ir.py"), Path("tests/test_shell_static_result_ir.py"),
    Path("tests/test_f3_shell_vertical_evidence.py"),
)


def _inputs() -> tuple[Any, ShellStaticModel]:
    document = load_model_ir_v2(ROOT / MODEL_PATH); payload = document.to_dict()
    node_ids = tuple(row["id"] for row in payload["nodes"]); node_index = {value: index for index, value in enumerate(node_ids)}
    material = payload["materials"][0]["parameters"]; section = payload["sections"][0]["parameters"]
    dof_index = {name: index for index, name in enumerate(payload["dof_components"])}
    restrained = tuple(sorted(6 * node_index[row["node_id"]] + dof_index[name] for row in payload["constraints"] for name in row["dofs"]))
    load = np.zeros(6 * len(node_ids))
    component_index = {"FX": 0, "FY": 1, "FZ": 2, "MX": 3, "MY": 4, "MZ": 5}
    for pattern in payload["load_patterns"]:
        for row in pattern["nodal_loads"]:
            for name, value in row["components_si"].items():
                load[6 * node_index[row["node_id"]] + component_index[name]] += float(value)
    model = ShellStaticModel(
        model_id=document.model_id, node_ids=node_ids,
        node_coordinates_m=tuple(row["coordinates_m"] for row in payload["nodes"]),
        element_ids=tuple(row["id"] for row in payload["elements"]),
        element_connectivity=tuple(tuple(node_index[value] for value in row["node_ids"]) for row in payload["elements"]),
        elastic_modulus_pa=material["elastic_modulus_pa"], poisson_ratio=material["poisson_ratio"],
        thickness_m=section["thickness_m"], restrained_dofs=restrained, load_global_n_nm=load,
    )
    return document, model


def _result(document: Any, model: ShellStaticModel, solution: Any) -> dict[str, Any]:
    result = create_shell_result_ir(
        result_id="f3.shell", model_ir_content_hash=document.content_hash,
        solver_result_hash=solution.result_hash, stiffness_hash=solution.stiffness_hash,
        load_hash=solution.load_hash, terminal_checkpoint_hash=solution.checkpoint.checkpoint_hash,
        solver_id=SOLVER_ID, node_ids=model.node_ids, element_ids=model.element_ids,
        displacement_global=solution.displacement_global, reaction_global_n_nm=solution.reaction_global_n_nm,
        equilibrium_residual_global_n_nm=solution.equilibrium_residual_global_n_nm,
        element_results=[asdict(row) for row in solution.element_results],
        maximum_free_residual=solution.maximum_free_residual,
        strain_energy_j=solution.strain_energy_j, external_work_j=solution.external_work_j,
    )
    manifest = result.to_manifest(); validate_shell_result_ir_manifest(manifest)
    return manifest


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = NONLINEAR.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_nonlinear_mdof_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt(
        schema="f3-vertical-evidence-gate.v1", stage="nonlinear_mdof", stage_index=7,
        source_commit_sha=source_commit, required_surfaces=tuple(stage["required_surfaces"]),
        verified_surfaces=tuple(stage["verified_surfaces"]),
        evidence_artifact_sha256=tuple(sorted(stage["evidence_artifact_sha256"].items())),
        predecessor_stage="mdof_linear_transient", predecessor_receipt_sha256=stage["predecessor_receipt_sha256"],
        external_vv_signature_status="waived", blockers=tuple(stage["blockers"]),
        public_product_promotion_passed=bool(stage["public_product_promotion_passed"]),
    )
    persisted = json.loads((ROOT / PREDECESSOR_RECEIPT).read_text(encoding="utf-8"))
    return receipt, LINEAR._sha_payload(current["stage_gate"]), {
        "source_receipt_path": PREDECESSOR_RECEIPT.as_posix(),
        "source_receipt_sha256": LINEAR._file_sha(PREDECESSOR_RECEIPT),
        "persisted_source_commit_sha": persisted["source_commit_sha"],
        "current_source_replay_executed": True, "replayed_source_commit_sha": source_commit,
        "public_product_promotion_passed": receipt.public_product_promotion_passed,
    }


def _patch_benchmark(model: ShellStaticModel) -> dict[str, Any]:
    points = np.asarray(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)))
    matrices = shell_triangle_matrices(points, elastic_modulus_pa=model.elastic_modulus_pa, poisson_ratio=model.poisson_ratio, thickness_m=model.thickness_m)
    epsilon = 1.0e-6; displacement = np.zeros(18)
    for node, point in enumerate(points):
        displacement[6 * node] = epsilon * point[0]
    computed = 0.5 * float(displacement @ matrices.stiffness_n_per_m @ displacement)
    expected = 0.5 * matrices.area_m2 * matrices.membrane_d_n_per_m[0, 0] * epsilon**2
    rigid = np.zeros(18); rigid[0::6] = 0.7; rigid[1::6] = -0.2; rigid[2::6] = 0.4
    rigid_energy = 0.5 * float(rigid @ matrices.stiffness_n_per_m @ rigid)
    rigid_relative_residual = float(
        np.linalg.norm(matrices.stiffness_n_per_m @ rigid, ord=np.inf)
        / (np.linalg.norm(matrices.stiffness_n_per_m, ord=np.inf) * np.linalg.norm(rigid, ord=np.inf))
    )
    return {
        "benchmark_id": "shell3-constant-membrane-strain-and-rigid-translation.v1",
        "computed_constant_strain_energy_j": computed, "closed_form_energy_j": expected,
        "relative_energy_error": abs(computed - expected) / expected,
        "relative_energy_tolerance": 1.0e-12, "rigid_translation_energy_j": rigid_energy,
        "rigid_translation_relative_residual": rigid_relative_residual,
        "rigid_relative_residual_tolerance": 1.0e-14,
    }


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head(); document, model = _inputs()
    solution = solve_shell_static(model); repeated = solve_shell_static(model)
    replay = resume_shell_static(model, solution.checkpoint); exact_restart = replay == solution
    manifest = _result(document, model, solution); benchmark = _patch_benchmark(model)
    displacement = np.asarray(solution.displacement_global).reshape((-1, 6)); coordinates = np.asarray(model.node_coordinates_m)
    contour = EXPLORER.evaluate_contour(
        result_type="shell_displacement_uz_m", values=tuple(map(float, displacement[:, 2])),
        locations=tuple((float(row[0]), float(row[1])) for row in coordinates),
    )
    all_pass = bool(
        document.analysis_ready and solution.contract_pass and not solution.fallback_used
        and not solution.regularization_used and solution.maximum_free_residual <= 1.0e-10
        and abs(solution.strain_energy_j - solution.external_work_j) <= 1.0e-12
        and exact_restart and repeated.result_hash == solution.result_hash
        and benchmark["relative_energy_error"] <= benchmark["relative_energy_tolerance"]
        and benchmark["rigid_translation_relative_residual"] <= benchmark["rigid_relative_residual_tolerance"]
    )
    surfaces: dict[str, Any] = {
        "model_ir": {"content_hash": document.content_hash, "model_id": document.model_id, "capability_profile": document.capability_profile, "analysis_ready": document.analysis_ready, "node_count": len(model.node_ids), "element_count": len(model.element_ids)},
        "solver": {"schema_version": solution.schema_version, "profile": solution.profile, "solver_id": SOLVER_ID, "free_dof_count": solution.free_dof_count, "maximum_free_residual": solution.maximum_free_residual, "fallback_used": solution.fallback_used, "regularization_used": solution.regularization_used},
        "result_ir": {"schema_version": manifest["schema_version"], "manifest": manifest, "manifest_valid": True},
        "recovery": {"element_results": manifest["element_results"], "strain_energy_sum_j": sum(row.strain_energy_j for row in solution.element_results), "reaction_vertical_sum_n": sum(solution.reaction_global_n_nm[2::6])},
        "checkpoint": {"terminal_checkpoint": solution.checkpoint.to_dict(), "exact_restart": exact_restart, "deterministic_repeat": repeated.result_hash == solution.result_hash},
        "workbench": {"schema_version": "f3-shell-workbench-payload.v1", "contour": asdict(contour), "summary": EXPLORER.build_results_summary(contour=contour)},
        "benchmark": benchmark,
        "platform": {"source_commit_sha": source_commit, "implementation": platform.python_implementation(), "python_version": platform.python_version(), "numpy_version": np.__version__, "self_verified": True},
        "external_vv": {"reference_profile": "closed-form-constant-strain-patch-and-rigid-body-invariance.v1", "verification_mode": "local_self_verification_user_authorized", "relative_energy_error": benchmark["relative_energy_error"], "signature_verifier_waived": True},
    }
    evidence = [F3Evidence(surface=name, status="verified" if all_pass else "blocked", artifact_sha256=LINEAR._sha_payload(value)) for name, value in surfaces.items()]
    predecessor, predecessor_hash, predecessor_replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="shell", source_commit_sha=source_commit, evidence=evidence,
        external_vv_signature=ExternalVVSignatureVerification(status="waived", authority="user_authorized_signature_verifier_waiver", waiver_reason="User authorized signature-verifier omission for F3 self-verification."),
        predecessor_receipt=predecessor, predecessor_receipt_sha256=predecessor_hash,
    )
    return {
        "schema_version": "f3-shell-vertical-evidence.v1", "source_commit_sha": source_commit,
        "source_input_checksums": {path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS},
        "status": "ready" if gate.public_product_promotion_passed else "blocked", "contract_pass": gate.public_product_promotion_passed,
        "predecessor_replay": predecessor_replay,
        "stage_gate": {"stage": gate.stage, "stage_index": gate.stage_index, "source_commit_sha": gate.source_commit_sha, "required_surfaces": list(gate.required_surfaces), "verified_surfaces": list(gate.verified_surfaces), "evidence_artifact_sha256": dict(gate.evidence_artifact_sha256), "predecessor_stage": gate.predecessor_stage, "predecessor_receipt_sha256": gate.predecessor_receipt_sha256, "external_vv_signature_status": gate.external_vv_signature_status, "blockers": list(gate.blockers), "public_product_promotion_passed": gate.public_product_promotion_passed},
        "surface_artifacts": surfaces,
        "claim_boundary": "Closes a bounded four-node, two-triangle, small-displacement linear CST membrane/Mindlin shell stage with physical equilibrium, authoritative recovery ResultIR, exact hash-bound restart, Workbench contour, and closed-form patch/rigid-mode verification. Nonlinear shell, higher-order elements, openings, broad mesh V&V, and contact remain outside.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--out", type=Path, default=DEFAULT_OUT); parser.add_argument("--check", action="store_true"); args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if args.check:
        if not out.is_file(): return 1
        recorded = json.loads(out.read_text(encoding="utf-8")); payload = build_receipt(source_commit_sha=recorded["source_commit_sha"])
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if recorded.get("source_input_checksums") != payload["source_input_checksums"] or out.read_text(encoding="utf-8") != text:
            print("f3_shell_vertical_evidence_mismatch"); return 1
        print("f3_shell_vertical_evidence_consistent"); return 0
    payload = build_receipt(); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    solver = payload["surface_artifacts"]["solver"]
    print(f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | residual={solver['maximum_free_residual']:.3e}")
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
