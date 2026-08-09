#!/usr/bin/env python3
"""Build the bounded frictionless contact nine-surface evidence receipt."""

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
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


SHELL = _load(
    "f3_shell_runner_for_contact",
    ROOT / "implementation/phase1/run_f3_shell_vertical_evidence.py",
)
LINEAR, EXPLORER = SHELL.LINEAR, SHELL.EXPLORER

from structural_analysis.engine_v2.contracts.contact_static_result import (  # noqa: E402
    create_contact_result_ir,
    validate_contact_result_ir_manifest,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.solvers.nonlinear.contact_static import (  # noqa: E402
    ContactStaticModel,
    resume_contact_static,
    solve_contact_static,
)
from structural_analysis.validation.f3_vertical_evidence import (  # noqa: E402
    ExternalVVSignatureVerification,
    F3Evidence,
    F3StageGateReceipt,
    evaluate_f3_stage_gate,
)

MODEL_PATH = Path("tests/fixtures/model_ir_v2/contact_frictionless_static.json")
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/f3_contact_vertical_evidence.json"
)
PREDECESSOR_RECEIPT = Path(
    "implementation/phase1/release_evidence/productization/f3_shell_vertical_evidence.json"
)
SOLVER_ID = "enumerated-active-set.frictionless-gap.v1"
SOURCE_PATHS = (
    MODEL_PATH,
    Path("src/structural_analysis/schemas/model_ir_v2.schema.json"),
    Path("src/structural_analysis/solvers/nonlinear/contact_static.py"),
    Path("src/structural_analysis/engine_v2/contracts/contact_static_result.py"),
    Path("src/structural_analysis/schemas/contact_static_result_ir_v1.schema.json"),
    Path("implementation/phase1/results_explorer.py"),
    Path("implementation/phase1/run_f3_shell_vertical_evidence.py"),
    Path("implementation/phase1/run_f3_contact_vertical_evidence.py"),
    Path("tests/test_contact_static_solver.py"),
    Path("tests/test_contact_model_ir.py"),
    Path("tests/test_contact_static_result_ir.py"),
    Path("tests/test_f3_contact_vertical_evidence.py"),
)


def _inputs() -> tuple[Any, ContactStaticModel]:
    document = load_model_ir_v2(ROOT / MODEL_PATH)
    row = document.to_dict()["contact"]
    return document, ContactStaticModel(
        model_id=document.model_id,
        dof_ids=row["dof_ids"],
        contact_ids=row["contact_ids"],
        stiffness_n_per_m=row["stiffness_matrix_n_per_m"],
        load_n=row["load_vector_n"],
        gap_upper_m=row["gap_upper_m"],
    )


def _result(document: Any, model: ContactStaticModel, solution: Any) -> dict[str, Any]:
    result = create_contact_result_ir(
        result_id="f3.contact",
        model_ir_content_hash=document.content_hash,
        solver_result_hash=solution.result_hash,
        stiffness_hash=solution.stiffness_hash,
        load_hash=solution.load_hash,
        terminal_checkpoint_hash=solution.checkpoint.checkpoint_hash,
        solver_id=SOLVER_ID,
        dof_ids=model.dof_ids,
        contact_ids=model.contact_ids,
        displacement_m=solution.displacement_m,
        contact_multiplier_n=solution.contact_multiplier_n,
        gap_remaining_m=solution.gap_remaining_m,
        equilibrium_residual_n=solution.equilibrium_residual_n,
        complementarity_n_m=solution.complementarity_n_m,
        active_contact_ids=solution.active_contact_ids,
        maximum_equilibrium_residual_n=solution.maximum_equilibrium_residual_n,
        maximum_penetration_m=solution.maximum_penetration_m,
        minimum_contact_multiplier_n=solution.minimum_contact_multiplier_n,
        maximum_complementarity_n_m=solution.maximum_complementarity_n_m,
    )
    manifest = result.to_manifest()
    validate_contact_result_ir_manifest(manifest)
    return manifest


