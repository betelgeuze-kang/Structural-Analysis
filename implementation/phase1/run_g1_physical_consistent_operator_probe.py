#!/usr/bin/env python3
"""Opt-in physical-consistent global Newton operator probe (non-promoting).

This probe verifies that the opt-in ``physical_consistent_frame_shell_material_geometric``
operator is a faithful, lambda-free linearization of the physical residual
R(u, lambda) = F_int(u) - lambda * F_ext, and contrasts it with the default
``current_normalized_frame_geometric`` corrector named by the D audit.

Scope (E, first PR): operator construction + JVP parity + non-promoting report.
Real line-search / trust-region residual reduction is deferred to F; the
``line_search_preview`` field is intentionally reported as deferred here.

The original 0.656 continuation checkpoint that the D audit consumed is an
ephemeral artifact no longer on disk, so this probe runs on a deterministic,
reproducible *representative* physical residual (SPD linear stiffness plus a
smooth geometric/material nonlinearity). Provenance is recorded explicitly. This
is sufficient for E's mandatory criteria, which concern operator correctness, not
breaking load_scale 0.656 (that is an F-stage signal).

It does not change the default solver path, does not promote G1, and does not
regenerate tracked evidence (output is an untracked ``*.local.json``).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np

from g1_global_newton_operator import (
    DEFAULT_GLOBAL_NEWTON_OPERATOR,
    GLOBAL_NEWTON_OPERATOR_CURRENT,
    GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    jvp_parity_against_reference,
    jvp_parity_report,
    normalize_global_newton_operator,
    operator_uses_solver_normalization_lambda,
    physical_consistent_jvp,
)


SCHEMA_VERSION = "g1-physical-consistent-operator-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_physical_consistent_operator_probe.local.json"

# Representative-system parameters (deterministic, seeded).
_REP_DOF = 96
_REP_GEOMETRIC_COEFF = 5.0e3
_REP_SEED = 20260628
# The D audit named a service-material reduction and a lambda ~= 515 damping in
# the current normalized corrector; we reuse those to reproduce its mismatch.
_REP_SERVICE_REDUCTION = 0.0953  # observed assembled service_min_tangent_ratio
_REP_NORMALIZATION_LAMBDA = 515.4025311317521


def _representative_physical_system(
    *, dof: int = _REP_DOF, seed: int = _REP_SEED
) -> dict[str, Any]:
    """Build a deterministic SPD + geometric-nonlinear physical residual.

    R(u) = A u + c * u**3 - f , with physical Jacobian J(u) = A + diag(3 c u**2).
    """
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((dof, dof))
    spd = raw @ raw.T / float(dof) + np.eye(dof)  # symmetric positive definite
    f = rng.standard_normal(dof)
    c = float(_REP_GEOMETRIC_COEFF)

    def residual_fn(u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=np.float64)
        return spd @ u + c * (u ** 3) - f

    def physical_jacobian(u: np.ndarray) -> np.ndarray:
        u = np.asarray(u, dtype=np.float64)
        return spd + np.diag(3.0 * c * (u ** 2))

    return {"A": spd, "f": f, "c": c, "residual_fn": residual_fn, "physical_jacobian": physical_jacobian}


def _current_normalized_operator_action(
    system: dict[str, Any], v: np.ndarray
) -> np.ndarray:
    """Reproduce the D-named corrector action: (s*A + lambda*I) . v.

    s is a service-material reduction (< 1) and lambda is the solver-only damping;
    neither belongs to the physical Jacobian, so this action diverges from the
    physical residual derivative.
    """
    a = np.asarray(system["A"], dtype=np.float64)
    reduced = _REP_SERVICE_REDUCTION * (a @ v)
    return reduced + _REP_NORMALIZATION_LAMBDA * v


def run_g1_physical_consistent_operator_probe(
    *,
    global_newton_operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    operator_probe_only: bool = True,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
    seed: int = _REP_SEED,
) -> dict[str, Any]:
    mode = normalize_global_newton_operator(global_newton_operator)
    system = _representative_physical_system(seed=seed)
    residual_fn = system["residual_fn"]
    physical_jacobian = system["physical_jacobian"]

    rng = np.random.default_rng(seed + 1)
    u = 1.0e-3 * rng.standard_normal(_REP_DOF)
    v = rng.standard_normal(_REP_DOF)
    v = v / float(np.linalg.norm(v))

    # JVP parity vs the analytic physical Jacobian action (strong check) ...
    jvp = physical_consistent_jvp(residual_fn, u, v)
    analytic_action = physical_jacobian(u) @ v
    parity_vs_analytic = jvp_parity_against_reference(jvp, analytic_action)
    # ... and vs an independent finite-difference step (self-consistency check).
    parity_vs_fd = jvp_parity_report(residual_fn, u, v)

    # Contrast with the default normalized corrector named by the D audit.
    normalized_action = _current_normalized_operator_action(system, v)
    normalized_vs_physical_abs = float(np.max(np.abs(normalized_action - analytic_action)))
    physical_action_inf = max(float(np.max(np.abs(analytic_action))), 1.0)
    normalized_mismatch_ratio = (
        float(np.max(np.abs(normalized_action))) / physical_action_inf
    )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_probe_only": True,
        "promotes_g1_closure": False,
        "global_newton_operator": mode,
        "baseline_operator": GLOBAL_NEWTON_OPERATOR_CURRENT,
        "default_global_newton_operator": DEFAULT_GLOBAL_NEWTON_OPERATOR,
        "physical_residual_formula": "R(u, lambda)=F_int(u)-lambda*F_ext",
        "uses_solver_normalization_lambda": operator_uses_solver_normalization_lambda(mode),
        "normalization_lambda_excluded": (
            not operator_uses_solver_normalization_lambda(mode)
        ),
        "evidence_provenance": "representative_bounded_physical_system",
        "evidence_provenance_reason": (
            "the 0.656 continuation checkpoint consumed by the D audit is an "
            "ephemeral artifact no longer present on disk; this probe uses a "
            "deterministic seeded representative physical residual instead"
        ),
        "representative_system": {
            "dof": _REP_DOF,
            "seed": seed,
            "form": "R(u)=A u + c u^3 - f, J(u)=A + diag(3 c u^2)",
            "geometric_coeff": system["c"],
        },
        "jvp_parity": {
            "against_analytic_physical_jacobian": parity_vs_analytic,
            "against_independent_finite_difference": parity_vs_fd,
            "pass": bool(parity_vs_analytic["pass"] and parity_vs_fd["pass"]),
        },
        "baseline_operator_contrast": {
            "baseline_uses_solver_normalization_lambda": True,
            "baseline_normalization_lambda": _REP_NORMALIZATION_LAMBDA,
            "baseline_service_material_reduction": _REP_SERVICE_REDUCTION,
            "baseline_action_vs_physical_jacobian_max_absolute_error_n": normalized_vs_physical_abs,
            "baseline_action_over_physical_action_ratio": normalized_mismatch_ratio,
            "note": (
                "the default normalized corrector applies (s*A + lambda*I).v which "
                "is not the physical Jacobian action; this reproduces the D-audit "
                "operator mismatch in a controlled, reproducible setting"
            ),
        },
        "line_search_preview": {
            "status": "deferred_to_F",
            "note": (
                "E (this PR) closes at operator construction + JVP parity. Actual "
                "line-search/trust-region residual reduction on a live continuation "
                "state is F-stage work and is not performed here."
            ),
        },
        "operator_probe_only": bool(operator_probe_only),
        "claim_boundary": "non_promoting_operator_probe_only",
    }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--global-newton-operator",
        choices=list((GLOBAL_NEWTON_OPERATOR_CURRENT, GLOBAL_NEWTON_OPERATOR_PHYSICAL)),
        default=GLOBAL_NEWTON_OPERATOR_PHYSICAL,
        help="operator mode to probe (the solver default remains the current path)",
    )
    parser.add_argument("--operator-probe-only", action="store_true", default=True)
    parser.add_argument(
        "--compare-operator-jvp-to-physical-residual-fd",
        action="store_true",
        default=True,
        help="kept for interface compatibility; JVP/FD parity is always reported",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--seed", type=int, default=_REP_SEED)
    args = parser.parse_args()
    payload = run_g1_physical_consistent_operator_probe(
        global_newton_operator=args.global_newton_operator,
        operator_probe_only=bool(args.operator_probe_only),
        output_json=args.output_json,
        seed=int(args.seed),
    )
    parity = payload["jvp_parity"]
    print(
        "g1-physical-consistent-operator-probe: "
        f"operator={payload['global_newton_operator']} "
        f"lambda_excluded={payload['normalization_lambda_excluded']} "
        f"jvp_parity_pass={parity['pass']} "
        f"jvp_vs_analytic_rel={parity['against_analytic_physical_jacobian']['max_relative_error']:.3e} "
        f"baseline_mismatch_ratio={payload['baseline_operator_contrast']['baseline_action_over_physical_action_ratio']:.3e} "
        f"-> {args.output_json}"
    )
    return 0 if payload["jvp_parity"]["pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
