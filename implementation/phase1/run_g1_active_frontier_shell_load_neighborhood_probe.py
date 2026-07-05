#!/usr/bin/env python3
"""Trace active-frontier shell hotspot rows to incident shell load elements."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
if str(PHASE1) in sys.path:
    sys.path.remove(str(PHASE1))
sys.path.insert(0, str(PHASE1))

from run_g1_active_frontier_residual_ownership_probe import (  # noqa: E402
    _load_checkpoint_free_state,
    residual_ownership_breakdown,
)
from run_g1_mgt_physical_line_search_smoke import (  # noqa: E402
    DEFAULT_MGT_MODEL,
    build_mgt_physical_residual_closure,
)
from run_g1_true_newton_reference_candidate import _max_abs  # noqa: E402
from run_mgt_residual_jacobian_consistency_probe import (  # noqa: E402
    _shell_internal_element_hotspot_diagnostics,
    _shell_surface_load_hotspot_diagnostics,
)


SCHEMA_VERSION = "g1-active-frontier-shell-load-neighborhood-probe.v1"
HERE = Path(__file__).resolve().parent
PRODUCTIZATION = HERE / "release_evidence" / "productization"
DEFAULT_CHECKPOINT_NPZ = (
    PRODUCTIZATION
    / "g1_adaptive_fixed_signed_all_components_from_structural_active_set_ls_trust_candidate.npz"
)
DEFAULT_OUT = PRODUCTIZATION / "g1_active_frontier_shell_load_neighborhood_probe.json"


def shell_setup_meta_from_closure_meta(meta: dict[str, Any]) -> dict[str, Any]:
    shell_inputs = meta.get("shell_inputs")
    if not isinstance(shell_inputs, dict):
        return {}
    return {
        "_node_xyz": shell_inputs.get("node_xyz"),
        "_node_id": shell_inputs.get("node_id"),
        "_elem_id": shell_inputs.get("elem_id"),
        "_elem_type_code": shell_inputs.get("elem_type_code"),
        "_elem_section_id": shell_inputs.get("elem_section_id"),
        "_elem_material_id": shell_inputs.get("elem_material_id"),
        "_conn_ptr": shell_inputs.get("conn_ptr"),
        "_conn_idx": shell_inputs.get("conn_idx"),
        "_material_props": shell_inputs.get("material_props"),
        "_plate_thickness_props": shell_inputs.get("plate_thickness_props"),
        "_frame_elements": shell_inputs.get("frame_elements"),
        "_restrained_dofs": shell_inputs.get("restrained_dofs"),
        "load_scale": shell_inputs.get("load_scale", meta.get("load_scale", 1.0)),
        "free": shell_inputs.get("free", meta.get("free")),
    }


def translate_ownership_rows_for_shell_helpers(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    for row in rows:
        dominant = str(
            row.get("dominant_component")
            or row.get("dominant_internal_component")
            or ""
        )
        dof = str(row.get("dof") or row.get("dof_label") or "").lower()
        translated.append(
            {
                "free_row": int(row.get("free_row", row.get("reduced_index", -1))),
                "global_dof": int(row.get("global_dof", -1)),
                "node_index": int(row.get("node_index", -1)),
                "dof": dof,
                "dominant_component": dominant,
                "residual_n": float(row.get("residual_n") or 0.0),
                "external_load_n": float(
                    row.get("external_load_n")
                    if row.get("external_load_n") is not None
                    else row.get("inferred_external_load_n")
                    if row.get("inferred_external_load_n") is not None
                    else 0.0
                ),
                "component_values_n": (
                    dict(row.get("component_values_n"))
                    if isinstance(row.get("component_values_n"), dict)
                    else {}
                ),
            }
        )
    return translated


def _first_row(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return {}


def _top_element_summary(row: dict[str, Any]) -> dict[str, Any]:
    elements = row.get("sample_incident_surface_elements")
    if not isinstance(elements, list) or not elements:
        return {}
    first = elements[0] if isinstance(elements[0], dict) else {}
    return {
        "elem_index": first.get("elem_index"),
        "elem_id": first.get("elem_id"),
        "target_dof_reference_shell_load_n": first.get(
            "target_dof_reference_shell_load_n"
        ),
        "target_dof_bending_internal_force_n": first.get(
            "target_dof_bending_internal_force_n"
        ),
        "target_dof_membrane_internal_force_n": first.get(
            "target_dof_membrane_internal_force_n"
        ),
        "target_dof_shell_internal_force_n": first.get(
            "target_dof_shell_internal_force_n"
        ),
    }


def run_g1_active_frontier_shell_load_neighborhood_probe(
    *,
    mgt_model: Path = DEFAULT_MGT_MODEL,
    checkpoint_npz: Path = DEFAULT_CHECKPOINT_NPZ,
    load_scale: float = 1.0,
    frame_tangent_source: str = "force_based_residual_tangent",
    shell_pressure_load_path_policy: str = "all_components",
    top_count: int = 16,
    max_rows: int = 8,
    max_elements_per_row: int = 12,
    output_json: Path | None = DEFAULT_OUT,
) -> dict[str, Any]:
    residual_fn, _x0, meta = build_mgt_physical_residual_closure(
        mgt_path=Path(mgt_model),
        roundtrip_npz=None,
        load_scale=float(load_scale),
        frame_tangent_source=frame_tangent_source,
        shell_pressure_load_path_policy=shell_pressure_load_path_policy,
    )
    free = np.asarray(meta["free"], dtype=np.int64)
    checkpoint = _load_checkpoint_free_state(
        checkpoint_npz=Path(checkpoint_npz),
        free=free,
        dof_count=int(meta["dof_count"]),
    )
    x = np.asarray(checkpoint["free_state"], dtype=np.float64)
    residual = np.asarray(residual_fn(x), dtype=np.float64)
    component_fn = meta.get("component_residual_fn")
    if not callable(component_fn):
        raise RuntimeError("component_residual_fn_missing")
    components = {
        str(name): np.asarray(values, dtype=np.float64)
        for name, values in component_fn(x).items()
    }
    ownership = residual_ownership_breakdown(
        residual=residual,
        component_forces=components,
        free=free,
        node_id=np.asarray(meta.get("node_id"), dtype=np.int64),
        dof_per_node=int(meta.get("dof_per_node") or 6),
        top_count=int(top_count),
    )
    helper_rows = translate_ownership_rows_for_shell_helpers(
        [
            row
            for row in ownership["top_rows"]
            if str(row.get("dominant_internal_component") or "").startswith("shell")
        ]
    )
    shell_setup_meta = shell_setup_meta_from_closure_meta(meta)
    full_u = np.asarray(checkpoint["full_displacement"], dtype=np.float64)
    surface_load_diagnostics = _shell_surface_load_hotspot_diagnostics(
        top_rows=helper_rows,
        setup_meta=shell_setup_meta,
        max_rows=int(max_rows),
        max_elements_per_row=int(max_elements_per_row),
    )
    internal_element_diagnostics = _shell_internal_element_hotspot_diagnostics(
        top_rows=helper_rows,
        u=full_u,
        setup_meta=shell_setup_meta,
        max_rows=int(max_rows),
        max_elements_per_row=int(max_elements_per_row),
    )
    load_top = _first_row(surface_load_diagnostics)
    internal_top = _first_row(internal_element_diagnostics)
    required_scale = load_top.get(
        "required_reference_shell_load_scale_for_zero_row_residual"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ready",
        "is_candidate_only": True,
        "promotes_g1_closure": False,
        "mgt_model": str(mgt_model),
        "checkpoint_npz": str(checkpoint_npz),
        "load_scale": float(load_scale),
        "frame_tangent_source": frame_tangent_source,
        "shell_pressure_load_path_policy": shell_pressure_load_path_policy,
        "checkpoint": {
            key: value
            for key, value in checkpoint.items()
            if key not in {"free_state", "full_displacement"}
        },
        "summary": {
            "top_residual_inf_n": ownership["top_residual_inf_n"],
            "shell_helper_row_count": len(helper_rows),
            "surface_load_diagnostics_evaluated": (
                surface_load_diagnostics.get("evaluated") is True
            ),
            "internal_element_diagnostics_evaluated": (
                internal_element_diagnostics.get("evaluated") is True
            ),
            "external_minus_reference_shell_load_inf_n": _max_abs(
                np.asarray(
                    [
                        float(row.get("external_minus_reference_shell_load_n") or 0.0)
                        for row in surface_load_diagnostics.get("rows", [])
                        if isinstance(row, dict)
                    ],
                    dtype=np.float64,
                )
            ),
            "component_minus_reconstructed_shell_inf_n": internal_element_diagnostics.get(
                "component_minus_reconstructed_shell_inf_n"
            ),
            "component_minus_reconstructed_bending_inf_n": internal_element_diagnostics.get(
                "component_minus_reconstructed_bending_inf_n"
            ),
            "top_row_node_id": load_top.get("raw_node_id")
            or internal_top.get("raw_node_id"),
            "top_row_dof": load_top.get("dof") or internal_top.get("dof"),
            "top_row_residual_n": load_top.get("residual_n")
            or internal_top.get("residual_n"),
            "top_row_external_load_n": load_top.get("external_load_n"),
            "top_row_reference_shell_load_reconstructed_n": load_top.get(
                "reference_shell_load_reconstructed_n"
            ),
            "top_row_required_reference_shell_load_scale_for_zero_row_residual": (
                required_scale
            ),
            "top_row_shell_internal_to_reference_load_scale": internal_top.get(
                "shell_internal_to_reference_load_scale"
            ),
            "top_row_incident_surface_element_count": internal_top.get(
                "incident_surface_element_count"
            ),
            "top_row_surface_component_element_count": internal_top.get(
                "surface_component_element_count"
            ),
            "top_row_surface_component_frame_connected_node_count": internal_top.get(
                "surface_component_frame_connected_node_count"
            ),
            "top_row_surface_component_restrained_translation_dof_count": internal_top.get(
                "surface_component_restrained_translation_dof_count"
            ),
            "top_row_surface_component_free_pressure_resultant": internal_top.get(
                "surface_component_free_pressure_resultant"
            ),
            "top_incident_element": _top_element_summary(internal_top),
        },
        "surface_load_diagnostics": surface_load_diagnostics,
        "internal_element_diagnostics": internal_element_diagnostics,
        "ownership_top_rows": ownership["top_rows"],
        "claim_boundary": (
            "Active frontier shell load-neighborhood probe only. It reconstructs "
            "incident shell load/internal-force contributors and does not close "
            "G1 full-load nonlinear equilibrium."
        ),
    }
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgt-model", type=Path, default=DEFAULT_MGT_MODEL)
    parser.add_argument("--checkpoint-npz", type=Path, default=DEFAULT_CHECKPOINT_NPZ)
    parser.add_argument("--load-scale", type=float, default=1.0)
    parser.add_argument("--frame-tangent-source", default="force_based_residual_tangent")
    parser.add_argument("--shell-pressure-load-path-policy", default="all_components")
    parser.add_argument("--top-count", type=int, default=16)
    parser.add_argument("--max-rows", type=int, default=8)
    parser.add_argument("--max-elements-per-row", type=int, default=12)
    parser.add_argument("--out", "--output-json", dest="output_json", type=Path, default=DEFAULT_OUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    payload = run_g1_active_frontier_shell_load_neighborhood_probe(
        mgt_model=args.mgt_model,
        checkpoint_npz=args.checkpoint_npz,
        load_scale=args.load_scale,
        frame_tangent_source=args.frame_tangent_source,
        shell_pressure_load_path_policy=args.shell_pressure_load_path_policy,
        top_count=args.top_count,
        max_rows=args.max_rows,
        max_elements_per_row=args.max_elements_per_row,
        output_json=args.output_json,
    )
    summary = payload.get("summary", {})
    print(
        "g1-active-frontier-shell-load-neighborhood-probe: "
        f"status={payload['status']} "
        f"top_residual={summary.get('top_residual_inf_n')} "
        f"required_shell_load_scale={summary.get('top_row_required_reference_shell_load_scale_for_zero_row_residual')} "
        f"incident_elements={summary.get('top_row_incident_surface_element_count')} "
        f"-> {args.output_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
