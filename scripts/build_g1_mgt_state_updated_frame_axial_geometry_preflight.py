#!/usr/bin/env python3
"""Build the fail-closed actual-MGT frame axial-geometry preflight receipt."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from jsonschema import Draft202012Validator
import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PHASE1_ROOT = ROOT / "implementation" / "phase1"
for candidate in (SCRIPT_DIR, SRC_ROOT, PHASE1_ROOT):
    candidate_text = str(candidate)
    while candidate_text in sys.path:
        sys.path.remove(candidate_text)
    sys.path.insert(0, candidate_text)

from mgt_state_updated_frame_axial_geometry import (  # noqa: E402
    audit_state_updated_frame_axial_property_coverage,
    prepack_state_updated_frame_axial_geometry,
)
from parse_mgt_section_material_properties import (  # noqa: E402
    load_mgt_section_material_properties,
)
from release_evidence_metadata import (  # noqa: E402
    engine_version,
    file_sha256,
    git_head,
    input_checksums,
)
from run_mgt_coupled_frame_surface_sparse_equilibrium import (  # noqa: E402
    _select_frame_elements,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    _beam_end_offset_lookup,
    _element_angle_array_from_props,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import (  # noqa: E402
    _run_uncoarsened_parser,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_MGT = Path(
    "implementation/phase1/open_data/midas/"
    "midas_generator_33.optimized.mgt"
)
DEFAULT_RECEIPT_OUT = (
    PRODUCTIZATION
    / "g1_mgt_state_updated_frame_axial_geometry_preflight.json"
)
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_state_updated_frame_axial_geometry_preflight_v1.schema.json"
)
SCHEMA_VERSION = (
    "g1-mgt-state-updated-frame-axial-geometry-preflight.v1"
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _strip_volatile(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            str(key): _strip_volatile(value)
            for key, value in payload.items()
            if key != "generated_at"
        }
    if isinstance(payload, list):
        return [_strip_volatile(value) for value in payload]
    return payload


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _label(repo_root: Path, path: Path) -> str:
    absolute = _resolve(repo_root, path).resolve()
    try:
        return absolute.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _input_paths(*, mgt_path: Path) -> list[Path]:
    return [
        mgt_path,
        Path(
            "implementation/phase1/"
            "mgt_state_updated_frame_axial_geometry.py"
        ),
        Path(
            "implementation/phase1/"
            "parse_mgt_section_material_properties.py"
        ),
        Path(
            "implementation/phase1/"
            "run_mgt_coupled_frame_surface_sparse_equilibrium.py"
        ),
        Path(
            "implementation/phase1/"
            "run_mgt_full_frame_6dof_sparse_equilibrium.py"
        ),
        Path(
            "implementation/phase1/"
            "run_mgt_uncoarsened_boundary_global_equilibrium.py"
        ),
        Path("implementation/phase1/parse_midas_mgt_to_json_npz.py"),
        SCHEMA_PATH,
        Path(
            "scripts/"
            "build_g1_mgt_state_updated_frame_axial_geometry_preflight.py"
        ),
        Path(
            "tests/"
            "test_build_g1_mgt_state_updated_frame_axial_geometry_preflight.py"
        ),
        Path("tests/test_mgt_state_updated_frame_axial_geometry.py"),
        Path("tests/test_parse_mgt_section_material_properties.py"),
    ]


def build_preflight(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_mgt = _resolve(repo_root, mgt_path)
    if not resolved_mgt.is_file():
        raise FileNotFoundError(f"mgt_path is missing: {resolved_mgt}")

    properties = load_mgt_section_material_properties(resolved_mgt)
    section_props = properties.get("sections") or {}
    source_material_props = properties.get("source_materials") or {}
    dgn_material_aliases = (
        properties.get("dgn_material_property_aliases") or {}
    )
    dgn_alias_audit = properties["dgn_material_property_alias_audit"]
    resolved_material_props = dict(source_material_props)
    resolved_material_props.update(dgn_material_aliases)
    beam_end_offsets = _beam_end_offset_lookup(
        properties.get("beam_end_offsets")
    )
    with tempfile.TemporaryDirectory(
        prefix="g1-frame-axial-preflight-"
    ) as temporary_directory:
        _roundtrip_json, generated_roundtrip, parser_report, _parser_run = (
            _run_uncoarsened_parser(
                mgt_path=resolved_mgt,
                work_dir=Path(temporary_directory),
            )
        )
        generated_roundtrip_sha256 = file_sha256(generated_roundtrip)
        with np.load(generated_roundtrip, allow_pickle=False) as archive:
            node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
            elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
            elem_type_code = np.asarray(
                archive["elem_type_code"], dtype=np.int32
            )
            elem_section_id = np.asarray(
                archive["elem_section_id"], dtype=np.int32
            )
            elem_material_id = np.asarray(
                archive["elem_material_id"], dtype=np.int32
            )
            conn_ptr = np.asarray(
                archive["elem_conn_ptr"], dtype=np.int64
            )
            conn_idx = np.asarray(
                archive["elem_conn_idx"], dtype=np.int64
            )
            elem_angle_deg = (
                np.asarray(archive["elem_angle_deg"], dtype=np.float64)
                if "elem_angle_deg" in archive.files
                else _element_angle_array_from_props(properties, elem_id)
            )

    frame_elements, connectivity_audit = _select_frame_elements(
        node_xyz=node_xyz,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        elem_angle_deg=elem_angle_deg,
        beam_end_offsets=beam_end_offsets,
    )
    strict_property_audit = audit_state_updated_frame_axial_property_coverage(
        frame_elements=frame_elements,
        section_props=section_props,
        material_props=source_material_props,
    )
    resolved_property_audit = (
        audit_state_updated_frame_axial_property_coverage(
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=resolved_material_props,
        )
    )

    strict_packed = None
    strict_failure: Exception | None = None
    try:
        strict_packed = prepack_state_updated_frame_axial_geometry(
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=source_material_props,
            require_real_properties=True,
        )
    except Exception as exc:  # receipt preserves unexpected failures too
        strict_failure = exc

    strict_prepack_succeeded = strict_packed is not None
    strict_expected_fail_closed = bool(
        not strict_property_audit["exact_source_property_coverage"]
        and isinstance(strict_failure, ValueError)
        and "requires complete source property coverage" in str(strict_failure)
    )
    strict_fallback_count = int(
        strict_packed.meta["property_fallback_count"]
        if strict_packed is not None
        else 0
    )
    strict_prepack_probe = {
        "attempted": True,
        "succeeded": strict_prepack_succeeded,
        "expected_fail_closed": strict_expected_fail_closed,
        "failure_type": (
            strict_failure.__class__.__name__
            if strict_failure is not None
            else None
        ),
        "failure_reason_code": (
            "INCOMPLETE_FRAME_SOURCE_PROPERTY_BINDING"
            if strict_expected_fail_closed
            else (
                "UNEXPECTED_PREPACK_FAILURE"
                if strict_failure is not None
                else None
            )
        ),
        "failure_message": (
            str(strict_failure) if strict_failure is not None else None
        ),
        "property_fallback_attempted": False,
        "property_fallback_count": strict_fallback_count,
    }

    resolved_packed = None
    resolved_failure: Exception | None = None
    try:
        resolved_packed = prepack_state_updated_frame_axial_geometry(
            node_xyz=node_xyz,
            frame_elements=frame_elements,
            section_props=section_props,
            material_props=resolved_material_props,
            require_real_properties=True,
        )
    except Exception as exc:  # receipt preserves unexpected failures too
        resolved_failure = exc
    resolved_fallback_count = int(
        resolved_packed.meta["property_fallback_count"]
        if resolved_packed is not None
        else 0
    )
    resolved_prepack_probe = {
        "attempted": True,
        "succeeded": resolved_packed is not None,
        "expected_fail_closed": False,
        "failure_type": (
            resolved_failure.__class__.__name__
            if resolved_failure is not None
            else None
        ),
        "failure_reason_code": (
            "UNEXPECTED_PREPACK_FAILURE"
            if resolved_failure is not None
            else None
        ),
        "failure_message": (
            str(resolved_failure) if resolved_failure is not None else None
        ),
        "property_fallback_attempted": False,
        "property_fallback_count": resolved_fallback_count,
    }
    alias_material_ids = {int(value) for value in dgn_material_aliases}
    alias_frame_usage: dict[int, int] = {}
    for element in frame_elements:
        material_id = int(element.material_id)
        if material_id not in alias_material_ids:
            continue
        alias_frame_usage[material_id] = (
            int(alias_frame_usage.get(material_id, 0)) + 1
        )
    alias_frame_element_count = int(sum(alias_frame_usage.values()))
    diagnostic_execution_ready = bool(
        dgn_alias_audit["contract_pass"]
        and resolved_property_audit["exact_source_property_coverage"]
        and resolved_packed is not None
        and resolved_fallback_count == 0
        and alias_frame_element_count
        == strict_property_audit["unresolved_source_property_element_count"]
    )
    engineer_review_required = bool(
        diagnostic_execution_ready
        and dgn_alias_audit["engineer_review_required"]
    )
    readiness_pass = bool(
        diagnostic_execution_ready and not engineer_review_required
    )
    contract_pass = bool(
        parser_report["contract_pass"]
        and connectivity_audit["frame_connectivity_source"]
        == "elem_conn_ptr/elem_conn_idx"
        and not connectivity_audit["edge_index_used_for_element_binding"]
        and connectivity_audit["line_element_row_accounting_exact"]
        and int(connectivity_audit["line_elements_solved"])
        == len(frame_elements)
        and int(strict_property_audit["frame_element_count"])
        == len(frame_elements)
        and int(resolved_property_audit["frame_element_count"])
        == len(frame_elements)
        and not strict_property_audit["exact_source_property_coverage"]
        and strict_expected_fail_closed
        and strict_fallback_count == 0
        and diagnostic_execution_ready
    )
    claims = {
        "actual_mgt_source_and_roundtrip_consumed": True,
        "authoritative_element_connectivity_consumed": bool(
            connectivity_audit["frame_connectivity_source"]
            == "elem_conn_ptr/elem_conn_idx"
            and not connectivity_audit[
                "edge_index_used_for_element_binding"
            ]
        ),
        "exact_raw_material_table_frame_property_coverage": bool(
            strict_property_audit["exact_source_property_coverage"]
        ),
        "exact_source_derived_alias_frame_property_coverage": bool(
            resolved_property_audit["exact_source_property_coverage"]
        ),
        "missing_property_prepack_failed_closed": (
            strict_expected_fail_closed
        ),
        "dgn_exact_type_name_alias_contract_pass": bool(
            dgn_alias_audit["contract_pass"]
        ),
        "dgn_numeric_elastic_override_consumed": False,
        "dgn_alias_engineer_review_required": engineer_review_required,
        "synthetic_property_fallback_used": False,
        "design_material_rows_promoted_to_analysis_properties": False,
        "actual_mgt_state_updated_axial_geometry_prepacked": (
            resolved_packed is not None
        ),
        "actual_mgt_state_updated_axial_geometry_connected_to_residual": False,
        "full_nonlinear_continuation": False,
        "full_corotational_frame": False,
        "g1_full_building_closure": False,
    }
    blockers: list[str] = [
        "raw_material_table_binding_incomplete_source_derived_alias_available"
    ]
    if engineer_review_required:
        blockers.append(
            "dgn_exact_type_name_material_inheritance_engineer_review_required"
        )
    if not claims["actual_mgt_state_updated_axial_geometry_prepacked"]:
        blockers.append("actual_mgt_state_updated_axial_geometry_not_prepacked")
    blockers.extend(
        [
            "actual_mgt_state_updated_axial_geometry_not_connected_to_residual",
            "full_nonlinear_continuation_not_executed",
            "full_corotational_frame_not_implemented",
        ]
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "ready"
            if readiness_pass
            else ("partial" if diagnostic_execution_ready else "blocked")
        ),
        "contract_pass": contract_pass,
        "readiness_pass": readiness_pass,
        "diagnostic_execution_ready": diagnostic_execution_ready,
        "engineer_review_required": engineer_review_required,
        "evidence_closure_pass": False,
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "source_commit_exact_replay_claim": False,
        "source_tree_state": "working_tree_with_uncommitted_goal_changes",
        "input_checksums": input_checksums(
            _input_paths(mgt_path=mgt_path),
            repo_root=repo_root,
        ),
        "case_id": "g1_real_mgt_state_updated_frame_axial_geometry_preflight",
        "inputs": {
            "mgt_path": _label(repo_root, mgt_path),
            "mgt_sha256": file_sha256(resolved_mgt),
            "roundtrip_derivation": (
                "parse_midas_mgt_to_json_npz:no_resolve_rigid_links:"
                "no_drop_unreferenced_nodes"
            ),
            "roundtrip_generated_uncoarsened": True,
            "generated_roundtrip_sha256": generated_roundtrip_sha256,
            "uncoarsened_parser_contract_pass": bool(
                parser_report["contract_pass"]
            ),
            "node_count": int(node_xyz.shape[0]),
            "element_count": int(elem_id.size),
            "analysis_material_table_ids": sorted(
                int(identifier) for identifier in source_material_props
            ),
            "dgn_alias_material_ids": sorted(
                int(identifier) for identifier in dgn_material_aliases
            ),
            "resolved_analysis_material_ids": sorted(
                int(identifier) for identifier in resolved_material_props
            ),
            "dgn_alias_frame_element_count": alias_frame_element_count,
            "dgn_alias_frame_material_id_counts": [
                {
                    "material_id": int(identifier),
                    "element_count": int(count),
                }
                for identifier, count in sorted(alias_frame_usage.items())
            ],
        },
        "frame_connectivity_audit": connectivity_audit,
        "source_property_coverage_audit": strict_property_audit,
        "dgn_material_property_alias_audit": dgn_alias_audit,
        "resolved_source_property_coverage_audit": (
            resolved_property_audit
        ),
        "prepack_probe": strict_prepack_probe,
        "resolved_prepack_probe": resolved_prepack_probe,
        "claims": claims,
        "blockers_remaining": list(dict.fromkeys(blockers)),
        "artifacts": {
            "receipt": _label(repo_root, receipt_out),
            "schema": str(SCHEMA_PATH),
        },
        "claim_boundary": (
            "This preflight preserves the raw *MATERIAL-only failure while "
            "allowing a source-derived, exact unique DGN-MATL type/name alias "
            "for diagnostic execution. The alias consumes no DGN numeric "
            "elastic override or synthetic fallback and remains engineer-review-"
            "required. It does not establish a full corotational beam, nonlinear "
            "continuation, HIP parity, or G1 full-building closure."
        ),
    }
    schema = _read_json(repo_root / SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    return payload


def check_preflight(
    *,
    repo_root: Path = ROOT,
    mgt_path: Path = DEFAULT_MGT,
    receipt_out: Path = DEFAULT_RECEIPT_OUT,
) -> tuple[bool, str]:
    target = _resolve(repo_root, receipt_out)
    if not target.is_file():
        return False, "g1_mgt_state_updated_frame_axial_preflight_missing"
    expected = build_preflight(
        repo_root=repo_root,
        mgt_path=mgt_path,
        receipt_out=receipt_out,
    )
    try:
        existing = _read_json(target)
    except Exception as exc:
        return False, (
            "g1_mgt_state_updated_frame_axial_preflight_unreadable:"
            f"{exc.__class__.__name__}"
        )
    if _strip_volatile(existing) != _strip_volatile(expected):
        return False, "g1_mgt_state_updated_frame_axial_preflight_mismatch"
    return True, "g1_mgt_state_updated_frame_axial_preflight_consistent"


def write_preflight(**kwargs: Any) -> dict[str, Any]:
    repo_root = Path(kwargs.get("repo_root", ROOT)).resolve()
    receipt_out = Path(kwargs.get("receipt_out", DEFAULT_RECEIPT_OUT))
    payload = build_preflight(**kwargs)
    target = _resolve(repo_root, receipt_out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_json_text(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--mgt", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        passed, reason = check_preflight(
            repo_root=args.repo_root,
            mgt_path=args.mgt,
            receipt_out=args.receipt_out,
        )
        print(reason)
        return 0 if passed else 1
    payload = write_preflight(
        repo_root=args.repo_root,
        mgt_path=args.mgt,
        receipt_out=args.receipt_out,
    )
    print(_json_text(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
