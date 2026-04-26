#!/usr/bin/env python3
"""Summarize a general FE contact benchmark matrix from checked-in structural/interface evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "general FE contact benchmark evidence is present across direct structural links, interface transfer, foundation/soil links, and SSI dynamics",
    "ERR_INVALID_INPUT": "invalid general FE contact benchmark input",
    "ERR_DIRECT_CONTACT": "direct structural-contact benchmark rows are incomplete",
    "ERR_FOUNDATION_LINK": "foundation/soil-link benchmark evidence is incomplete",
    "ERR_INTERFACE_TRANSFER": "substructuring interface-transfer evidence is incomplete",
    "ERR_SSI_BOUNDARY": "nonlinear SSI boundary evidence is incomplete",
    "ERR_SOIL_TUNNEL": "soil-tunnel SSI benchmark evidence is incomplete",
    "ERR_SUPPORT_SURFACE": "support-search / node-to-surface proxy evidence is incomplete",
    "ERR_SUPPORT_FAMILY_SURFACE": "support-search family-surface evidence is incomplete",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "structural_contact_validation_report",
        "structural_contact_gate_report",
        "foundation_soil_link_gate_report",
        "ssi_boundary_report",
        "substructuring_interface_report",
        "soil_tunnel_ssi_report",
        "out",
    ],
    "properties": {
        "structural_contact_validation_report": {"type": "string", "minLength": 1},
        "structural_contact_gate_report": {"type": "string", "minLength": 1},
        "foundation_soil_link_gate_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "substructuring_interface_report": {"type": "string", "minLength": 1},
        "soil_tunnel_ssi_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}

DIRECT_CATEGORY_ORDER = (
    ("gap", "gap"),
    ("uplift", "uplift"),
    ("compression-only", "compression_only"),
    ("bearing", "bearing"),
    ("friction", "friction"),
    ("pounding", "pounding"),
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _bool(value: Any) -> bool:
    return bool(value)


def _row(label: str, *, ready: bool, evidence_kind: str, contract: str, note: str, source: str = "") -> dict[str, Any]:
    return {
        "label": str(label),
        "ready": bool(ready),
        "evidence_kind": str(evidence_kind),
        "contract": str(contract),
        "source": str(source),
        "note": str(note),
    }


def _sorted_string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _int_map(items: Any) -> dict[str, int]:
    if not isinstance(items, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, value in items.items():
        label = str(key).strip()
        if not label:
            continue
        try:
            normalized[label] = int(value)
        except Exception:
            continue
    return normalized


def _surface_list(*candidates: Any) -> list[str]:
    merged: set[str] = set()
    for candidate in candidates:
        merged.update(_sorted_string_list(candidate))
    return sorted(merged)


def _surface_counts(*candidates: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for candidate in candidates:
        for key, value in _int_map(candidate).items():
            merged[key] = max(merged.get(key, 0), value)
    return merged


def _missing_required_labels(required: list[str], present: list[str]) -> list[str]:
    if not required:
        return []
    present_labels = {str(label).strip() for label in present if str(label).strip()}
    return [label for label in required if label not in present_labels]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--structural-contact-validation-report",
        default="implementation/phase1/structural_contact_validation_report.json",
    )
    parser.add_argument(
        "--structural-contact-gate-report",
        default="implementation/phase1/structural_contact_gate_report.json",
    )
    parser.add_argument(
        "--foundation-soil-link-gate-report",
        default="implementation/phase1/foundation_soil_link_gate_report.json",
    )
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument(
        "--substructuring-interface-report",
        default="implementation/phase1/substructuring_interface_report.json",
    )
    parser.add_argument("--soil-tunnel-ssi-report", default="implementation/phase1/soil_tunnel_ssi_report.json")
    parser.add_argument("--out", default="implementation/phase1/general_fe_contact_benchmark_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "structural_contact_validation_report": str(args.structural_contact_validation_report),
        "structural_contact_gate_report": str(args.structural_contact_gate_report),
        "foundation_soil_link_gate_report": str(args.foundation_soil_link_gate_report),
        "ssi_boundary_report": str(args.ssi_boundary_report),
        "substructuring_interface_report": str(args.substructuring_interface_report),
        "soil_tunnel_ssi_report": str(args.soil_tunnel_ssi_report),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_general_fe_contact_benchmark_gate")

        structural_contact_validation_path = Path(args.structural_contact_validation_report)
        structural_contact_gate_path = Path(args.structural_contact_gate_report)
        foundation_soil_link_gate_path = Path(args.foundation_soil_link_gate_report)
        ssi_boundary_path = Path(args.ssi_boundary_report)
        substructuring_interface_path = Path(args.substructuring_interface_report)
        soil_tunnel_path = Path(args.soil_tunnel_ssi_report)

        structural_contact_validation = _load_json(structural_contact_validation_path)
        structural_contact_gate = _load_json(structural_contact_gate_path)
        foundation_soil_link_gate = _load_json(foundation_soil_link_gate_path)
        ssi_boundary = _load_json(ssi_boundary_path)
        substructuring_interface = _load_json(substructuring_interface_path)
        soil_tunnel = _load_json(soil_tunnel_path)

        validation_categories = (
            structural_contact_validation.get("categories")
            if isinstance(structural_contact_validation.get("categories"), dict)
            else {}
        )
        validation_summary = (
            structural_contact_validation.get("summary")
            if isinstance(structural_contact_validation.get("summary"), dict)
            else {}
        )
        structural_contact_checks = (
            structural_contact_gate.get("checks")
            if isinstance(structural_contact_gate.get("checks"), dict)
            else {}
        )
        structural_contact_support_surface = (
            structural_contact_gate.get("support_surface_evidence")
            if isinstance(structural_contact_gate.get("support_surface_evidence"), dict)
            else {}
        )
        category_readiness = [
            row
            for row in (structural_contact_gate.get("category_readiness") or [])
            if isinstance(row, dict)
        ]
        category_readiness_by_label = {
            str(row.get("category", "") or "").strip(): row for row in category_readiness if str(row.get("category", "") or "").strip()
        }
        foundation_checks = (
            foundation_soil_link_gate.get("checks")
            if isinstance(foundation_soil_link_gate.get("checks"), dict)
            else {}
        )
        foundation_summary = (
            foundation_soil_link_gate.get("summary")
            if isinstance(foundation_soil_link_gate.get("summary"), dict)
            else {}
        )
        ssi_checks = ssi_boundary.get("checks") if isinstance(ssi_boundary.get("checks"), dict) else {}
        substructuring_checks = (
            substructuring_interface.get("checks")
            if isinstance(substructuring_interface.get("checks"), dict)
            else {}
        )
        substructuring_metrics = (
            substructuring_interface.get("metrics")
            if isinstance(substructuring_interface.get("metrics"), dict)
            else {}
        )
        soil_tunnel_checks = soil_tunnel.get("checks") if isinstance(soil_tunnel.get("checks"), dict) else {}
        soil_tunnel_metrics = soil_tunnel.get("metrics") if isinstance(soil_tunnel.get("metrics"), dict) else {}
        support_link_group_counts = _surface_counts(
            structural_contact_support_surface.get("support_link_group_counts"),
            foundation_summary.get("support_link_group_counts"),
            foundation_summary.get("support_library_group_counts"),
            validation_summary.get("support_link_group_counts"),
            validation_summary.get("support_library_group_counts"),
        )
        if not support_link_group_counts:
            support_link_group_counts = {
                "contact": len(DIRECT_CATEGORY_ORDER),
                "foundation": len(_sorted_string_list(foundation_summary.get("foundation_support_model_types"))),
                "device": len(_sorted_string_list(foundation_summary.get("device_model_types"))),
            }
        support_search_model_types = _surface_list(
            structural_contact_support_surface.get("support_search_model_types"),
            foundation_summary.get("support_search_model_types"),
            validation_summary.get("support_search_model_types"),
        )
        node_to_surface_proxy_model_types = _surface_list(
            structural_contact_support_surface.get("node_to_surface_proxy_model_types"),
            foundation_summary.get("node_to_surface_proxy_model_types"),
            validation_summary.get("node_to_surface_proxy_model_types"),
        )
        search_surface_mode_counts = _surface_counts(
            structural_contact_support_surface.get("search_surface_mode_counts"),
            foundation_summary.get("search_surface_mode_counts"),
            validation_summary.get("search_surface_mode_counts"),
        )
        search_family_counts = _surface_counts(
            structural_contact_support_surface.get("search_family_counts"),
            foundation_summary.get("search_family_counts"),
            validation_summary.get("search_family_counts"),
        )
        support_search_family_types = _surface_list(
            structural_contact_support_surface.get("support_search_family_types"),
            foundation_summary.get("support_search_family_types"),
            validation_summary.get("support_search_family_types"),
            list(search_family_counts.keys()),
        )
        support_search_family_requirements = _surface_list(
            structural_contact_support_surface.get("support_search_family_requirements"),
            foundation_summary.get("support_search_family_requirements"),
            validation_summary.get("support_search_family_requirements"),
            ["device_support_search", "foundation_support_search"],
        )
        node_to_surface_proxy_family_types = _surface_list(
            structural_contact_support_surface.get("node_to_surface_proxy_family_types"),
            foundation_summary.get("node_to_surface_proxy_family_types"),
            validation_summary.get("node_to_surface_proxy_family_types"),
        )
        support_depth_score = 0
        for candidate in (
            structural_contact_support_surface.get("support_depth_score"),
            foundation_summary.get("support_depth_score"),
            validation_summary.get("support_depth_score"),
        ):
            try:
                support_depth_score = max(support_depth_score, int(candidate))
            except Exception:
                continue
        support_search_surface_present = bool(
            structural_contact_checks.get("support_search_surface_present", False)
            or foundation_checks.get("support_search_surface_ready", False)
            or support_search_model_types
        )
        node_to_surface_proxy_surface_present = bool(
            structural_contact_checks.get("node_to_surface_proxy_surface_present", False)
            or foundation_checks.get("node_to_surface_proxy_surface_ready", False)
            or node_to_surface_proxy_model_types
        )
        support_depth_surface_present = bool(
            structural_contact_checks.get("support_depth_surface_present", False) or support_depth_score > 0
        )
        support_search_missing_family_types = _missing_required_labels(
            support_search_family_requirements,
            support_search_family_types,
        )
        node_to_surface_proxy_missing_family_types = _missing_required_labels(
            support_search_family_requirements,
            node_to_surface_proxy_family_types,
        )
        support_search_missing_family_counts = [
            label
            for label in support_search_family_requirements
            if int(search_family_counts.get(label, 0) or 0) <= 0
        ]
        support_search_family_surface_explicit = bool(
            support_search_family_types and search_family_counts
        )
        node_to_surface_proxy_family_surface_explicit = bool(node_to_surface_proxy_family_types)

        matrix_rows: list[dict[str, Any]] = []
        ready_direct_categories = 0
        direct_link_model_types = [
            str(item).strip()
            for item in (validation_summary.get("link_model_types") or [])
            if str(item).strip()
        ]
        for category_label, readiness_key in DIRECT_CATEGORY_ORDER:
            validation_row = validation_categories.get(category_label) or validation_categories.get(readiness_key) or {}
            gate_row = category_readiness_by_label.get(category_label, {})
            ready = bool(
                structural_contact_validation.get("contract_pass", False)
                and structural_contact_gate.get("contract_pass", False)
                and _bool(validation_row.get("validated"))
                and _bool(gate_row.get("ready"))
                and _bool(structural_contact_checks.get(f"{readiness_key}_ready", False))
            )
            if ready:
                ready_direct_categories += 1
            matrix_rows.append(
                _row(
                    category_label,
                    ready=ready,
                    evidence_kind="direct_structural_contact",
                    contract=str(validation_row.get("link_model_type", "") or "support_link"),
                    source="structural_contact_validation+gate",
                    note=(
                        f"class={str(validation_row.get('implementation_class', '') or 'n/a')} | "
                        f"validated={bool(validation_row.get('validated', False))} | "
                        f"gate_ready={bool(gate_row.get('ready', False))}"
                    ),
                )
            )

        foundation_ready = bool(
            foundation_soil_link_gate.get("contract_pass", False)
            and _bool(foundation_checks.get("foundation_scope_ready"))
            and _bool(foundation_checks.get("foundation_artifact_ready"))
            and _bool(foundation_checks.get("foundation_link_models_ready"))
        )
        matrix_rows.append(
            _row(
                "foundation_soil_link",
                ready=foundation_ready,
                evidence_kind="foundation_soil_link",
                contract="soil_impedance+support_links",
                source="foundation_soil_link_gate",
                note=(
                    f"foundation_members={int(foundation_summary.get('foundation_member_type_count', 0) or 0)} | "
                    f"optimized_groups={int(foundation_summary.get('optimized_foundation_group_count', 0) or 0)} | "
                    f"links={len(direct_link_model_types)}"
                ),
            )
        )

        interface_ready = bool(
            substructuring_interface.get("contract_pass", False)
            and _bool(substructuring_checks.get("finite_transfer"))
            and _bool(substructuring_checks.get("coupling_stability"))
        )
        matrix_rows.append(
            _row(
                "interface_transfer",
                ready=interface_ready,
                evidence_kind="substructuring_interface",
                contract="finite_transfer+coupling_stability",
                source="substructuring_interface_report",
                note=f"transfer_ratio={float(substructuring_metrics.get('mean_transfer_ratio_building_to_track', 0.0) or 0.0):.3f}",
            )
        )

        ssi_ready = bool(
            ssi_boundary.get("contract_pass", False)
            and _bool(ssi_checks.get("ssi_nonlinear_boundary_active"))
            and _bool(ssi_checks.get("ssi_transfer_finite"))
            and _bool(ssi_checks.get("material_model_pass"))
        )
        matrix_rows.append(
            _row(
                "ssi_boundary_nonlinear",
                ready=ssi_ready,
                evidence_kind="ssi_boundary",
                contract="nonlinear_boundary",
                source="ssi_boundary_gate_report",
                note=(
                    f"section_family={bool(ssi_checks.get('section_family_pass', False))} | "
                    f"material_model={bool(ssi_checks.get('material_model_pass', False))}"
                ),
            )
        )

        soil_tunnel_ready = bool(
            soil_tunnel.get("contract_pass", False)
            and _bool(soil_tunnel_checks.get("finite_response"))
            and _bool(soil_tunnel_checks.get("monotonic_stiffness"))
            and _bool(soil_tunnel_checks.get("positive_damping"))
            and _bool(soil_tunnel_checks.get("high_freq_attenuation"))
        )
        matrix_rows.append(
            _row(
                "soil_tunnel_dynamic",
                ready=soil_tunnel_ready,
                evidence_kind="soil_tunnel_ssi",
                contract="dynamic_impedance_response",
                source="soil_tunnel_ssi_report",
                note=(
                    f"k_range={float(soil_tunnel_metrics.get('k_min', 0.0) or 0.0):.3g}-"
                    f"{float(soil_tunnel_metrics.get('k_max', 0.0) or 0.0):.3g} | "
                    f"damping_range={float(soil_tunnel_metrics.get('c_min', 0.0) or 0.0):.3g}-"
                    f"{float(soil_tunnel_metrics.get('c_max', 0.0) or 0.0):.3g}"
                ),
            )
        )

        ready_row_count = sum(1 for row in matrix_rows if bool(row.get("ready", False)))
        total_row_count = len(matrix_rows)
        checks = {
            "direct_structural_contact_pass": ready_direct_categories == len(DIRECT_CATEGORY_ORDER),
            "foundation_soil_link_pass": bool(foundation_ready),
            "interface_transfer_pass": bool(interface_ready),
            "ssi_boundary_pass": bool(ssi_ready),
            "soil_tunnel_dynamic_pass": bool(soil_tunnel_ready),
            "support_search_surface_pass": bool(support_search_surface_present),
            "node_to_surface_proxy_surface_pass": bool(node_to_surface_proxy_surface_present),
            "support_depth_surface_pass": bool(support_depth_surface_present),
            "support_search_family_surface_required": bool(support_search_surface_present),
            "node_to_surface_proxy_family_surface_required": bool(node_to_surface_proxy_surface_present),
            "support_search_family_surface_explicit": bool(support_search_family_surface_explicit),
            "node_to_surface_proxy_family_surface_explicit": bool(node_to_surface_proxy_family_surface_explicit),
            "support_search_family_requirements_met": not support_search_missing_family_types,
            "node_to_surface_proxy_family_requirements_met": not node_to_surface_proxy_missing_family_types,
            "support_search_family_count_coverage_pass": not support_search_missing_family_counts,
            "support_search_family_surface_pass": bool(
                (not support_search_surface_present)
                or (
                    support_search_family_surface_explicit
                    and not support_search_missing_family_types
                    and not support_search_missing_family_counts
                )
            ),
            "node_to_surface_proxy_family_surface_pass": bool(
                (not node_to_surface_proxy_surface_present)
                or (
                    node_to_surface_proxy_family_surface_explicit
                    and not node_to_surface_proxy_missing_family_types
                )
            ),
            "all_matrix_rows_ready": ready_row_count == total_row_count,
        }
        contract_pass = bool(
            checks["direct_structural_contact_pass"]
            and checks["foundation_soil_link_pass"]
            and checks["interface_transfer_pass"]
            and checks["ssi_boundary_pass"]
            and checks["soil_tunnel_dynamic_pass"]
            and checks["support_search_surface_pass"]
            and checks["node_to_surface_proxy_surface_pass"]
            and checks["support_depth_surface_pass"]
            and checks["support_search_family_surface_pass"]
            and checks["node_to_surface_proxy_family_surface_pass"]
            and checks["all_matrix_rows_ready"]
        )
        if not checks["direct_structural_contact_pass"]:
            reason_code = "ERR_DIRECT_CONTACT"
        elif not checks["foundation_soil_link_pass"]:
            reason_code = "ERR_FOUNDATION_LINK"
        elif not checks["interface_transfer_pass"]:
            reason_code = "ERR_INTERFACE_TRANSFER"
        elif not checks["ssi_boundary_pass"]:
            reason_code = "ERR_SSI_BOUNDARY"
        elif not checks["soil_tunnel_dynamic_pass"]:
            reason_code = "ERR_SOIL_TUNNEL"
        elif not (
            checks["support_search_surface_pass"]
            and checks["node_to_surface_proxy_surface_pass"]
            and checks["support_depth_surface_pass"]
        ):
            reason_code = "ERR_SUPPORT_SURFACE"
        elif not (
            checks["support_search_family_surface_pass"]
            and checks["node_to_surface_proxy_family_surface_pass"]
        ):
            reason_code = "ERR_SUPPORT_FAMILY_SURFACE"
        else:
            reason_code = "PASS"

        coupling_depth_score = int(support_depth_score) + int(ready_row_count)
        general_fe_contact_matrix_surface = {
            "status": "PASS" if contract_pass else "CHECK",
            "ready_row_count": int(ready_row_count),
            "total_row_count": int(total_row_count),
            "direct_structural_contact_ready_count": int(ready_direct_categories),
            "direct_structural_contact_total_count": int(len(DIRECT_CATEGORY_ORDER)),
            "foundation_ready": bool(foundation_ready),
            "interface_ready": bool(interface_ready),
            "ssi_boundary_ready": bool(ssi_ready),
            "soil_tunnel_ready": bool(soil_tunnel_ready),
            "support_link_group_counts": dict(support_link_group_counts),
            "support_search_model_count": len(support_search_model_types),
            "node_to_surface_proxy_model_count": len(node_to_surface_proxy_model_types),
            "support_depth_score": int(support_depth_score),
            "coupling_depth_score": int(coupling_depth_score),
            "search_family_counts": dict(search_family_counts),
            "support_search_family_types": list(support_search_family_types),
            "support_search_family_count": len(support_search_family_types),
            "support_search_family_requirement_count": len(support_search_family_requirements),
            "support_search_missing_family_types": list(support_search_missing_family_types),
            "support_search_missing_family_counts": list(support_search_missing_family_counts),
            "node_to_surface_proxy_family_types": list(node_to_surface_proxy_family_types),
            "node_to_surface_proxy_family_count": len(node_to_surface_proxy_family_types),
            "node_to_surface_proxy_family_requirement_count": len(support_search_family_requirements),
            "node_to_surface_proxy_missing_family_types": list(node_to_surface_proxy_missing_family_types),
            "support_search_family_surface_pass": bool(checks["support_search_family_surface_pass"]),
            "node_to_surface_proxy_family_surface_pass": bool(
                checks["node_to_surface_proxy_family_surface_pass"]
            ),
        }
        summary = {
            "ready_row_count": int(ready_row_count),
            "total_row_count": int(total_row_count),
            "direct_structural_contact_ready_count": int(ready_direct_categories),
            "direct_structural_contact_total_count": int(len(DIRECT_CATEGORY_ORDER)),
            "direct_link_model_types": direct_link_model_types,
            "foundation_member_type_count": int(foundation_summary.get("foundation_member_type_count", 0) or 0),
            "optimized_foundation_group_count": int(foundation_summary.get("optimized_foundation_group_count", 0) or 0),
            "support_link_group_counts": support_link_group_counts,
            "support_search_model_types": support_search_model_types,
            "support_search_model_count": len(support_search_model_types),
            "node_to_surface_proxy_model_types": node_to_surface_proxy_model_types,
            "node_to_surface_proxy_model_count": len(node_to_surface_proxy_model_types),
            "search_surface_mode_counts": search_surface_mode_counts,
            "search_family_counts": search_family_counts,
            "support_search_family_types": support_search_family_types,
            "support_search_family_requirements": support_search_family_requirements,
            "support_search_family_count": len(support_search_family_types),
            "support_search_missing_family_types": support_search_missing_family_types,
            "support_search_missing_family_counts": support_search_missing_family_counts,
            "node_to_surface_proxy_family_types": node_to_surface_proxy_family_types,
            "node_to_surface_proxy_family_count": len(node_to_surface_proxy_family_types),
            "node_to_surface_proxy_missing_family_types": node_to_surface_proxy_missing_family_types,
            "support_depth_score": int(support_depth_score),
            "coupling_depth_score": int(coupling_depth_score),
            "interface_transfer_ratio": float(substructuring_metrics.get("mean_transfer_ratio_building_to_track", 0.0) or 0.0),
            "soil_tunnel_k_min": float(soil_tunnel_metrics.get("k_min", 0.0) or 0.0),
            "soil_tunnel_k_max": float(soil_tunnel_metrics.get("k_max", 0.0) or 0.0),
            "general_fe_contact_matrix_surface": general_fe_contact_matrix_surface,
        }
        summary_line = (
            f"General FE contact matrix: {'PASS' if contract_pass else 'CHECK'} | "
            f"ready={ready_row_count}/{total_row_count} | "
            f"direct={ready_direct_categories}/{len(DIRECT_CATEGORY_ORDER)} | "
            f"foundation={'yes' if foundation_ready else 'no'} | "
            f"interface={'yes' if interface_ready else 'no'} | "
            f"ssi={'yes' if ssi_ready else 'no'} | "
            f"soil_tunnel={'yes' if soil_tunnel_ready else 'no'} | "
            f"support=contact:{int(support_link_group_counts.get('contact', 0) or 0)},"
            f"foundation:{int(support_link_group_counts.get('foundation', 0) or 0)},"
            f"device:{int(support_link_group_counts.get('device', 0) or 0)} | "
            f"support_search={len(support_search_model_types)} | "
            f"node_surface_proxy={len(node_to_surface_proxy_model_types)} | "
            f"support_depth={int(support_depth_score)} | "
            f"coupling_depth={int(coupling_depth_score)} | "
            f"support_families={len(support_search_family_types)}/{len(support_search_family_requirements)} | "
            f"proxy_families={len(node_to_surface_proxy_family_types)}/{len(support_search_family_requirements)}"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-general-fe-contact-benchmark-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                **input_payload,
                "input_sha256": {
                    "structural_contact_validation_report": _sha256(structural_contact_validation_path) if structural_contact_validation_path.exists() else "",
                    "structural_contact_gate_report": _sha256(structural_contact_gate_path) if structural_contact_gate_path.exists() else "",
                    "foundation_soil_link_gate_report": _sha256(foundation_soil_link_gate_path) if foundation_soil_link_gate_path.exists() else "",
                    "ssi_boundary_report": _sha256(ssi_boundary_path) if ssi_boundary_path.exists() else "",
                    "substructuring_interface_report": _sha256(substructuring_interface_path) if substructuring_interface_path.exists() else "",
                    "soil_tunnel_ssi_report": _sha256(soil_tunnel_path) if soil_tunnel_path.exists() else "",
                },
            },
            "checks": checks,
            "general_fe_contact_matrix_surface": general_fe_contact_matrix_surface,
            "summary": summary,
            "matrix_rows": matrix_rows,
            "summary_line": summary_line,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "limitations": [
                "This matrix summarizes checked-in benchmark/gate evidence; it does not claim full general-contact FE parity on its own.",
                "Direct structural-contact rows currently rely on validated special-link constitutive contracts rather than arbitrary mesh-to-mesh contact surfaces.",
                "Foundation/soil and interface rows are contract-backed interaction surfaces used to track solver breadth, not a full multiphysics contact stack.",
            ],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line)
        print(f"Wrote general FE contact benchmark gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-general-fe-contact-benchmark-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(payload["reason"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