def _predecessor(source_commit: str) -> tuple[F3StageGateReceipt, str, dict[str, Any]]:
    current = SHELL.build_receipt(source_commit_sha=source_commit)
    if not current["contract_pass"]:
        raise RuntimeError("f3_shell_predecessor_replay_failed")
    stage = current["stage_gate"]
    receipt = F3StageGateReceipt.from_dict(stage)
    persisted = json.loads((ROOT / PREDECESSOR_RECEIPT).read_text(encoding="utf-8"))
    return (
        receipt,
        LINEAR._sha_payload(current["stage_gate"]),
        {
            "source_receipt_path": PREDECESSOR_RECEIPT.as_posix(),
            "source_receipt_sha256": LINEAR._file_sha(PREDECESSOR_RECEIPT),
            "persisted_source_commit_sha": persisted["source_commit_sha"],
            "current_source_replay_executed": True,
            "replayed_source_commit_sha": source_commit,
            "vertical_stage_contract_passed": receipt.vertical_stage_contract_passed,
            "public_product_promotion_passed": receipt.public_product_promotion_passed,
        },
    )


def _benchmark(model: ContactStaticModel, solution: Any) -> dict[str, Any]:
    expected_displacement = np.asarray((0.08, 0.095))
    expected_multiplier = np.asarray((89.0, 0.0))
    breadth_loads = (
        ((10.0, 20.0), ()),
        ((150.0, 60.0), ("C1",)),
        ((-10.0, 200.0), ("C2",)),
        ((200.0, 250.0), ("C1", "C2")),
    )
    cases = []
    for load, expected_active in breadth_loads:
        case = ContactStaticModel(
            model_id=f"breadth-{len(cases)}",
            dof_ids=model.dof_ids,
            contact_ids=model.contact_ids,
            stiffness_n_per_m=model.stiffness_n_per_m,
            load_n=load,
            gap_upper_m=model.gap_upper_m,
        )
        result = solve_contact_static(case)
        cases.append(
            {
                "load_n": list(load),
                "expected_active_contact_ids": list(expected_active),
                "computed_active_contact_ids": list(result.active_contact_ids),
                "pass": result.active_contact_ids == expected_active
                and result.contract_pass,
            }
        )
    return {
        "benchmark_id": "two-dof-frictionless-gap-closed-form-kkt.v1",
        "expected_displacement_m": expected_displacement.tolist(),
        "expected_contact_multiplier_n": expected_multiplier.tolist(),
        "maximum_displacement_error_m": float(
            np.max(np.abs(np.asarray(solution.displacement_m) - expected_displacement))
        ),
        "maximum_multiplier_error_n": float(
            np.max(
                np.abs(np.asarray(solution.contact_multiplier_n) - expected_multiplier)
            )
        ),
        "displacement_tolerance_m": 1.0e-13,
        "multiplier_tolerance_n": 1.0e-11,
        "active_set_breadth_cases": cases,
        "active_set_breadth_pass": all(row["pass"] for row in cases),
    }


