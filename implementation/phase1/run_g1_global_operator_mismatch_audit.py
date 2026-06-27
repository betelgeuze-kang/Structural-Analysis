#!/usr/bin/env python3
"""Non-promoting G1 global Newton operator mismatch audit.

This module NAMES the operator that the current G1 direct-residual Newton
corrector actually uses, and contrasts it with the physical residual operator.
It is an *audit*, not a fix and not a closure: it never promotes any G1 gate.

It is intentionally derived from already-emitted, non-promoting local probe and
tangent reports so that it is deterministic and fast (no ~50 min solver re-run):

  - probe report   : run_mgt_direct_residual_newton_probe.py output (``*.local.json``)
  - tangent report : run_mgt_frame_material_nonlinear_tangent.py output (``*.local.json``)

The audit fixes, in a machine-readable form, the four findings required to make
the next implementation step (an opt-in physical-consistent operator) safe:

  1. the solver-only normalization factor (``normalization_lambda``, e.g. ~515)
     used for the linear-correction direction is named explicitly;
  2. the frame / geometric corrector operator uses a different scaling than the
     physical residual operator (service-material reduction + lambda damping);
  3. the shell/surface material tangent is essentially elastic/passive at the
     audited checkpoint and is therefore NOT the driver of the stall;
  4. the alpha scan "only an infinitesimal alpha is a descent direction"
     phenomenon is reproduced from the recorded trust-region candidate rows.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "g1-global-operator-mismatch-audit.local.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_PROBE_JSON = PRODUCTIZATION / "g1_full_load_hip_newton_direct_probe.local.json"
DEFAULT_TANGENT_JSON = PRODUCTIZATION / "mgt_frame_material_nonlinear_tangent.local.json"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_global_operator_mismatch_audit.local.json"

# An accepted step is only a descent step when the resulting residual is below
# the iteration start residual. A healthy consistent-tangent Newton accepts an
# O(1) step (alpha ~ 1.0); we classify the descent window as "tiny" when the
# largest descent alpha is at or below this threshold, i.e. ~1000x below a unit
# step. The recorded probe descent window tops out near 1.25e-4.
TINY_DESCENT_ALPHA_THRESHOLD = 1.0e-3
# Shell material is treated as elastic/passive when essentially no surface row
# is nonlinear and the worst surface tangent ratio is within this band of 1.0.
SHELL_ELASTIC_RATIO_BAND = 5.0e-3


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"required audit input not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"audit input is not a JSON object: {path}")
    return payload


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalization_findings(probe: dict[str, Any]) -> dict[str, Any]:
    base = probe.get("base_direct_residual") or {}
    newton = probe.get("newton_direction") or {}
    rc = probe.get("residual_contract") or {}
    lam = _safe_float(base.get("linear_correction_regularization"))
    lam_newton = _safe_float(newton.get("regularization"))
    return {
        "normalization_lambda": lam,
        "newton_direction_regularization": lam_newton,
        "linearized_tangent_description": newton.get("linearized_tangent"),
        "direct_residual_uses_solver_regularization": bool(
            rc.get("direct_residual_uses_solver_regularization", False)
        ),
        "regularization_used_only_for_linear_correction_direction": bool(
            rc.get("regularization_used_only_for_linear_correction_direction", False)
        ),
        "service_material_tangent_used_for_newton_direction_only": bool(
            rc.get("service_material_tangent_used_for_newton_direction_only", False)
        ),
        "physical_direct_residual_inf_n": _safe_float(base.get("direct_residual_inf_n")),
        "regularized_residual_inf_n": _safe_float(base.get("regularized_residual_inf_n")),
        "quasi_tangent_residual_inf_n": _safe_float(rc.get("quasi_tangent_residual_inf_n")),
        "normalization_lambda_named": lam is not None and lam > 0.0,
    }


def _scaling_findings(probe: dict[str, Any]) -> dict[str, Any]:
    mf = probe.get("mesh_fingerprint") or {}
    frame_mat = mf.get("frame_material_meta") or {}
    service_mat = mf.get("service_material_meta") or {}
    rc = probe.get("residual_contract") or {}
    norm = _normalization_findings(probe)
    frame_min = _safe_float(frame_mat.get("min_solver_tangent_ratio"))
    service_min = _safe_float(service_mat.get("service_min_tangent_ratio"))
    service_mean = _safe_float(service_mat.get("service_mean_tangent_ratio"))
    lam = norm["normalization_lambda"] or 0.0
    # The corrector operator differs from the physical residual operator when the
    # frame service-material tangent is reduced away from elastic AND/OR a global
    # lambda damping is added that is explicitly excluded from the physical residual.
    frame_reduced = frame_min is not None and frame_min < 0.98
    service_reduced = service_min is not None and service_min < 0.98
    lambda_excluded_from_residual = (
        lam > 0.0
        and not norm["direct_residual_uses_solver_regularization"]
        and norm["regularization_used_only_for_linear_correction_direction"]
    )
    return {
        "frame_tangent_ratio_min": frame_min,
        "frame_tangent_ratio_max": 1.0,
        "frame_tangent_reduction_element_count": int(
            frame_mat.get("tangent_reduction_element_count") or 0
        ),
        "service_material_scale_min": service_min,
        "service_material_scale_mean": service_mean,
        "geometric_delta_included": bool(rc.get("frame_geometric_equilibrium_included", False)),
        "geometric_delta_stiffness_nnz": int(mf.get("frame_geometric_delta_stiffness_nnz") or 0),
        "normalization_lambda": lam if lam > 0.0 else None,
        "corrector_operator_scaling_differs_from_physical_residual": bool(
            (frame_reduced or service_reduced) or lambda_excluded_from_residual
        ),
        "corrector_operator_scaling_mismatch_reasons": [
            *(["frame_service_material_tangent_reduced_below_elastic"] if frame_reduced else []),
            *(["assembled_service_material_tangent_reduced_below_elastic"] if service_reduced else []),
            *(["lambda_damping_added_to_corrector_but_excluded_from_physical_residual"]
              if lambda_excluded_from_residual else []),
        ],
    }


def _shell_passive_findings(probe: dict[str, Any]) -> dict[str, Any]:
    mf = probe.get("mesh_fingerprint") or {}
    ssm = mf.get("service_shell_material_meta") or {}
    nonlinear = int(ssm.get("nonlinear_tangent_surface_element_count") or 0)
    min_ratio = _safe_float(ssm.get("min_tangent_ratio"))
    max_abs_strain = _safe_float(ssm.get("max_abs_strain"))
    elastic = bool(
        nonlinear == 0
        and min_ratio is not None
        and (1.0 - min_ratio) <= SHELL_ELASTIC_RATIO_BAND
    )
    return {
        "shell_tangent_ratio_min": min_ratio,
        "shell_tangent_ratio_max": _safe_float(ssm.get("mean_tangent_ratio")),
        "shell_max_abs_strain": max_abs_strain,
        "shell_nonlinear_surface_element_count": nonlinear,
        "shell_state_tag_counts": ssm.get("state_tag_counts") or {},
        "shell_material_tangent_elastic_passive_at_checkpoint": elastic,
        "shell_material_tangent_is_stall_driver": (not elastic),
    }


def _alpha_scan_findings(probe: dict[str, Any]) -> dict[str, Any]:
    tr = probe.get("trust_region_line_search") or {}
    iterations = tr.get("iterations") or []
    rows: list[dict[str, Any]] = []
    any_tiny_descent_only = False
    for it in iterations:
        start = _safe_float(it.get("start_direct_residual_inf_n"))
        dj = it.get("directional_residual_jacobian") or {}
        predicted = _safe_float(dj.get("jacobian_action_inf_n"))
        candidates = it.get("candidate_rows") or []
        descent_alphas: list[float] = []
        increasing_alphas: list[float] = []
        scan: list[dict[str, Any]] = []
        for cr in candidates:
            alpha = _safe_float(cr.get("alpha"))
            resid = _safe_float(cr.get("direct_residual_inf_n"))
            if alpha is None or resid is None or start is None:
                continue
            is_descent = resid < start
            (descent_alphas if is_descent else increasing_alphas).append(alpha)
            scan.append({"alpha": alpha, "direct_residual_inf_n": resid, "is_descent": is_descent})
        largest_descent_alpha = max(descent_alphas) if descent_alphas else None
        smallest_increasing_alpha = min(increasing_alphas) if increasing_alphas else None
        # predicted/actual mismatch: linearized operator predicts a residual action
        # of `predicted` per unit step, while the physical residual scale is `start`.
        mismatch_ratio = (
            predicted / start if (predicted is not None and start not in (None, 0.0)) else None
        )
        tiny_descent_only = bool(
            largest_descent_alpha is not None
            and largest_descent_alpha <= TINY_DESCENT_ALPHA_THRESHOLD
            and smallest_increasing_alpha is not None
        )
        any_tiny_descent_only = any_tiny_descent_only or tiny_descent_only
        rows.append({
            "iteration": it.get("iteration"),
            "start_direct_residual_inf_n": start,
            "directional_jacobian_predicted_residual_change_inf_n": predicted,
            "largest_descent_alpha": largest_descent_alpha,
            "smallest_increasing_alpha": smallest_increasing_alpha,
            "predicted_over_actual_mismatch_ratio": mismatch_ratio,
            "tiny_alpha_descent_only": tiny_descent_only,
            "alpha_scan": scan,
        })
    return {
        "tiny_descent_alpha_threshold": TINY_DESCENT_ALPHA_THRESHOLD,
        "tiny_alpha_descent_only_reproduced": any_tiny_descent_only,
        "max_predicted_over_actual_mismatch_ratio": max(
            (r["predicted_over_actual_mismatch_ratio"] for r in rows
             if r["predicted_over_actual_mismatch_ratio"] is not None),
            default=None,
        ),
        "iterations": rows,
    }


def _tangent_class_findings(tangent: dict[str, Any]) -> dict[str, Any]:
    fd = tangent.get("local_constitutive_tangent_fd_consistency") or {}
    worst = fd.get("sample_worst_rows") or []
    per_class: dict[str, dict[str, Any]] = {}
    for row in worst:
        tag = str(row.get("state_tag") or "")
        cons = _safe_float(row.get("constitutive_tangent_mpa"))
        solver = _safe_float(row.get("solver_tangent_mpa"))
        ratio = (solver / cons) if (cons not in (None, 0.0) and solver is not None) else None
        bucket = per_class.setdefault(tag, {"sample_count": 0, "solver_over_consistent_ratios": []})
        bucket["sample_count"] += 1
        if ratio is not None:
            bucket["solver_over_consistent_ratios"].append(ratio)
    return {
        "physical_material_tangent_is_fd_consistent": bool(
            fd.get("constitutive_tangent_fd_consistency_pass", False)
        ),
        "physical_material_tangent_max_relative_error": _safe_float(fd.get("max_relative_error")),
        "physical_material_tangent_relative_error_tolerance": _safe_float(
            fd.get("relative_error_tolerance")
        ),
        "bounded_solver_tangent_row_count": int(fd.get("bounded_solver_tangent_row_count") or 0),
        "bounded_solver_state_tag_counts": fd.get("bounded_solver_state_tag_counts") or {},
        "per_state_class_solver_over_consistent_tangent_ratio_samples": per_class,
        "note": (
            "physical_material_tangent_mpa is the FD-consistent constitutive tangent; "
            "solver_tangent_mpa is the bounded/regularized tangent injected into the "
            "Newton direction. bounded_solver_state_tag_counts names which state classes "
            "have solver tangent diverging from the physical constitutive tangent."
        ),
    }


def run_g1_global_operator_mismatch_audit(
    *,
    probe_json: Path = DEFAULT_PROBE_JSON,
    tangent_json: Path = DEFAULT_TANGENT_JSON,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    probe = _load_json(probe_json)
    tangent = _load_json(tangent_json)

    normalization = _normalization_findings(probe)
    scaling = _scaling_findings(probe)
    shell = _shell_passive_findings(probe)
    alpha = _alpha_scan_findings(probe)
    tangent_classes = _tangent_class_findings(tangent)

    termination = {
        "normalization_factor_named": bool(normalization["normalization_lambda_named"]),
        "frame_geometric_scaling_differs_from_physical_residual_named": bool(
            scaling["corrector_operator_scaling_differs_from_physical_residual"]
        ),
        "shell_material_tangent_elastic_passive_evidence_present": bool(
            shell["shell_material_tangent_elastic_passive_at_checkpoint"]
        ),
        "tiny_alpha_descent_only_reproduced": bool(
            alpha["tiny_alpha_descent_only_reproduced"]
        ),
    }
    audit_complete = all(termination.values())

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_audit_only": True,
        "promotes_g1_closure": False,
        "claim_boundary": (
            "This is a non-promoting operator-naming audit. It does NOT prove or "
            "promote G1 closure, does not change the solver, and preserves all "
            "partial/proxy/external-blocked evidence boundaries."
        ),
        "inputs": {
            "probe_json": str(probe_json),
            "probe_source_commit_sha": probe.get("source_commit_sha"),
            "probe_status": probe.get("status"),
            "probe_checkpoint_load_scale": _safe_float((probe.get("checkpoint") or {}).get("load_scale")),
            "tangent_json": str(tangent_json),
            "tangent_status": tangent.get("status"),
        },
        "current_corrector_operator": {
            "description": normalization["linearized_tangent_description"],
            **normalization,
            **scaling,
        },
        "physical_residual_operator": {
            "definition": (probe.get("residual_contract") or {}).get("definition"),
            "physical_internal_force_model": (
                (probe.get("residual_contract") or {}).get("physical_internal_force_model")
            ),
            **tangent_classes,
        },
        "shell_material_state": shell,
        "alpha_scan_descent_audit": alpha,
        "operator_mismatch_summary": {
            "named_wrong_operator": (
                "current_normalized_frame_geometric (service-material reduced frame "
                "tangent + geometric delta + lambda damping) used for the Newton "
                "direction, which is NOT the Jacobian of the physical residual "
                "R(u, lambda) = F_int(u) - lambda * F_ext."
            ),
            "max_predicted_over_actual_mismatch_ratio": alpha["max_predicted_over_actual_mismatch_ratio"],
            "stall_driver": "regularized_reduced_frame_geometric_operator_not_shell_material",
        },
        "termination_criteria": termination,
        "audit_complete": audit_complete,
    }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-json", type=Path, default=DEFAULT_PROBE_JSON)
    parser.add_argument("--tangent-json", type=Path, default=DEFAULT_TANGENT_JSON)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_global_operator_mismatch_audit(
        probe_json=args.probe_json,
        tangent_json=args.tangent_json,
        output_json=args.output_json,
    )
    tc = payload["termination_criteria"]
    print(
        "g1-global-operator-mismatch-audit: "
        f"complete={payload['audit_complete']} "
        f"lambda={payload['current_corrector_operator']['normalization_lambda']} "
        f"scaling_differs={tc['frame_geometric_scaling_differs_from_physical_residual_named']} "
        f"shell_passive={tc['shell_material_tangent_elastic_passive_evidence_present']} "
        f"tiny_alpha_only={tc['tiny_alpha_descent_only_reproduced']} "
        f"max_mismatch_ratio={payload['operator_mismatch_summary']['max_predicted_over_actual_mismatch_ratio']} "
        f"-> {args.output_json}"
    )
    return 0 if payload["audit_complete"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
