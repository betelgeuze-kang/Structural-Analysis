#!/usr/bin/env python3
"""Summarize direct nonlinear foundation/soil-link evidence from checked-in contracts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from runtime_contracts import InputContractError, validate_input_contract
try:
    from foundation_link_library import describe_foundation_link_library
except Exception:  # pragma: no cover - additive fallback when the library is unavailable.
    def describe_foundation_link_library() -> dict[str, object]:
        return {}

try:
    from device_library import describe_device_library
except Exception:  # pragma: no cover - additive fallback when the library is unavailable.
    def describe_device_library() -> dict[str, object]:
        return {}


REASONS = {
    "PASS": "direct nonlinear foundation/soil-link evidence is present across foundation optimization, SSI, soil-link dynamics, and validated support links",
    "ERR_INVALID_INPUT": "invalid foundation/soil-link gate input",
    "ERR_FOUNDATION_SCOPE": "foundation optimization scope evidence is missing",
    "ERR_SSI_BOUNDARY": "nonlinear SSI boundary evidence is missing",
    "ERR_SOIL_TUNNEL": "soil tunnel SSI dynamic evidence is missing",
    "ERR_IMPEDANCE_SCHEMA": "soil impedance schema does not expose radial/tangential spring-dashpot contracts",
    "ERR_FOUNDATION_LINK_MODELS": "foundation-oriented support link models are missing",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "foundation_optimization_report",
        "foundation_optimization_artifact",
        "ssi_boundary_report",
        "soil_tunnel_ssi_report",
        "soil_impedance_table",
        "structural_contact_validation_report",
        "out",
    ],
    "properties": {
        "foundation_optimization_report": {"type": "string", "minLength": 1},
        "foundation_optimization_artifact": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "soil_tunnel_ssi_report": {"type": "string", "minLength": 1},
        "soil_impedance_table": {"type": "string", "minLength": 1},
        "structural_contact_validation_report": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _sorted_string_list(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _sorted_string_union(*sources: object) -> list[str]:
    merged: set[str] = set()
    for source in sources:
        if isinstance(source, (list, tuple, set)):
            candidates = source
        else:
            continue
        for item in candidates:
            text = str(item).strip()
            if text:
                merged.add(text)
    return sorted(merged)


def _int_map(items: object) -> dict[str, int]:
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


def _merge_int_maps_max(*sources: object) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in sources:
        for key, value in _int_map(source).items():
            merged[key] = max(merged.get(key, 0), int(value))
    return merged


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--foundation-optimization-report",
        default="implementation/phase1/release/design_optimization/foundation_optimization_report.json",
    )
    parser.add_argument(
        "--foundation-optimization-artifact",
        default="implementation/phase1/release/design_optimization/foundation_optimization_artifact.json",
    )
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--soil-tunnel-ssi-report", default="implementation/phase1/soil_tunnel_ssi_report.json")
    parser.add_argument("--soil-impedance-table", default="implementation/phase1/soil_impedance_table.json")
    parser.add_argument(
        "--structural-contact-validation-report",
        default="implementation/phase1/structural_contact_validation_report.json",
    )
    parser.add_argument("--out", default="implementation/phase1/foundation_soil_link_gate_report.json")
    args = parser.parse_args()

    input_payload = {
        "foundation_optimization_report": str(args.foundation_optimization_report),
        "foundation_optimization_artifact": str(args.foundation_optimization_artifact),
        "ssi_boundary_report": str(args.ssi_boundary_report),
        "soil_tunnel_ssi_report": str(args.soil_tunnel_ssi_report),
        "soil_impedance_table": str(args.soil_impedance_table),
        "structural_contact_validation_report": str(args.structural_contact_validation_report),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_foundation_soil_link_gate")

        foundation_report_path = Path(args.foundation_optimization_report)
        foundation_artifact_path = Path(args.foundation_optimization_artifact)
        ssi_boundary_path = Path(args.ssi_boundary_report)
        soil_tunnel_path = Path(args.soil_tunnel_ssi_report)
        soil_impedance_path = Path(args.soil_impedance_table)
        structural_contact_validation_path = Path(args.structural_contact_validation_report)

        foundation_report = _load_json(foundation_report_path)
        foundation_artifact = _load_json(foundation_artifact_path)
        ssi_boundary = _load_json(ssi_boundary_path)
        soil_tunnel = _load_json(soil_tunnel_path)
        soil_impedance_text = _load_text(soil_impedance_path)
        structural_contact_validation = _load_json(structural_contact_validation_path)

        foundation_checks = foundation_report.get("checks") if isinstance(foundation_report.get("checks"), dict) else {}
        foundation_summary = foundation_report.get("summary") if isinstance(foundation_report.get("summary"), dict) else {}
        foundation_artifact_summary = (
            foundation_artifact.get("summary") if isinstance(foundation_artifact.get("summary"), dict) else {}
        )
        ssi_checks = ssi_boundary.get("checks") if isinstance(ssi_boundary.get("checks"), dict) else {}
        soil_tunnel_checks = soil_tunnel.get("checks") if isinstance(soil_tunnel.get("checks"), dict) else {}
        structural_contact_summary = (
            structural_contact_validation.get("summary")
            if isinstance(structural_contact_validation.get("summary"), dict)
            else {}
        )
        structural_contact_checks = (
            structural_contact_validation.get("checks")
            if isinstance(structural_contact_validation.get("checks"), dict)
            else {}
        )
        link_model_types = sorted(
            str(item).strip()
            for item in (structural_contact_summary.get("link_model_types") or [])
            if str(item).strip()
        )
        foundation_support_catalog = describe_foundation_link_library()
        foundation_support_model_types = _sorted_string_union(
            structural_contact_summary.get("foundation_support_model_types"),
            list(foundation_support_catalog.keys()),
        )
        required_foundation_support_models = ["p-y", "pile_head", "q-z", "t-z"]
        missing_foundation_support_models = [
            name for name in required_foundation_support_models if name not in foundation_support_model_types
        ]
        device_catalog = describe_device_library()
        device_model_types = _sorted_string_union(
            structural_contact_summary.get("device_model_types"),
            list(device_catalog.keys()),
        )
        derived_support_search_model_types = [
            name
            for name, row in {**foundation_support_catalog, **device_catalog}.items()
            if isinstance(row, dict) and bool(row.get("support_search_ready", False))
        ]
        support_search_model_types = _sorted_string_union(
            structural_contact_summary.get("support_search_model_types"),
            derived_support_search_model_types,
        )
        derived_search_family_counts: dict[str, int] = {}
        for row in list(foundation_support_catalog.values()) + list(device_catalog.values()):
            if not isinstance(row, dict):
                continue
            family = str(row.get("search_family", "")).strip()
            if not family:
                continue
            derived_search_family_counts[family] = int(derived_search_family_counts.get(family, 0) + 1)
        search_family_counts = _merge_int_maps_max(
            structural_contact_summary.get("search_family_counts"),
            derived_search_family_counts,
        )
        support_search_family_types = _sorted_string_union(
            structural_contact_summary.get("support_search_family_types"),
            list(search_family_counts.keys()),
            [
                str(row.get("search_family", "")).strip()
                for row in list(foundation_support_catalog.values()) + list(device_catalog.values())
                if isinstance(row, dict) and str(row.get("search_family", "")).strip()
            ],
        )
        support_search_family_requirements = sorted(
            {
                str(item).strip()
                for item in (
                    structural_contact_summary.get("support_search_family_requirements")
                    or ["device_support_search", "foundation_support_search"]
                )
                if str(item).strip()
            }
        )
        derived_node_to_surface_proxy_model_types = [
            name
            for name, row in {**foundation_support_catalog, **device_catalog}.items()
            if isinstance(row, dict) and bool(row.get("node_to_surface_proxy", False))
        ]
        node_to_surface_proxy_model_types = _sorted_string_union(
            structural_contact_summary.get("node_to_surface_proxy_model_types"),
            derived_node_to_surface_proxy_model_types,
        )
        node_to_surface_proxy_family_types = _sorted_string_union(
            structural_contact_summary.get("node_to_surface_proxy_family_types"),
            [
                str(row.get("search_family", "")).strip()
                for row in list(foundation_support_catalog.values()) + list(device_catalog.values())
                if isinstance(row, dict)
                and bool(row.get("node_to_surface_proxy", False))
                and str(row.get("search_family", "")).strip()
            ],
        )
        derived_search_surface_mode_counts: dict[str, int] = {}
        for row in list(foundation_support_catalog.values()) + list(device_catalog.values()):
            if not isinstance(row, dict):
                continue
            mode = str(row.get("search_surface_mode", "")).strip()
            if mode:
                derived_search_surface_mode_counts[mode] = int(derived_search_surface_mode_counts.get(mode, 0) + 1)
        search_surface_mode_counts = _merge_int_maps_max(
            structural_contact_summary.get("search_surface_mode_counts"),
            derived_search_surface_mode_counts,
        )
        derived_support_depth_score = sum(
            int((row.get("support_depth_rank", 0) or 0))
            for row in list(foundation_support_catalog.values()) + list(device_catalog.values())
            if isinstance(row, dict)
        )
        try:
            summary_support_depth_score = int(structural_contact_summary.get("support_depth_score", 0) or 0)
        except Exception:
            summary_support_depth_score = 0
        support_depth_score = max(summary_support_depth_score, derived_support_depth_score)
        contact_group_counts = _merge_int_maps_max(
            structural_contact_summary.get("support_link_group_counts"),
            structural_contact_summary.get("support_library_group_counts"),
            structural_contact_summary.get("search_ready_group_counts"),
        )
        try:
            explicit_contact_family_count = int(structural_contact_summary.get("contact_family_count", 0) or 0)
        except Exception:
            explicit_contact_family_count = 0
        derived_contact_family_count = max(
            len(link_model_types),
            int(contact_group_counts.get("contact", 0) or 0),
        )
        contact_family_count = max(explicit_contact_family_count, derived_contact_family_count)
        required_link_models = [
            "bearing_bilinear",
            "compression_only_penalty",
            "normal_gap_unilateral",
            "uplift_seat_unilateral",
        ]
        missing_link_models = [name for name in required_link_models if name not in link_model_types]

        impedance_schema_tokens = (
            "k_radial_N_m2",
            "k_tangential_N_m2",
            "c_radial_Ns_m2",
            "c_tangential_Ns_m2",
        )
        foundation_scope_ready = bool(
            foundation_report.get("contract_pass", False)
            and foundation_checks.get("foundation_scope_ready", False)
            and foundation_checks.get("foundation_optimization_evidence_present", False)
            and int(foundation_summary.get("foundation_member_type_count", 0) or 0) > 0
        )
        foundation_artifact_ready = bool(
            foundation_artifact.get("contract_pass", False)
            and int(foundation_artifact_summary.get("optimized_foundation_group_count", 0) or 0) > 0
        )
        ssi_boundary_ready = bool(
            ssi_boundary.get("contract_pass", False)
            and ssi_checks.get("ssi_nonlinear_boundary_active", False)
            and ssi_checks.get("ssi_transfer_finite", False)
            and ssi_checks.get("material_model_pass", False)
        )
        soil_tunnel_ready = bool(
            soil_tunnel.get("contract_pass", False)
            and bool(soil_tunnel_checks.get("finite_response", False))
            and bool(soil_tunnel_checks.get("monotonic_stiffness", False))
            and bool(soil_tunnel_checks.get("positive_damping", False))
            and bool(soil_tunnel_checks.get("high_freq_attenuation", False))
        )
        impedance_schema_ready = bool(soil_impedance_text and all(token in soil_impedance_text for token in impedance_schema_tokens))
        foundation_link_models_ready = bool(
            structural_contact_validation.get("contract_pass", False)
            and not missing_link_models
            and not missing_foundation_support_models
        )

        checks = {
            "foundation_scope_ready": bool(foundation_scope_ready),
            "foundation_artifact_ready": bool(foundation_artifact_ready),
            "ssi_boundary_ready": bool(ssi_boundary_ready),
            "soil_tunnel_ready": bool(soil_tunnel_ready),
            "impedance_schema_ready": bool(impedance_schema_ready),
            "foundation_link_models_ready": bool(foundation_link_models_ready),
            "foundation_support_model_surface_ready": bool(not missing_foundation_support_models),
            "device_model_surface_ready": bool(bool(device_model_types)),
            "support_search_surface_ready": bool(
                structural_contact_checks.get("support_search_surface_pass", bool(support_search_model_types))
            ),
            "contact_family_surface_ready": bool(
                structural_contact_checks.get("contact_family_surface_pass", contact_family_count >= len(required_link_models))
            ),
            "support_search_family_surface_ready": bool(
                structural_contact_checks.get(
                    "support_search_family_surface_pass",
                    bool(
                        support_search_family_types
                        and all(label in support_search_family_types for label in support_search_family_requirements)
                    ),
                )
            ),
            "node_to_surface_proxy_ready": bool(
                structural_contact_checks.get("node_to_surface_proxy_pass", bool(node_to_surface_proxy_model_types))
            ),
            "node_to_surface_proxy_family_surface_ready": bool(
                structural_contact_checks.get(
                    "node_to_surface_proxy_family_surface_pass",
                    bool(
                        node_to_surface_proxy_family_types
                        and all(label in node_to_surface_proxy_family_types for label in support_search_family_requirements)
                    ),
                )
            ),
        }
        contract_pass = bool(
            checks["foundation_scope_ready"]
            and checks["foundation_artifact_ready"]
            and checks["ssi_boundary_ready"]
            and checks["soil_tunnel_ready"]
            and checks["impedance_schema_ready"]
            and checks["foundation_link_models_ready"]
            and checks["foundation_support_model_surface_ready"]
            and checks["contact_family_surface_ready"]
            and checks["support_search_family_surface_ready"]
            and checks["node_to_surface_proxy_family_surface_ready"]
        )
        if not checks["foundation_scope_ready"] or not checks["foundation_artifact_ready"]:
            reason_code = "ERR_FOUNDATION_SCOPE"
        elif not checks["ssi_boundary_ready"]:
            reason_code = "ERR_SSI_BOUNDARY"
        elif not checks["soil_tunnel_ready"]:
            reason_code = "ERR_SOIL_TUNNEL"
        elif not checks["impedance_schema_ready"]:
            reason_code = "ERR_IMPEDANCE_SCHEMA"
        elif not (
            checks["foundation_link_models_ready"]
            and checks["contact_family_surface_ready"]
            and checks["support_search_family_surface_ready"]
            and checks["node_to_surface_proxy_family_surface_ready"]
        ):
            reason_code = "ERR_FOUNDATION_LINK_MODELS"
        else:
            reason_code = "PASS"

        summary = {
            "foundation_member_type_count": int(foundation_summary.get("foundation_member_type_count", 0) or 0),
            "optimized_foundation_group_count": int(
                foundation_artifact_summary.get("optimized_foundation_group_count", 0) or 0
            ),
            "foundation_scope_source": str(foundation_summary.get("foundation_scope_source", "") or ""),
            "foundation_optimization_mode": str(foundation_summary.get("optimization_mode", "") or ""),
            "soil_link_contract_tokens": list(impedance_schema_tokens),
            "foundation_link_model_types": link_model_types,
            "required_foundation_link_models": required_link_models,
            "missing_foundation_link_models": missing_link_models,
            "foundation_support_model_types": foundation_support_model_types,
            "required_foundation_support_models": required_foundation_support_models,
            "missing_foundation_support_models": missing_foundation_support_models,
            "device_model_types": device_model_types,
            "support_library_group_counts": {
                "contact": len(link_model_types),
                "foundation": len(foundation_support_model_types),
                "device": len(device_model_types),
            },
            "support_link_group_counts": {
                "contact": len(link_model_types),
                "foundation": len(foundation_support_model_types),
                "device": len(device_model_types),
            },
            "support_search_model_types": support_search_model_types,
            "support_search_family_types": support_search_family_types,
            "support_search_family_requirements": support_search_family_requirements,
            "node_to_surface_proxy_model_types": node_to_surface_proxy_model_types,
            "node_to_surface_proxy_family_types": node_to_surface_proxy_family_types,
            "search_surface_mode_counts": search_surface_mode_counts,
            "search_family_counts": search_family_counts,
            "contact_family_count": int(contact_family_count),
            "support_depth_score": support_depth_score,
            "support_implementation_catalogs": {
                "foundation_link_library": foundation_support_catalog,
                "device_library": device_catalog,
            },
        }
        summary_line = (
            f"Foundation/soil link: {'PASS' if contract_pass else 'CHECK'} | "
            f"foundation_members={summary['foundation_member_type_count']} | "
            f"optimized_groups={summary['optimized_foundation_group_count']} | "
            f"ssi={'yes' if checks['ssi_boundary_ready'] else 'no'} | "
            f"soil_tunnel={'yes' if checks['soil_tunnel_ready'] else 'no'} | "
            f"impedance_schema={'yes' if checks['impedance_schema_ready'] else 'no'} | "
            f"links={len(link_model_types)}({','.join(link_model_types) if link_model_types else 'none'}) | "
            f"foundation_support={len(foundation_support_model_types)}"
            f"({','.join(foundation_support_model_types) if foundation_support_model_types else 'none'}) | "
            f"devices={len(device_model_types)}({','.join(device_model_types) if device_model_types else 'none'}) | "
            f"support_search={len(support_search_model_types)} | "
            f"node_surface_proxy={len(node_to_surface_proxy_model_types)} | "
            f"support_depth={support_depth_score} | "
            f"support_families={len(support_search_family_types)} | "
            f"proxy_families={len(node_to_surface_proxy_family_types)}"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-foundation-soil-link-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                **input_payload,
                "input_sha256": {
                    "foundation_optimization_report": _sha256(foundation_report_path) if foundation_report_path.exists() else "",
                    "foundation_optimization_artifact": _sha256(foundation_artifact_path) if foundation_artifact_path.exists() else "",
                    "ssi_boundary_report": _sha256(ssi_boundary_path) if ssi_boundary_path.exists() else "",
                    "soil_tunnel_ssi_report": _sha256(soil_tunnel_path) if soil_tunnel_path.exists() else "",
                    "soil_impedance_table": _sha256(soil_impedance_path) if soil_impedance_path.exists() else "",
                    "structural_contact_validation_report": _sha256(structural_contact_validation_path)
                    if structural_contact_validation_path.exists()
                    else "",
                },
            },
            "checks": checks,
            "summary": summary,
            "summary_line": summary_line,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "limitations": [
                "This gate summarizes checked-in contract evidence and does not solve a full foundation FE interaction benchmark matrix by itself.",
                "The soil impedance table is treated as a checked-in contract surface for radial/tangential spring-dashpot parameters.",
                "Foundation link evidence currently relies on validated support-link families plus SSI/foundation optimization artifacts.",
                "Device-library coverage is surfaced here as adjacent implementation evidence and does not replace dedicated device validation gates.",
            ],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line)
        print(f"Wrote foundation/soil link gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-foundation-soil-link-gate",
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
