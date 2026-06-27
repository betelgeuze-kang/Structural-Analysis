#!/usr/bin/env python3
"""Non-promoting physical-residual line-search preview (F1).

Drives the opt-in physical-consistent global Newton operator into a Newton
direction solve + physical-residual backtracking line-search on the deterministic
representative physical system from E, and reports whether it beats the D-audit
tiny-alpha stall.

It does not change the default solver path, does not promote G1, and does not
regenerate tracked evidence (output is an untracked ``*.local.json``). The real
MGT 0.656 continuation application is F2 and is intentionally NOT done here.
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
    jvp_parity_report,
    normalize_global_newton_operator,
    operator_uses_solver_normalization_lambda,
    physical_consistent_jvp,
)
from g1_physical_residual_line_search import (
    D_AUDIT_MAX_PREDICTED_ACTUAL_RATIO,
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
    solve_physical_newton_direction,
)
from run_g1_physical_consistent_operator_probe import (
    _REP_SEED,
    _representative_physical_system,
)


SCHEMA_VERSION = "g1-physical-consistent-line-search-preview.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_physical_consistent_line_search_preview.local.json"


def run_g1_physical_consistent_line_search_preview(
    *,
    global_newton_operator: str = GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    direction_mode: str = "matrix_free_gmres",
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
    seed: int = _REP_SEED,
) -> dict[str, Any]:
    mode = normalize_global_newton_operator(global_newton_operator)
    system = _representative_physical_system(seed=seed)
    residual_fn = system["residual_fn"]
    physical_jacobian = system["physical_jacobian"]

    rng = np.random.default_rng(seed + 2)
    n = int(system["f"].size)
    u = 1.0e-3 * rng.standard_normal(n)

    # JVP parity must still hold before we trust the direction solve.
    v = rng.standard_normal(n)
    v = v / float(np.linalg.norm(v))
    parity = jvp_parity_report(residual_fn, u, v)

    p, solve_meta = solve_physical_newton_direction(residual_fn, u, mode=direction_mode)
    if p is None:
        line_search = {
            "status": "blocked",
            "reason_code": solve_meta.get("reason_code", "direction_solve_failed"),
            "accepted_alpha": None,
            "residual_reduction_ratio": None,
            "alpha_rows": [],
        }
        jvp_action = None
    else:
        jvp_action = physical_consistent_jvp(residual_fn, u, p)
        line_search = physical_residual_backtracking_line_search(
            residual_fn, u, p, jvp_action=jvp_action, alphas=DEFAULT_ALPHAS
        )

    f_ratio = line_search.get("accepted_predicted_over_actual_mismatch_ratio")
    mismatch_improved = bool(
        f_ratio is not None and f_ratio < D_AUDIT_MAX_PREDICTED_ACTUAL_RATIO
    )

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_preview_only": True,
        "promotes_g1_closure": False,
        "global_newton_operator": mode,
        "baseline_operator": GLOBAL_NEWTON_OPERATOR_CURRENT,
        "default_global_newton_operator": DEFAULT_GLOBAL_NEWTON_OPERATOR,
        "physical_residual_formula": "R(u, lambda)=F_int(u)-lambda*F_ext",
        "uses_solver_normalization_lambda": operator_uses_solver_normalization_lambda(mode),
        "normalization_lambda_excluded": not operator_uses_solver_normalization_lambda(mode),
        "evidence_provenance": "representative_bounded_physical_system",
        "evidence_provenance_reason": (
            "F1 preview on the deterministic seeded representative physical residual "
            "from E; the real MGT 0.656 continuation is deferred to F2"
        ),
        "linear_solver": {
            "mode": solve_meta.get("mode", direction_mode),
            "jvp_parity_required": True,
            "jvp_parity_pass": bool(parity["pass"]),
            "jvp_parity_max_relative_error": parity["max_relative_error"],
            "converged": bool(solve_meta.get("converged", False)),
            "reason_code": solve_meta.get("reason_code"),
        },
        "line_search_preview": {
            "status": line_search.get("status"),
            "reason_code": line_search.get("reason_code"),
            "alpha_candidates": list(DEFAULT_ALPHAS),
            "accepted_alpha": line_search.get("accepted_alpha"),
            "residual_before_n": line_search.get("residual_before_n"),
            "residual_after_n": line_search.get("residual_after_n"),
            "residual_reduction_ratio": line_search.get("residual_reduction_ratio"),
            "beats_d_tiny_alpha_threshold": line_search.get("beats_d_tiny_alpha_threshold"),
            "beats_d_residual_reduction_baseline": line_search.get(
                "beats_d_residual_reduction_baseline"
            ),
            "alpha_rows": line_search.get("alpha_rows", []),
        },
        "mismatch_reduction": {
            "d_audit_max_predicted_actual_ratio": D_AUDIT_MAX_PREDICTED_ACTUAL_RATIO,
            "f_preview_predicted_actual_ratio": f_ratio,
            "improved": mismatch_improved,
        },
        "f2_scope_note": (
            "real MGT model / 0.656 continuation checkpoint regeneration and "
            "application is F2; not performed in this preview"
        ),
        "claim_boundary": "non_promoting_line_search_preview_only",
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
        choices=[GLOBAL_NEWTON_OPERATOR_CURRENT, GLOBAL_NEWTON_OPERATOR_PHYSICAL],
        default=GLOBAL_NEWTON_OPERATOR_PHYSICAL,
    )
    parser.add_argument(
        "--direction-mode",
        choices=["matrix_free_gmres", "representative_direct"],
        default="matrix_free_gmres",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--seed", type=int, default=_REP_SEED)
    args = parser.parse_args()
    payload = run_g1_physical_consistent_line_search_preview(
        global_newton_operator=args.global_newton_operator,
        direction_mode=args.direction_mode,
        output_json=args.output_json,
        seed=int(args.seed),
    )
    ls = payload["line_search_preview"]
    mr = payload["mismatch_reduction"]
    print(
        "g1-physical-consistent-line-search-preview: "
        f"status={ls['status']} accepted_alpha={ls['accepted_alpha']} "
        f"reduction={ls['residual_reduction_ratio']} "
        f"beats_d_alpha={ls['beats_d_tiny_alpha_threshold']} "
        f"beats_d_reduction={ls['beats_d_residual_reduction_baseline']} "
        f"f_mismatch_ratio={mr['f_preview_predicted_actual_ratio']} improved={mr['improved']} "
        f"-> {args.output_json}"
    )
    return 0 if ls["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
