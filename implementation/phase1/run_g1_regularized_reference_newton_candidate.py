#!/usr/bin/env python3
"""Non-promoting regularized reference Newton candidate (F2g).

F2f showed that, at the real MGT reference state (load_scale=0.1, real per-element
service tangent), a moderate relative-diagonal regularization (mu=0.1) makes the
consistent assembled tangent factorable and yields a full-step (alpha=1.0), ~87%
residual-reduction physical-residual descent direction.

F2g asks the next question: does a regularized physical-consistent Newton iterate
reduce the physical residual *over multiple steps* (convergence), not just once?

This is a candidate runner, not a fix and not a closure: no production solver path
change, no 0.656 continuation regeneration, no G1 promotion. Output is an untracked
``*.local.json``. It uses a modified-Newton scheme (the regularized reference
tangent is factorized once and reused; the physical residual is re-evaluated each
step), which directly probes whether the reference operator drives convergence.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from g1_global_newton_operator import DEFAULT_JVP_EPS, physical_consistent_jvp
from g1_physical_residual_line_search import (
    DEFAULT_ALPHAS,
    physical_residual_backtracking_line_search,
)
from g1_regularized_direction import PRODUCTION_LAMBDA, regularize_matrix
from run_g1_mgt_physical_line_search_smoke import (
    ERR_MGT_INPUT_MISSING,
    ERR_MGT_STATE_BUILD_FAILED,
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)


SCHEMA_VERSION = "g1-regularized-reference-newton-candidate.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_OUTPUT_JSON = PRODUCTIZATION / "g1_regularized_reference_newton_candidate.local.json"
DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")

DirectionFn = Callable[[np.ndarray, np.ndarray], "tuple[np.ndarray | None, dict[str, Any]]"]
ResidualFn = Callable[[np.ndarray], np.ndarray]

STOP_MAX_STEPS = "max_steps"
STOP_GATE = "residual_gate_passed"
STOP_NO_DESCENT = "line_search_no_descent"
STOP_SOLVE_FAILED = "solve_failed"
STOP_NAN = "fail_closed_nan"
STOP_STALLED = "stalled_min_reduction"
STOP_PARITY_FAILED = "parity_failed"


def _inf_norm(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    return float(np.max(np.abs(x))) if x.size else 0.0


def _finite(x: np.ndarray) -> bool:
    return bool(np.all(np.isfinite(np.asarray(x, dtype=np.float64))))


def _line_search_trial_summary(ls: dict[str, Any]) -> dict[str, Any]:
    alpha_rows = [
        row for row in ls.get("alpha_rows", []) if isinstance(row, dict)
    ]
    finite_rows = [row for row in alpha_rows if row.get("finite") is True]
    best_trial = (
        min(
            finite_rows,
            key=lambda row: float(row.get("residual_inf_n", float("inf"))),
        )
        if finite_rows
        else None
    )
    return {
        "status": ls.get("status"),
        "reason_code": ls.get("reason_code"),
        "accepted_alpha": ls.get("accepted_alpha"),
        "residual_before_n": ls.get("residual_before_n"),
        "residual_after_n": ls.get("residual_after_n"),
        "residual_reduction_ratio": ls.get("residual_reduction_ratio"),
        "alpha_row_count": len(alpha_rows),
        "all_trials_finite": (
            len(alpha_rows) > 0 and len(alpha_rows) == len(finite_rows)
        ),
        "best_trial": best_trial,
        "alpha_rows": alpha_rows,
    }


def _residual_jvp_contract(r: np.ndarray, jvp_action: np.ndarray) -> dict[str, Any]:
    r = np.asarray(r, dtype=np.float64)
    jvp_action = np.asarray(jvp_action, dtype=np.float64)
    if not _finite(r) or not _finite(jvp_action):
        return {
            "finite": False,
            "reason_code": "nonfinite_residual_or_jvp",
        }
    residual_inf = _inf_norm(r)
    jvp_inf = _inf_norm(jvp_action)
    linearized = r + jvp_action
    linearized_inf = _inf_norm(linearized)
    residual_l2 = float(np.linalg.norm(r))
    jvp_l2 = float(np.linalg.norm(jvp_action))
    linearized_l2 = float(np.linalg.norm(linearized))
    dot = float(np.dot(r, jvp_action))
    cosine = (
        float(-dot / max(residual_l2 * jvp_l2, 1.0e-30))
        if residual_l2 > 0.0 and jvp_l2 > 0.0
        else None
    )
    return {
        "finite": True,
        "residual_inf_n": residual_inf,
        "jvp_action_inf_n": jvp_inf,
        "jvp_plus_residual_inf_n": linearized_inf,
        "jvp_plus_residual_relative_inf": linearized_inf / max(residual_inf, 1.0),
        "jvp_plus_residual_l2_ratio": linearized_l2 / max(residual_l2, 1.0e-30),
        "residual_dot_jvp": dot,
        "local_l2_residual_descent": bool(dot < 0.0),
        "negative_residual_alignment_cosine": cosine,
    }


def regularized_direction_solve_contract(
    k_unregularized: Any,
    k_regularized: Any,
    p: np.ndarray,
    r: np.ndarray,
    *,
    regularization_mode: str,
    regularization_mu: float,
    effective_shift: float,
    scale_source: str,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    p = np.asarray(p, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    if not _finite(p) or not _finite(r):
        return (
            {
                "finite": False,
                "reason_code": "nonfinite_residual_or_direction",
            },
            {},
        )
    k_action = np.asarray(k_unregularized @ p, dtype=np.float64)
    kreg_action = np.asarray(k_regularized @ p, dtype=np.float64)
    if not _finite(k_action) or not _finite(kreg_action):
        return (
            {
                "finite": False,
                "reason_code": "nonfinite_tangent_action",
            },
            {},
        )
    residual_inf = _inf_norm(r)
    regularized_solve_residual = kreg_action + r
    unregularized_linearized_residual = k_action + r
    regularization_action = kreg_action - k_action
    return (
        {
            "finite": True,
            "regularization_mode": str(regularization_mode),
            "regularization_mu": float(regularization_mu),
            "effective_shift": float(effective_shift),
            "scale_source": str(scale_source),
            "regularized_linear_solve_residual_inf_n": _inf_norm(
                regularized_solve_residual
            ),
            "regularized_linear_solve_relative_inf": _inf_norm(
                regularized_solve_residual
            )
            / max(residual_inf, 1.0),
            "unregularized_tangent_plus_residual_inf_n": _inf_norm(
                unregularized_linearized_residual
            ),
            "unregularized_tangent_plus_residual_relative_inf": _inf_norm(
                unregularized_linearized_residual
            )
            / max(residual_inf, 1.0),
            "regularization_action_inf_n": _inf_norm(regularization_action),
            "regularization_action_vs_residual_inf": _inf_norm(
                regularization_action
            )
            / max(residual_inf, 1.0),
        },
        {
            "_unregularized_tangent_action": k_action,
            "_regularized_tangent_action": kreg_action,
        },
    )


def _direction_row_metadata(meta: dict[str, Any] | None) -> dict[str, Any] | None:
    if not meta:
        return None
    free = meta.get("free")
    node_id = meta.get("node_id")
    dof_per_node = int(meta.get("dof_per_node") or len(DOF_LABELS))
    if free is None or node_id is None or dof_per_node <= 0:
        return None
    return {
        "free": np.asarray(free, dtype=np.int64),
        "node_id": np.asarray(node_id, dtype=np.int64),
        "dof_per_node": int(dof_per_node),
    }


def tangent_component_actions(
    component_stiffness_free: dict[str, Any] | None,
    p: np.ndarray,
) -> dict[str, np.ndarray]:
    if not component_stiffness_free:
        return {}
    direction = np.asarray(p, dtype=np.float64)
    return {
        name: np.asarray(stiffness @ direction, dtype=np.float64)
        for name, stiffness in component_stiffness_free.items()
    }


def _annotate_reduced_row(
    entry: dict[str, Any],
    row_metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    if not row_metadata:
        return entry
    free = row_metadata.get("free")
    node_id = row_metadata.get("node_id")
    dof_per_node = int(row_metadata.get("dof_per_node") or len(DOF_LABELS))
    reduced_index = int(entry["reduced_index"])
    if free is None or reduced_index < 0 or reduced_index >= len(free):
        return entry
    global_dof = int(np.asarray(free, dtype=np.int64)[reduced_index])
    node_index = global_dof // dof_per_node
    local_dof_index = global_dof % dof_per_node
    annotated = {
        **entry,
        "global_dof": global_dof,
        "node_index": int(node_index),
        "local_dof_index": int(local_dof_index),
        "dof_label": (
            DOF_LABELS[local_dof_index]
            if 0 <= local_dof_index < len(DOF_LABELS)
            else f"DOF{local_dof_index}"
        ),
    }
    node_ids = np.asarray(node_id, dtype=np.int64) if node_id is not None else None
    if node_ids is not None and 0 <= node_index < int(node_ids.size):
        annotated["node_id"] = int(node_ids[node_index])
    return annotated


def _top_abs_entries(
    values: np.ndarray,
    *,
    limit: int = 5,
    row_metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0 or not _finite(arr):
        return []
    order = np.argsort(-np.abs(arr))[: max(int(limit), 0)]
    return [
        _annotate_reduced_row(
            {
                "reduced_index": int(index),
                "value": float(arr[index]),
                "abs": float(abs(arr[index])),
            },
            row_metadata,
        )
        for index in order
    ]


def _component_directional_jvp_rows(
    component_residual_fn: Callable[[np.ndarray], dict[str, np.ndarray]] | None,
    x: np.ndarray,
    p: np.ndarray,
    row_entries: list[dict[str, Any]],
    total_jvp_action: np.ndarray,
    *,
    tangent_component_actions: dict[str, np.ndarray] | None = None,
    eps: float = DEFAULT_JVP_EPS,
) -> dict[str, Any] | None:
    if component_residual_fn is None or not row_entries:
        return None
    x = np.asarray(x, dtype=np.float64)
    p = np.asarray(p, dtype=np.float64)
    try:
        plus = component_residual_fn(x + float(eps) * p)
        minus = component_residual_fn(x - float(eps) * p)
    except Exception as exc:  # noqa: BLE001
        return {
            "attempted": True,
            "status": "blocked",
            "reason_code": f"component_jvp_failed:{type(exc).__name__}",
        }
    names = sorted(set(plus) | set(minus))
    component_jvps: dict[str, np.ndarray] = {}
    shape = np.asarray(total_jvp_action, dtype=np.float64).shape
    for name in names:
        pvals = np.asarray(plus.get(name, np.zeros(shape)), dtype=np.float64)
        mvals = np.asarray(minus.get(name, np.zeros(shape)), dtype=np.float64)
        if pvals.shape != shape or mvals.shape != shape:
            return {
                "attempted": True,
                "status": "blocked",
                "reason_code": "component_jvp_shape_mismatch",
                "component": name,
                "expected_shape": list(shape),
                "plus_shape": list(pvals.shape),
                "minus_shape": list(mvals.shape),
            }
        component_jvps[name] = (pvals - mvals) / (2.0 * float(eps))
    if not component_jvps:
        return {
            "attempted": True,
            "status": "blocked",
            "reason_code": "no_component_jvps",
        }
    component_sum = np.sum(list(component_jvps.values()), axis=0)
    total_jvp = np.asarray(total_jvp_action, dtype=np.float64)
    rows: list[dict[str, Any]] = []
    for entry in row_entries:
        reduced_index = int(entry.get("reduced_index", -1))
        if reduced_index < 0 or reduced_index >= total_jvp.size:
            continue
        values = {
            name: float(jvp[reduced_index])
            for name, jvp in component_jvps.items()
        }
        tangent_values = {
            name: float(np.asarray(action, dtype=np.float64)[reduced_index])
            for name, action in (tangent_component_actions or {}).items()
            if np.asarray(action, dtype=np.float64).shape == total_jvp.shape
        }
        tangent_gap_values = {
            name: values.get(name, 0.0) - tangent_values.get(name, 0.0)
            for name in sorted(set(values) | set(tangent_values))
        }
        dominant_name = max(values, key=lambda key: abs(values[key]))
        dominant_tangent_gap_name = (
            max(tangent_gap_values, key=lambda key: abs(tangent_gap_values[key]))
            if tangent_gap_values
            else None
        )
        top_values = sorted(
            (
                {"component": name, "value": value, "abs": abs(value)}
                for name, value in values.items()
            ),
            key=lambda row: -float(row["abs"]),
        )[:5]
        top_tangent_gap_values = sorted(
            (
                {"component": name, "value": value, "abs": abs(value)}
                for name, value in tangent_gap_values.items()
            ),
            key=lambda row: -float(row["abs"]),
        )[:5]
        rows.append(
            {
                **entry,
                "dominant_component": dominant_name,
                "dominant_component_value": values[dominant_name],
                "component_values": values,
                "top_component_values": top_values,
                "tangent_component_action_values": tangent_values,
                "component_jvp_minus_tangent_action_values": tangent_gap_values,
                "dominant_component_tangent_gap": dominant_tangent_gap_name,
                "dominant_component_tangent_gap_value": (
                    tangent_gap_values[dominant_tangent_gap_name]
                    if dominant_tangent_gap_name is not None
                    else None
                ),
                "top_component_tangent_gap_values": top_tangent_gap_values,
                "component_sum_jvp": float(component_sum[reduced_index]),
                "total_jvp_action": float(total_jvp[reduced_index]),
                "component_sum_minus_total_jvp": float(
                    component_sum[reduced_index] - total_jvp[reduced_index]
                ),
            }
        )
    return {
        "attempted": True,
        "status": "ready",
        "eps": float(eps),
        "component_names": names,
        "component_count": len(names),
        "component_sum_minus_total_jvp_inf_n": _inf_norm(component_sum - total_jvp),
        "rows": rows,
    }


def _augment_direction_solve_contract(
    meta: dict[str, Any] | None,
    r: np.ndarray,
    jvp_action: np.ndarray,
    *,
    x: np.ndarray,
    p: np.ndarray,
) -> dict[str, Any] | None:
    if not meta or not isinstance(meta.get("direction_solve_contract"), dict):
        return None
    contract = dict(meta["direction_solve_contract"])
    row_metadata = meta.get("_row_metadata")
    tangent_component_actions = meta.get("_tangent_component_actions")
    unregularized_action = meta.get("_unregularized_tangent_action")
    if unregularized_action is not None and _finite(unregularized_action):
        unregularized_action = np.asarray(unregularized_action, dtype=np.float64)
        tangent_gap = np.asarray(jvp_action, dtype=np.float64) - np.asarray(
            unregularized_action, dtype=np.float64
        )
        unregularized_linearized_residual = unregularized_action + np.asarray(
            r, dtype=np.float64
        )
        residual_inf = _inf_norm(r)
        contract["jvp_minus_unregularized_tangent_action_inf_n"] = _inf_norm(
            tangent_gap
        )
        contract["jvp_minus_unregularized_tangent_action_relative_inf"] = (
            _inf_norm(tangent_gap) / max(residual_inf, 1.0)
        )
        contract["dominant_jvp_minus_unregularized_tangent_action_rows"] = (
            _top_abs_entries(tangent_gap, row_metadata=row_metadata)
        )
        component_jvp = _component_directional_jvp_rows(
            meta.get("_component_residual_fn"),
            x,
            p,
            contract["dominant_jvp_minus_unregularized_tangent_action_rows"],
            jvp_action,
            tangent_component_actions=tangent_component_actions,
        )
        if component_jvp is not None:
            contract["dominant_jvp_gap_component_breakdown"] = component_jvp
        contract["dominant_unregularized_tangent_plus_residual_rows"] = (
            _top_abs_entries(
                unregularized_linearized_residual,
                row_metadata=row_metadata,
            )
        )
    regularized_action = meta.get("_regularized_tangent_action")
    if (
        unregularized_action is not None
        and regularized_action is not None
        and _finite(unregularized_action)
        and _finite(regularized_action)
    ):
        regularization_action = np.asarray(
            regularized_action, dtype=np.float64
        ) - np.asarray(unregularized_action, dtype=np.float64)
        contract["dominant_regularization_action_rows"] = _top_abs_entries(
            regularization_action,
            row_metadata=row_metadata,
        )
        contract["diagnostic_row_space"] = (
            "free_reduced_dof_index_with_global_dof_mapping"
            if row_metadata
            else "free_reduced_dof_index"
        )
    return contract


def _contract_summary(history: list[dict[str, Any]]) -> dict[str, Any]:
    def _collect(key: str) -> list[dict[str, Any]]:
        return [
            row[key]
            for row in history
            if isinstance(row.get(key), dict) and row[key].get("finite") is True
        ]

    def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "count": 0,
                "max_jvp_plus_residual_relative_inf": None,
                "all_local_l2_residual_descent": None,
            }
        return {
            "count": len(rows),
            "max_jvp_plus_residual_relative_inf": max(
                float(row["jvp_plus_residual_relative_inf"]) for row in rows
            ),
            "all_local_l2_residual_descent": all(
                row.get("local_l2_residual_descent") is True for row in rows
            ),
        }

    direction_solve_rows = _collect("direction_solve_contract")

    def _max_or_none(rows: list[dict[str, Any]], key: str) -> float | None:
        values = [row.get(key) for row in rows if row.get(key) is not None]
        if not values:
            return None
        return max(float(value) for value in values)

    def _dominant_direction_solve_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates = [
            row
            for row in rows
            if row.get("jvp_minus_unregularized_tangent_action_relative_inf")
            is not None
        ]
        if not candidates:
            return None
        row = max(
            candidates,
            key=lambda item: float(
                item["jvp_minus_unregularized_tangent_action_relative_inf"]
            ),
        )
        return {
            "jvp_minus_unregularized_tangent_action_relative_inf": float(
                row["jvp_minus_unregularized_tangent_action_relative_inf"]
            ),
            "jvp_minus_unregularized_tangent_action_inf_n": row.get(
                "jvp_minus_unregularized_tangent_action_inf_n"
            ),
            "diagnostic_row_space": row.get("diagnostic_row_space"),
            "dominant_jvp_minus_unregularized_tangent_action_rows": row.get(
                "dominant_jvp_minus_unregularized_tangent_action_rows"
            ),
            "dominant_unregularized_tangent_plus_residual_rows": row.get(
                "dominant_unregularized_tangent_plus_residual_rows"
            ),
            "dominant_regularization_action_rows": row.get(
                "dominant_regularization_action_rows"
            ),
            "dominant_jvp_gap_component_breakdown": row.get(
                "dominant_jvp_gap_component_breakdown"
            ),
        }

    return {
        "forward_directions": _summarize(_collect("forward_residual_jvp_contract")),
        "accepted_directions": _summarize(_collect("accepted_residual_jvp_contract")),
        "reverse_direction_previews": _summarize(
            _collect("reverse_residual_jvp_contract")
        ),
        "direction_solve_contracts": {
            "count": len(direction_solve_rows),
            "max_regularized_linear_solve_relative_inf": _max_or_none(
                direction_solve_rows,
                "regularized_linear_solve_relative_inf",
            ),
            "max_unregularized_tangent_plus_residual_relative_inf": _max_or_none(
                direction_solve_rows,
                "unregularized_tangent_plus_residual_relative_inf",
            ),
            "max_regularization_action_vs_residual_inf": _max_or_none(
                direction_solve_rows,
                "regularization_action_vs_residual_inf",
            ),
            "max_jvp_minus_unregularized_tangent_action_relative_inf": _max_or_none(
                direction_solve_rows,
                "jvp_minus_unregularized_tangent_action_relative_inf",
            ),
            "dominant_jvp_gap_row_set": _dominant_direction_solve_row(
                direction_solve_rows
            ),
        },
    }


def run_multistep_newton(
    residual_fn: ResidualFn,
    x0: np.ndarray,
    direction_fn: DirectionFn,
    *,
    max_newton_steps: int = 8,
    residual_gate_n: float = 5.0e-4,
    min_reduction_per_step: float = 1.0e-6,
    alphas: tuple[float, ...] = DEFAULT_ALPHAS,
    return_final_state: bool = False,
    allow_signed_direction_globalization: bool = False,
) -> dict[str, Any]:
    """Testable multi-step Newton loop on a physical residual with line-search.

    ``direction_fn(x, r)`` returns ``(p, meta)`` (p=None on solve failure).
    """
    x = np.asarray(x0, dtype=np.float64).copy()
    r = np.asarray(residual_fn(x), dtype=np.float64)
    if not _finite(r):
        result = {"newton_history": [],
                  "summary": {"initial_residual_n": None, "final_residual_n": None,
                              "total_reduction_ratio": None, "monotonic_residual_decrease": False,
                              "residual_gate_passed": False, "stop_reason": STOP_NAN}}
        if return_final_state:
            result["final_state"] = x.copy()
        return result
    initial = _inf_norm(r)
    history: list[dict[str, Any]] = []
    monotonic = True
    stop_reason = STOP_MAX_STEPS
    for it in range(int(max_newton_steps)):
        r = np.asarray(residual_fn(x), dtype=np.float64)
        if not _finite(r):
            stop_reason = STOP_NAN
            break
        rb = _inf_norm(r)
        if rb <= residual_gate_n:
            stop_reason = STOP_GATE
            break
        p, meta = direction_fn(x, r)
        if p is None or not _finite(p):
            history.append({"iteration": it, "residual_before_n": rb,
                            "direction_solve_status": "blocked",
                            "reason_code": (meta or {}).get("reason_code", "solve_failed"),
                            "accepted_alpha": None})
            stop_reason = (meta or {}).get("solve_stop_reason", STOP_SOLVE_FAILED)
            break
        direction_inf = _inf_norm(p)
        jvp_action = physical_consistent_jvp(residual_fn, x, p)
        jvp_action_inf = _inf_norm(jvp_action)
        forward_contract = _residual_jvp_contract(r, jvp_action)
        reverse_contract = _residual_jvp_contract(r, -jvp_action)
        direction_solve_contract = _augment_direction_solve_contract(
            meta, r, jvp_action, x=x, p=p
        )
        ls = physical_residual_backtracking_line_search(
            residual_fn, x, p, jvp_action=jvp_action, alphas=alphas,
        )
        if ls.get("status") != "ready":
            ls_summary = _line_search_trial_summary(ls)
            reverse_ls = physical_residual_backtracking_line_search(
                residual_fn,
                x,
                -p,
                jvp_action=-jvp_action,
                alphas=alphas,
            )
            reverse_summary = _line_search_trial_summary(reverse_ls)
            if (
                allow_signed_direction_globalization
                and reverse_summary["status"] == "ready"
            ):
                alpha = float(reverse_summary["accepted_alpha"])
                ra = float(reverse_summary["residual_after_n"])
                reduction = (rb - ra) / max(rb, 1.0e-30)
                row = {
                    "iteration": it,
                    "residual_before_n": rb,
                    "direction_solve_status": "ready",
                    "accepted_alpha": alpha,
                    "accepted_direction_sign": -1,
                    "residual_after_n": ra,
                    "residual_reduction_ratio": reduction,
                    "line_search_status": "ready_reverse_direction",
                    "forward_line_search_status": ls_summary["status"],
                    "forward_line_search_reason_code": ls_summary["reason_code"],
                    "direction_inf_norm": direction_inf,
                    "jvp_action_inf_n": jvp_action_inf,
                    "forward_residual_jvp_contract": forward_contract,
                    "reverse_residual_jvp_contract": reverse_contract,
                    "accepted_residual_jvp_contract": reverse_contract,
                    "line_search_best_trial": ls_summary["best_trial"],
                    "reverse_direction_line_search_preview": reverse_summary,
                    "signed_direction_globalization_used": True,
                }
                for key in ("tangent_rebuilt", "assembled_tangent_parity_pass"):
                    if meta and key in meta:
                        row[key] = meta[key]
                if direction_solve_contract is not None:
                    row["direction_solve_contract"] = direction_solve_contract
                history.append(row)
                if ra > rb:
                    monotonic = False
                x = x - alpha * p
                if reduction < min_reduction_per_step:
                    stop_reason = STOP_STALLED
                    break
                continue
            history.append({"iteration": it, "residual_before_n": rb,
                            "direction_solve_status": "ready",
                            "line_search_status": ls_summary["status"],
                            "line_search_reason_code": ls_summary["reason_code"],
                            "accepted_alpha": None,
                            "direction_inf_norm": direction_inf,
                            "jvp_action_inf_n": jvp_action_inf,
                            "forward_residual_jvp_contract": forward_contract,
                            "reverse_residual_jvp_contract": reverse_contract,
                            "line_search_alpha_row_count": ls_summary["alpha_row_count"],
                            "line_search_all_trials_finite": ls_summary[
                                "all_trials_finite"
                            ],
                            "line_search_best_trial": ls_summary["best_trial"],
                            "line_search_alpha_rows": ls_summary["alpha_rows"],
                            "reverse_direction_line_search_preview": reverse_summary,
                            **(
                                {"direction_solve_contract": direction_solve_contract}
                                if direction_solve_contract is not None
                                else {}
                            )})
            stop_reason = STOP_NO_DESCENT
            break
        alpha = float(ls["accepted_alpha"])
        ra = float(ls["residual_after_n"])
        reduction = (rb - ra) / max(rb, 1.0e-30)
        row = {"iteration": it, "residual_before_n": rb,
               "direction_solve_status": "ready", "accepted_alpha": alpha,
               "accepted_direction_sign": 1,
               "residual_after_n": ra, "residual_reduction_ratio": reduction,
               "line_search_status": "ready",
               "direction_inf_norm": direction_inf,
               "jvp_action_inf_n": jvp_action_inf,
               "forward_residual_jvp_contract": forward_contract,
               "accepted_residual_jvp_contract": forward_contract}
        for key in ("tangent_rebuilt", "assembled_tangent_parity_pass"):
            if meta and key in meta:
                row[key] = meta[key]
        if direction_solve_contract is not None:
            row["direction_solve_contract"] = direction_solve_contract
        history.append(row)
        if ra > rb:
            monotonic = False
        x = x + alpha * p
        if reduction < min_reduction_per_step:
            stop_reason = STOP_STALLED
            break
    final_r = np.asarray(residual_fn(x), dtype=np.float64)
    final = _inf_norm(final_r) if _finite(final_r) else None
    summary = {
        "initial_residual_n": initial,
        "final_residual_n": final,
        "total_reduction_ratio": ((initial - final) / max(initial, 1.0e-30)) if final is not None else None,
        "monotonic_residual_decrease": bool(monotonic),
        "residual_gate_passed": bool(final is not None and final <= residual_gate_n),
        "stop_reason": stop_reason,
        "steps_taken": len(history),
        "signed_direction_globalization_used": any(
            row.get("signed_direction_globalization_used") is True for row in history
        ),
        "signed_direction_step_count": sum(
            1 for row in history if row.get("accepted_direction_sign") == -1
        ),
        "directional_residual_jvp_contract": _contract_summary(history),
    }
    result = {"newton_history": history, "summary": summary}
    if return_final_state:
        result["final_state"] = x.copy()
    return result


def run_g1_regularized_reference_newton_candidate(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    roundtrip_npz: Path | None = None,
    load_scale: float = 0.1,
    frame_service_tangent_source: str = "real_per_element",
    frame_tangent_source: str = "service_material_plus_geometric_delta",
    regularization_mode: str = "relative_diagonal_shift",
    regularization_mu: float = 0.1,
    max_newton_steps: int = 8,
    residual_gate_n: float = 5.0e-4,
    allow_signed_direction_globalization: bool = False,
    output_json: Path | None = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    mgt_model = Path(mgt_model)

    def _base() -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_candidate_only": True,
            "promotes_g1_closure": False,
            "load_scale": load_scale,
            "frame_service_tangent_source": frame_service_tangent_source,
            "frame_tangent_source": frame_tangent_source,
            "regularization": {
                "mode": regularization_mode, "mu": regularization_mu, "selected_from_f2f": True,
            },
            "signed_direction_globalization": {
                "enabled": bool(allow_signed_direction_globalization),
                "claim_boundary": "non_promoting_diagnostic_globalization_only",
            },
            "production_lambda": PRODUCTION_LAMBDA,
            "claim_boundary": "non_promoting_regularized_reference_newton_candidate_only",
        }

    if not mgt_model.is_file():
        payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_INPUT_MISSING,
                   "uses_real_mgt_model": False, "mgt_source": str(mgt_model),
                   "newton_history": [], "summary": {"stop_reason": "mgt_input_missing"}}
    else:
        try:
            residual_fn, x0, meta = build_mgt_physical_residual_closure(
                mgt_path=mgt_model, roundtrip_npz=roundtrip_npz, load_scale=load_scale,
                frame_service_tangent_source=frame_service_tangent_source,
                frame_tangent_source=frame_tangent_source,
            )
        except Exception as exc:  # noqa: BLE001
            payload = {**_base(), "status": "blocked", "reason_code": ERR_MGT_STATE_BUILD_FAILED,
                       "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                       "detail": f"{type(exc).__name__}:{exc}",
                       "newton_history": [], "summary": {"stop_reason": "state_build_failed"}}
        else:
            k_free = meta["tangent_free_csr"]
            k_reg, eff_shift, scale_source = regularize_matrix(k_free, regularization_mode, regularization_mu)
            try:
                factor = splu(csc_matrix(k_reg))
            except Exception as exc:  # noqa: BLE001
                payload = {**_base(), "status": "blocked", "reason_code": "ERR_REGULARIZED_FACTOR_FAILED",
                           "uses_real_mgt_model": True, "mgt_source": str(mgt_model),
                           "detail": str(exc)[:160], "newton_history": [],
                           "summary": {"stop_reason": "solve_failed"}}
            else:
                row_metadata = _direction_row_metadata(meta)

                def direction_fn(x: np.ndarray, r: np.ndarray):
                    try:
                        p = np.asarray(factor.solve(-np.asarray(r, dtype=np.float64)), dtype=np.float64)
                    except Exception as exc:  # noqa: BLE001
                        return None, {"reason_code": f"solve_error:{type(exc).__name__}"}
                    contract, action_meta = regularized_direction_solve_contract(
                        k_free,
                        k_reg,
                        p,
                        r,
                        regularization_mode=regularization_mode,
                        regularization_mu=regularization_mu,
                        effective_shift=eff_shift,
                        scale_source=scale_source,
                    )
                    return p, {
                        "reason_code": "ok",
                        "modified_newton_reused_factor": True,
                        "direction_solve_contract": contract,
                        "_row_metadata": row_metadata,
                        "_component_residual_fn": meta.get("component_residual_fn"),
                        "_tangent_component_actions": tangent_component_actions(
                            meta.get("tangent_component_stiffness_free"),
                            p,
                        ),
                        **action_meta,
                    }

                result = run_multistep_newton(
                    residual_fn, x0, direction_fn,
                    max_newton_steps=max_newton_steps, residual_gate_n=residual_gate_n,
                    allow_signed_direction_globalization=(
                        allow_signed_direction_globalization
                    ),
                )
                summary = result["summary"]
                status = "ready" if summary["stop_reason"] in {STOP_GATE, STOP_MAX_STEPS, STOP_STALLED} else "review"
                payload = {
                    **_base(),
                    "status": status,
                    "reason_code": summary["stop_reason"],
                    "uses_real_mgt_model": True,
                    "mgt_source": str(mgt_model),
                    "regularization": {
                        "mode": regularization_mode, "mu": regularization_mu,
                        "effective_shift": eff_shift, "scale_source": scale_source,
                        "selected_from_f2f": True,
                        "effective_shift_vs_production_515_ratio": (
                            eff_shift / PRODUCTION_LAMBDA if PRODUCTION_LAMBDA else None),
                    },
                    "newton_history": result["newton_history"],
                    "summary": summary,
                    "resource_usage": {
                        "dof_count": meta["dof_count"], "free_dof_count": meta["free_dof_count"],
                        "element_count": meta["element_count"],
                    },
                }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument("--load-scale", type=float, default=0.1)
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"], default="real_per_element",
    )
    parser.add_argument(
        "--frame-tangent-source",
        choices=["service_material_plus_geometric_delta", "force_based_residual_tangent"],
        default="service_material_plus_geometric_delta",
    )
    parser.add_argument("--regularization-mode", default="relative_diagonal_shift")
    parser.add_argument("--regularization-mu", type=float, default=0.1)
    parser.add_argument("--direction-solver", default="sparse_direct_spsolve")  # interface parity
    parser.add_argument("--max-newton-steps", type=int, default=8)
    parser.add_argument("--residual-gate-n", type=float, default=5.0e-4)
    parser.add_argument("--allow-signed-direction-globalization", action="store_true")
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()
    payload = run_g1_regularized_reference_newton_candidate(
        mgt_model=args.mgt_model, roundtrip_npz=args.roundtrip_npz, load_scale=args.load_scale,
        frame_service_tangent_source=args.frame_service_tangent_source,
        frame_tangent_source=args.frame_tangent_source,
        regularization_mode=args.regularization_mode, regularization_mu=args.regularization_mu,
        max_newton_steps=args.max_newton_steps, residual_gate_n=args.residual_gate_n,
        allow_signed_direction_globalization=args.allow_signed_direction_globalization,
        output_json=args.output_json,
    )
    s = payload.get("summary", {})
    print(
        "g1-regularized-reference-newton-candidate: "
        f"status={payload['status']} reason={payload['reason_code']} "
        f"steps={s.get('steps_taken')} init={s.get('initial_residual_n')} final={s.get('final_residual_n')} "
        f"total_reduction={s.get('total_reduction_ratio')} monotonic={s.get('monotonic_residual_decrease')} "
        f"gate={s.get('residual_gate_passed')} -> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
