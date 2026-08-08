#!/usr/bin/env python3
"""Aggregate the exact N1 CPU mathematical exit criteria without closing G1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt import (  # noqa: E402
    check_receipt as check_full_mesh_receipt,
)
from build_n1_stateful_material_matrix_free_newton_breadth_receipt import (  # noqa: E402
    check_receipt as check_material_breadth_receipt,
)
from release_evidence_metadata import commit_bound_input_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
FULL_MESH_RECEIPT = (
    PRODUCTIZATION
    / "g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.json"
)
MATERIAL_BREADTH_RECEIPT = (
    PRODUCTIZATION / "n1_stateful_material_matrix_free_newton_breadth_receipt.json"
)
DEFAULT_OUT = PRODUCTIZATION / "n1_cpu_mathematical_closure_gate.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/n1_cpu_mathematical_closure_gate_v1.schema.json"
)
SCRIPT_PATH = Path("scripts/build_n1_cpu_mathematical_closure_gate.py")
FULL_MESH_BUILDER_PATH = Path(
    "scripts/"
    "build_g1_mgt_state_updated_frame_axial_matrix_free_newton_continuation_receipt.py"
)
MATERIAL_BREADTH_BUILDER_PATH = Path(
    "scripts/build_n1_stateful_material_matrix_free_newton_breadth_receipt.py"
)
PROVENANCE_HELPER_PATH = Path("scripts/release_evidence_metadata.py")
VERSION = "n1-cpu-mathematical-closure-gate.v1"
SOURCE_INPUTS = (
    SCRIPT_PATH,
    SCHEMA,
    FULL_MESH_BUILDER_PATH,
    MATERIAL_BREADTH_BUILDER_PATH,
    PROVENANCE_HELPER_PATH,
    FULL_MESH_RECEIPT,
    MATERIAL_BREADTH_RECEIPT,
)
EVALUATION_ORDER = (
    "physical_residual_definition_fixed",
    "residual_jacobian_directional_consistency",
    "accepted_state_tangent_refresh",
    "material_trial_commit_rollback",
    "line_search_physical_merit",
    "increment_gate",
    "fallback_zero",
    "load_scale_0p656_reproduced",
    "adaptive_continuation",
    "full_load_1p0",
    "residual_pass",
    "increment_pass",
    "actual_mgt_full_equation_space",
    "material_family_breadth",
    "regularization_zero",
    "exact_restart",
)
CLAIM_BOUNDARY = (
    "This aggregate closes the separately scoped N1 CPU mathematical milestone by "
    "combining exact-replayed actual-MGT 70,560-equation finite-chord axial "
    "equilibrium evidence with a separate four-family stateful material Newton "
    "breadth gate, exactly as required by the N1 exit criteria. It does not claim "
    "that the four stateful laws are connected to the actual-MGT full frame/shell "
    "operator, does not upgrade reference-geometry bending/torsion, and does not "
    "close the production ROCm/HIP G1 milestone."
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("n1_closure_json_object_required")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _receipt_hash(payload: dict[str, Any]) -> str:
    return _sha256_bytes(
        _canonical_bytes(
            {key: value for key, value in payload.items() if key != "receipt_hash"}
        )
    )


def _git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _git_commit_is_ancestor(root: Path, source_commit_sha: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit_sha, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _aggregate_source(
    *, root: Path, source_commit_sha: str
) -> tuple[dict[str, Any], bool]:
    source_is_ancestor = _git_commit_is_ancestor(root, source_commit_sha)
    metadata = commit_bound_input_metadata(
        SOURCE_INPUTS,
        repo_root=root,
        source_commit_sha=source_commit_sha,
        additional_blockers=(
            () if source_is_ancestor else ("source_commit_not_ancestor_of_head",)
        ),
    )
    provenance = metadata["source_input_provenance"]
    generator_script_sha256 = _sha256_bytes((root / SCRIPT_PATH).read_bytes())
    generator_matches_source = bool(
        metadata["input_checksums"].get(SCRIPT_PATH.as_posix())
        == generator_script_sha256
    )
    commit_bound = bool(
        source_is_ancestor and provenance["contract_pass"] and generator_matches_source
    )
    return (
        {
            "source_commit_sha": metadata["source_commit_sha"],
            "source_commit_is_ancestor_of_head": source_is_ancestor,
            "generator_script_sha256": generator_script_sha256,
            "generator_matches_source_commit": generator_matches_source,
            "generator_source_control_state": (
                "commit_bound" if commit_bound else "working_tree"
            ),
            "input_checksums": metadata["input_checksums"],
            "source_input_provenance": provenance,
        },
        commit_bound,
    )


def _closure(evaluations: dict[str, bool]) -> bool:
    return set(evaluations) == set(EVALUATION_ORDER) and all(evaluations.values())


def _verify_upstreams(root: Path) -> None:
    for passed, reason in (
        check_full_mesh_receipt(repo_root=root),
        check_material_breadth_receipt(repo_root=root),
    ):
        if not passed:
            raise ValueError(f"n1_closure_upstream_invalid:{reason}")


def build(
    *,
    root: Path = ROOT,
    generated_at: str | None = None,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    _verify_upstreams(root)
    aggregate_source, generator_committed = _aggregate_source(
        root=root,
        source_commit_sha=source_commit_sha or _git_head(root),
    )
    full_path = root / FULL_MESH_RECEIPT
    material_path = root / MATERIAL_BREADTH_RECEIPT
    full = _read(full_path)
    material = _read(material_path)
    continuation = full["continuation"]
    continuation_metrics = continuation["metrics"]
    strict = full["strict_g1_gate_full_load_probe"]
    strict_result = strict["result"]
    strict_metrics = strict_result["metrics"]
    adaptive = full["adaptive_step_reduction_replay"]
    adaptive_metrics = adaptive["result"]["metrics"]
    reproduction = full["load_scale_0p656_reproduction"]
    operator_audit = full["matrix_free_operator_recurrence_binding_audit"]
    residual_contract = full["adapter_binding"]["residual_evaluation_contract"]
    geometry = full["adapter_binding"]["state_updated_frame_axial_geometry"]

    evaluations = {
        "physical_residual_definition_fixed": bool(
            residual_contract["residual_formula"]["residual_sign_convention"]
            == "internal_minus_external"
            and residual_contract["residual_formula_hash"]
            == operator_audit["residual_formula_hash"]
        ),
        "residual_jacobian_directional_consistency": bool(
            full["claims"]["residual_tangent_parent_consistency_audited"]
            and full["local_quadratic_convergence_audit"]["contract_pass"]
            and material["all_family_tangent_checks_passed"]
        ),
        "accepted_state_tangent_refresh": bool(
            continuation["claims"]["accepted_iterate_tangent_refresh"]
            and continuation_metrics["accepted_iterate_tangent_refresh_count"] > 0
        ),
        "material_trial_commit_rollback": bool(
            material["claims"]["trial_commit_rollback"]
            and material["all_family_material_commits_observed"]
            and material["all_family_failed_step_rollbacks_byte_exact"]
        ),
        "line_search_physical_merit": bool(
            continuation["claims"]["line_search_physical_merit"]
            and continuation_metrics["physical_merit_profile"]
            == "half_squared_physical_residual_l2.v1"
            and material["line_search_merit"] == "half_squared_physical_residual_l2.v1"
        ),
        "increment_gate": bool(
            continuation_metrics["residual_and_increment_acceptance_gate"]
            and material["all_family_increment_gates_passed"]
        ),
        "fallback_zero": bool(
            continuation_metrics["fallback_count"] == 0
            and strict_metrics["fallback_count"] == 0
            and adaptive_metrics["fallback_count"] == 0
            and material["fallback_count"] == 0
        ),
        "load_scale_0p656_reproduced": bool(
            full["claims"]["actual_load_scale_0p656_reproduced"]
            and reproduction["contract_pass"]
            and reproduction["residual_gate_passed"]
            and reproduction["increment_gate_passed"]
        ),
        "adaptive_continuation": bool(
            full["claims"]["actual_adaptive_step_reduction_path"]
            and adaptive["contract_pass"]
            and adaptive_metrics["failed_step_count"] == 2
            and adaptive_metrics["target_load_factor_reached"]
        ),
        "full_load_1p0": bool(
            strict["full_load_target_reached"]
            and strict_metrics["final_load_factor"] == 1.0
            and continuation_metrics["target_load_factor_reached"]
        ),
        "residual_pass": bool(
            strict["residual_gate_passed"]
            and strict["final_residual_inf_n"]
            <= strict["configured_residual_tolerance_inf_n"]
        ),
        "increment_pass": bool(
            strict_metrics["residual_and_increment_acceptance_gate"]
            and strict_metrics["maximum_accepted_relative_increment"] <= 1.0e-4
        ),
        "actual_mgt_full_equation_space": bool(
            strict_metrics["equation_count"] == 70_560
            and continuation_metrics["equation_count"] == 70_560
            and geometry["element_count"] == 5_572
            and geometry["property_fallback_count"] == 0
        ),
        "material_family_breadth": bool(
            material["family_contract_pass"]
            and material["material_family_count"] == 4
            and material["claims"][
                "stateful_material_matrix_free_newton_family_breadth"
            ]
        ),
        "regularization_zero": bool(
            continuation_metrics["regularization_count"] == 0
            and strict_metrics["regularization_count"] == 0
            and adaptive_metrics["regularization_count"] == 0
            and material["regularization_count"] == 0
        ),
        "exact_restart": bool(
            full["claims"]["midpoint_restart_exact"]
            and full["claims"]["adaptive_midpoint_restart_exact"]
            and full["restart_replay"]["final_vector_bytes_exact"]
            and adaptive["final_vector_bytes_exact"]
            and material["all_family_checkpoint_restarts_byte_exact"]
        ),
    }
    closed = _closure(evaluations)
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "",
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "ready" if closed else "partial",
        "contract_pass": True,
        "aggregate_source": aggregate_source,
        "sources": {
            "actual_mgt_full_mesh": {
                "path": FULL_MESH_RECEIPT.as_posix(),
                "file_sha256": _sha256_bytes(full_path.read_bytes()),
                "schema_version": full["schema_version"],
                "source_commit_sha": full["source_commit_sha"],
                "source_commit_exact_replay": full["source_commit_exact_replay_claim"],
            },
            "material_family_breadth": {
                "path": MATERIAL_BREADTH_RECEIPT.as_posix(),
                "file_sha256": _sha256_bytes(material_path.read_bytes()),
                "schema_version": material["schema_version"],
                "source_commit_sha": material["source_commit_sha"],
                "source_commit_exact_replay": material[
                    "source_commit_exact_replay_claim"
                ],
            },
        },
        "evaluations": evaluations,
        "metrics": {
            "free_equation_count": strict_metrics["equation_count"],
            "full_mesh_frame_element_count": geometry["element_count"],
            "final_load_factor": strict_metrics["final_load_factor"],
            "final_residual_inf_n": strict["final_residual_inf_n"],
            "residual_tolerance_inf_n": strict["configured_residual_tolerance_inf_n"],
            "maximum_accepted_relative_increment": strict_metrics[
                "maximum_accepted_relative_increment"
            ],
            "material_families": material["material_families"],
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "claims": {
            "n1_cpu_mathematical_closure": closed,
            "actual_mgt_full_mesh_stateful_material_coupling": False,
            "g1_production_rocm_hip_closure": False,
            "aggregate_generator_committed": generator_committed,
        },
        "blockers_remaining": [
            name for name, passed in evaluations.items() if not passed
        ],
        "non_n1_boundaries": [
            "actual_mgt_full_mesh_stateful_material_coupling",
            "full_corotational_frame_bending_torsion",
            "production_rocm_hip_cross_device_execution",
        ]
        + (
            []
            if generator_committed
            else ["aggregate_generator_commit_and_separate_pr"]
        ),
        "claim_boundary": CLAIM_BOUNDARY
        + (
            " The aggregate generator, schema, and upstream inputs are bound to "
            "an ancestor source commit; the receipt may be committed in a later "
            "evidence-only descendant without creating a cyclic HEAD dependency."
            if generator_committed
            else " The aggregate generator is still a working-tree artifact. Its "
            "mathematical evaluations may be reviewed, but branch promotion requires "
            "a commit-bound source followed by a separate evidence receipt commit."
        ),
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return payload


def validate(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    require_commit_bound: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    schema = _read(root / SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("n1_closure_receipt_hash_mismatch")
    source_commit_sha = payload["aggregate_source"]["source_commit_sha"]
    if not _git_commit_is_ancestor(root, source_commit_sha):
        raise ValueError("n1_closure_source_commit_not_ancestor")
    expected = build(
        root=root,
        generated_at=payload["generated_at"],
        source_commit_sha=source_commit_sha,
    )
    if payload != expected:
        raise ValueError("n1_closure_exact_replay_mismatch")
    if (
        require_commit_bound
        and payload["aggregate_source"]["generator_source_control_state"]
        != "commit_bound"
    ):
        raise ValueError("n1_closure_generator_not_commit_bound")
    return payload


def write(
    *,
    root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    source_commit_sha: str | None = None,
    require_commit_bound: bool = False,
) -> dict[str, Any]:
    payload = build(root=root, source_commit_sha=source_commit_sha)
    target = out if out.is_absolute() else root / out
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate(payload, root=root, require_commit_bound=require_commit_bound)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source-commit")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--require-commit-bound", action="store_true")
    args = parser.parse_args(argv)
    target = args.out if args.out.is_absolute() else ROOT / args.out
    payload = (
        validate(
            _read(target),
            root=ROOT,
            require_commit_bound=args.require_commit_bound,
        )
        if args.check
        else write(
            root=ROOT,
            out=args.out,
            source_commit_sha=args.source_commit,
            require_commit_bound=args.require_commit_bound,
        )
    )
    print(
        f"{payload['status']} | n1_closure="
        f"{payload['claims']['n1_cpu_mathematical_closure']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