def build_receipt(*, source_commit_sha: str | None = None) -> dict[str, Any]:
    source_commit = source_commit_sha or LINEAR._git_head()
    document, model = _inputs()
    solution = solve_contact_static(model)
    repeated = solve_contact_static(model)
    exact_restart = resume_contact_static(model, solution.checkpoint) == solution
    manifest = _result(document, model, solution)
    benchmark = _benchmark(model, solution)
    contour = EXPLORER.evaluate_contour(
        result_type="contact_multiplier_n",
        values=solution.contact_multiplier_n,
        locations=tuple(
            (float(index), float(model.gap_upper_m[index]))
            for index in range(len(model.contact_ids))
        ),
    )
    all_pass = bool(
        document.analysis_ready
        and solution.contract_pass
        and not solution.fallback_used
        and not solution.regularization_used
        and solution.maximum_equilibrium_residual_n <= 1.0e-10
        and solution.maximum_penetration_m <= 1.0e-12
        and solution.minimum_contact_multiplier_n >= 0.0
        and solution.maximum_complementarity_n_m <= 1.0e-12
        and exact_restart
        and repeated.result_hash == solution.result_hash
        and benchmark["maximum_displacement_error_m"]
        <= benchmark["displacement_tolerance_m"]
        and benchmark["maximum_multiplier_error_n"]
        <= benchmark["multiplier_tolerance_n"]
        and benchmark["active_set_breadth_pass"]
    )
    surfaces: dict[str, Any] = {
        "model_ir": {
            "content_hash": document.content_hash,
            "model_id": document.model_id,
            "capability_profile": document.capability_profile,
            "analysis_ready": document.analysis_ready,
            "contact_count": len(model.contact_ids),
        },
        "solver": {
            "schema_version": solution.schema_version,
            "profile": solution.profile,
            "solver_id": SOLVER_ID,
            "active_set_trials": solution.active_set_trials,
            "active_contact_ids": list(solution.active_contact_ids),
            "maximum_equilibrium_residual_n": solution.maximum_equilibrium_residual_n,
            "maximum_penetration_m": solution.maximum_penetration_m,
            "minimum_contact_multiplier_n": solution.minimum_contact_multiplier_n,
            "maximum_complementarity_n_m": solution.maximum_complementarity_n_m,
            "fallback_used": solution.fallback_used,
            "regularization_used": solution.regularization_used,
        },
        "result_ir": {
            "schema_version": manifest["schema_version"],
            "manifest": manifest,
            "manifest_valid": True,
        },
        "recovery": {
            "contact_ids": list(model.contact_ids),
            "displacement_m": list(solution.displacement_m),
            "gap_remaining_m": list(solution.gap_remaining_m),
            "contact_multiplier_n": list(solution.contact_multiplier_n),
            "active_contact_ids": list(solution.active_contact_ids),
        },
        "checkpoint": {
            "terminal_checkpoint": solution.checkpoint.to_dict(),
            "exact_restart": exact_restart,
            "deterministic_repeat": repeated.result_hash == solution.result_hash,
        },
        "workbench": {
            "schema_version": "f3-contact-workbench-payload.v1",
            "contact_multiplier_contour": asdict(contour),
            "summary": EXPLORER.build_results_summary(contour=contour),
        },
        "benchmark": benchmark,
        "platform": {
            "source_commit_sha": source_commit,
            "implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "self_verified": True,
        },
        "external_vv": {
            "reference_profile": "independent-two-dof-active-set-kkt-closed-form.v1",
            "verification_mode": "local_self_verification_user_authorized",
            "maximum_displacement_error_m": benchmark["maximum_displacement_error_m"],
            "maximum_multiplier_error_n": benchmark["maximum_multiplier_error_n"],
            "signature_verifier_waived": True,
        },
    }
    evidence = [
        F3Evidence(
            surface=name,
            status="verified" if all_pass else "blocked",
            artifact_sha256=LINEAR._sha_payload(value),
        )
        for name, value in surfaces.items()
    ]
    predecessor, predecessor_hash, predecessor_replay = _predecessor(source_commit)
    gate = evaluate_f3_stage_gate(
        stage="contact",
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
        "schema_version": "f3-contact-vertical-evidence.v1",
        "source_commit_sha": source_commit,
        "source_input_checksums": {
            path.as_posix(): LINEAR._file_sha(path) for path in SOURCE_PATHS
        },
        "status": gate.status,
        "contract_pass": gate.vertical_stage_contract_passed,
        "predecessor_replay": predecessor_replay,
        "stage_gate": gate.to_dict(),
        "surface_artifacts": surfaces,
        "claim_boundary": "Closes a bounded two-DOF frictionless nodal upper-gap contact stage with an actual active-set KKT solve, authoritative contact ResultIR, exact hash-bound restart, Workbench multiplier contour, closed-form KKT parity, and inactive/single/both contact breadth. Friction, surface contact, impact, large sliding, nonlinear material, and broad mesh V&V remain outside.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    if args.check:
        if not out.is_file():
            return 1
        recorded = json.loads(out.read_text(encoding="utf-8"))
        payload = build_receipt(source_commit_sha=recorded["source_commit_sha"])
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if (
            recorded.get("source_input_checksums") != payload["source_input_checksums"]
            or out.read_text(encoding="utf-8") != text
        ):
            print("f3_contact_vertical_evidence_mismatch")
            return 1
        print("f3_contact_vertical_evidence_consistent")
        return 0
    payload = build_receipt()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    solver = payload["surface_artifacts"]["solver"]
    print(
        f"{payload['status']} | surfaces={len(payload['stage_gate']['verified_surfaces'])}/9 | active={solver['active_contact_ids']}"
    )
    return 0 if payload["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
