#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from runtime_contracts import InputContractError, validate_input_contract
try:
    from foundation_link_library import describe_foundation_link_library
except Exception:  # pragma: no cover - fallback keeps the validator additive.
    def describe_foundation_link_library() -> dict[str, object]:
        return {}

try:
    from device_library import describe_device_library
except Exception:  # pragma: no cover - fallback keeps the validator additive.
    def describe_device_library() -> dict[str, object]:
        return {}

from special_link_library import (
    BearingLink,
    CompressionOnlyLink,
    FrictionLink,
    GapLink,
    PoundingLink,
    UpliftLink,
    describe_special_link_library,
)


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["out"],
    "properties": {
        "out": {"type": "string", "minLength": 1},
    },
}


def _close(a: float, b: float, tol: float = 1.0e-9) -> bool:
    return abs(float(a) - float(b)) <= float(tol)


def _validate_gap() -> dict[str, object]:
    link = GapLink(stiffness=8.0e4, gap_opening=0.004)
    open_state = link.evaluate(0.002)
    closed_state = link.evaluate(0.006)
    expected_force = 8.0e4 * (0.006 - 0.004)
    passed = (
        not open_state.engaged
        and _close(open_state.force, 0.0)
        and closed_state.engaged
        and _close(closed_state.force, expected_force)
        and _close(closed_state.tangent, 8.0e4)
    )
    return {
        "validated": bool(passed),
        "implementation_class": type(link).__name__,
        "checks": {
            "open_gap_zero_force": bool(not open_state.engaged and _close(open_state.force, 0.0)),
            "closure_force_linear": bool(_close(closed_state.force, expected_force)),
            "closure_tangent_linear": bool(_close(closed_state.tangent, 8.0e4)),
        },
        "sample_points": {
            "open": {"displacement": 0.002, "force": open_state.force, "state": open_state.state_label},
            "closed": {"displacement": 0.006, "force": closed_state.force, "state": closed_state.state_label},
        },
        "link_model_type": "normal_gap_unilateral",
    }


def _validate_uplift() -> dict[str, object]:
    link = UpliftLink(stiffness=7.5e4)
    uplifted = link.evaluate(0.003)
    seated = link.evaluate(-0.002)
    expected_force = 7.5e4 * 0.002
    passed = (
        not uplifted.engaged
        and _close(uplifted.force, 0.0)
        and seated.engaged
        and _close(seated.force, expected_force)
    )
    return {
        "validated": bool(passed),
        "implementation_class": type(link).__name__,
        "checks": {
            "uplift_releases_contact": bool(not uplifted.engaged and _close(uplifted.force, 0.0)),
            "seating_restores_compression": bool(seated.engaged and _close(seated.force, expected_force)),
        },
        "sample_points": {
            "uplifted": {"displacement": 0.003, "force": uplifted.force, "state": uplifted.state_label},
            "seated": {"displacement": -0.002, "force": seated.force, "state": seated.state_label},
        },
        "link_model_type": "uplift_seat_unilateral",
    }


def _validate_compression_only() -> dict[str, object]:
    link = CompressionOnlyLink(stiffness=9.0e4)
    released = link.evaluate(-0.001)
    compressed = link.evaluate(0.003)
    expected_force = 9.0e4 * 0.003
    passed = (
        not released.engaged
        and _close(released.force, 0.0)
        and compressed.engaged
        and _close(compressed.force, expected_force)
    )
    return {
        "validated": bool(passed),
        "implementation_class": type(link).__name__,
        "checks": {
            "tension_releases": bool(not released.engaged and _close(released.force, 0.0)),
            "compression_carries_force": bool(compressed.engaged and _close(compressed.force, expected_force)),
        },
        "sample_points": {
            "released": {"displacement": -0.001, "force": released.force, "state": released.state_label},
            "compressed": {"displacement": 0.003, "force": compressed.force, "state": compressed.state_label},
        },
        "link_model_type": "compression_only_penalty",
    }


def _validate_bearing() -> dict[str, object]:
    link = BearingLink(elastic_stiffness=1.2e5, yield_force=180.0, post_yield_ratio=0.12)
    elastic = link.evaluate(0.001)
    post = link.evaluate(0.004)
    elastic_limit = 180.0 / 1.2e5
    expected_post = 180.0 + (1.2e5 * 0.12) * (0.004 - elastic_limit)
    passed = (
        elastic.engaged
        and elastic.state_label == "elastic"
        and _close(elastic.force, 120.0)
        and post.engaged
        and post.state_label == "post-yield"
        and _close(post.force, expected_post)
        and _close(post.tangent, 1.2e5 * 0.12)
    )
    return {
        "validated": bool(passed),
        "implementation_class": type(link).__name__,
        "checks": {
            "elastic_branch_linear": bool(_close(elastic.force, 120.0)),
            "post_yield_branch_active": bool(post.state_label == "post-yield" and _close(post.force, expected_post)),
        },
        "sample_points": {
            "elastic": {"displacement": 0.001, "force": elastic.force, "state": elastic.state_label},
            "post_yield": {"displacement": 0.004, "force": post.force, "state": post.state_label},
        },
        "link_model_type": "bearing_bilinear",
    }


def _validate_friction() -> dict[str, object]:
    link = FrictionLink(tangential_stiffness=6.0e4, friction_coefficient=0.42, normal_force=320.0)
    stick = link.evaluate(0.001)
    slip = link.evaluate(0.004)
    limit = 0.42 * 320.0
    passed = (
        stick.engaged
        and stick.state_label == "stick"
        and _close(stick.force, 60.0)
        and slip.engaged
        and slip.state_label == "slip"
        and _close(abs(slip.force), limit)
        and _close(slip.tangent, 0.0)
    )
    return {
        "validated": bool(passed),
        "implementation_class": type(link).__name__,
        "checks": {
            "stick_branch_linear": bool(_close(stick.force, 60.0)),
            "slip_branch_capped": bool(_close(abs(slip.force), limit) and _close(slip.tangent, 0.0)),
        },
        "sample_points": {
            "stick": {"displacement": 0.001, "force": stick.force, "state": stick.state_label},
            "slip": {"displacement": 0.004, "force": slip.force, "state": slip.state_label},
        },
        "link_model_type": "coulomb_friction",
    }


def _validate_pounding() -> dict[str, object]:
    link = PoundingLink(contact_stiffness=1.8e5, damping=220.0, impact_gap=0.003)
    separated = link.evaluate(0.002, velocity=0.4)
    impact = link.evaluate(0.006, velocity=0.5)
    expected_force = 1.8e5 * (0.006 - 0.003) + 220.0 * 0.5
    passed = (
        not separated.engaged
        and _close(separated.force, 0.0)
        and impact.engaged
        and impact.state_label == "impact"
        and _close(impact.force, expected_force)
    )
    return {
        "validated": bool(passed),
        "implementation_class": type(link).__name__,
        "checks": {
            "pre_impact_open": bool(not separated.engaged and _close(separated.force, 0.0)),
            "impact_force_kelvin_voigt": bool(_close(impact.force, expected_force)),
        },
        "sample_points": {
            "separated": {"displacement": 0.002, "velocity": 0.4, "force": separated.force, "state": separated.state_label},
            "impact": {"displacement": 0.006, "velocity": 0.5, "force": impact.force, "state": impact.state_label},
        },
        "link_model_type": "kelvin_voigt_pounding",
    }


def _validate_event_sequence() -> dict[str, object]:
    uplift = UpliftLink(stiffness=7.5e4)
    pounding = PoundingLink(contact_stiffness=1.8e5, damping=220.0, impact_gap=0.003)
    trace = [
        {"step": 1, "seat_disp": 0.002, "impact_disp": 0.002, "impact_vel": 0.2, "expected_uplift": "uplifted", "expected_pounding": "separated"},
        {"step": 2, "seat_disp": -0.001, "impact_disp": 0.002, "impact_vel": 0.1, "expected_uplift": "seated", "expected_pounding": "separated"},
        {"step": 3, "seat_disp": -0.001, "impact_disp": 0.006, "impact_vel": 0.4, "expected_uplift": "seated", "expected_pounding": "impact"},
    ]
    mismatch = 0
    rows = []
    for row in trace:
        uplift_state = uplift.evaluate(row["seat_disp"]).state_label
        pounding_state = pounding.evaluate(row["impact_disp"], velocity=row["impact_vel"]).state_label
        row_mismatch = int(uplift_state != row["expected_uplift"]) + int(pounding_state != row["expected_pounding"])
        mismatch += row_mismatch
        rows.append({
            "step": row["step"],
            "uplift_state": uplift_state,
            "expected_uplift": row["expected_uplift"],
            "pounding_state": pounding_state,
            "expected_pounding": row["expected_pounding"],
            "mismatch": row_mismatch,
        })
    return {"contact_uplift_event_sequence_mismatch": mismatch, "rows": rows}


def _build_support_search_surface(
    *,
    link_model_types: list[str],
    foundation_catalog: dict[str, object],
    device_catalog: dict[str, object],
) -> dict[str, object]:
    foundation_rows = [row for row in foundation_catalog.values() if isinstance(row, dict)]
    device_rows = [row for row in device_catalog.values() if isinstance(row, dict)]
    support_rows = foundation_rows + device_rows

    search_ready_model_types = sorted(
        {
            str(row.get("link_name", "")).strip()
            for row in support_rows
            if bool(row.get("support_search_ready", False)) and str(row.get("link_name", "")).strip()
        }
    )
    node_to_surface_proxy_model_types = sorted(
        {
            str(row.get("link_name", "")).strip()
            for row in support_rows
            if bool(row.get("node_to_surface_proxy", False)) and str(row.get("link_name", "")).strip()
        }
    )
    search_surface_mode_counts: dict[str, int] = {}
    search_family_counts: dict[str, int] = {}
    support_depth_score = 0
    evidence_rows: list[dict[str, object]] = []
    support_search_family_types: set[str] = set()
    node_to_surface_proxy_family_types: set[str] = set()
    for row in support_rows:
        link_name = str(row.get("link_name", "")).strip()
        mode = str(row.get("search_surface_mode", "")).strip()
        family = str(row.get("search_family", "")).strip()
        if mode:
            search_surface_mode_counts[mode] = int(search_surface_mode_counts.get(mode, 0) + 1)
        if family:
            search_family_counts[family] = int(search_family_counts.get(family, 0) + 1)
            support_search_family_types.add(family)
            if bool(row.get("node_to_surface_proxy", False)):
                node_to_surface_proxy_family_types.add(family)
        support_depth_score += int(row.get("support_depth_rank", 0) or 0)
        if link_name:
            evidence_rows.append(
                {
                    "link_name": link_name,
                    "support_role": str(row.get("support_role", "")),
                    "search_surface_mode": mode,
                    "node_to_surface_proxy": bool(row.get("node_to_surface_proxy", False)),
                    "support_search_ready": bool(row.get("support_search_ready", False)),
                    "sample_probe_state": str(row.get("sample_probe_state", "")),
                    "sample_probe_engaged": bool(row.get("sample_probe_engaged", False)),
                }
            )

    contact_search_surface_types = sorted(set(link_model_types))
    search_surface_ready = bool(search_ready_model_types and contact_search_surface_types)
    node_to_surface_proxy_ready = bool(node_to_surface_proxy_model_types)
    support_search_family_requirements = ["device_support_search", "foundation_support_search"]
    contact_family_count = len(contact_search_surface_types)
    return {
        "support_search_model_types": search_ready_model_types,
        "node_to_surface_proxy_model_types": node_to_surface_proxy_model_types,
        "contact_search_surface_types": contact_search_surface_types,
        "contact_family_count": int(contact_family_count),
        "search_surface_mode_counts": search_surface_mode_counts,
        "search_family_counts": search_family_counts,
        "support_search_family_types": sorted(support_search_family_types),
        "node_to_surface_proxy_family_types": sorted(node_to_surface_proxy_family_types),
        "support_search_family_requirements": list(support_search_family_requirements),
        "support_depth_score": int(support_depth_score),
        "support_search_evidence_rows": evidence_rows[:24],
        "search_ready_group_counts": {
            "contact": int(contact_family_count),
            "support_ready": len(search_ready_model_types),
            "node_to_surface_proxy": len(node_to_surface_proxy_model_types),
        },
        "support_search_surface_pass": bool(search_surface_ready),
        "node_to_surface_proxy_pass": bool(node_to_surface_proxy_ready),
        "support_search_family_surface_pass": bool(
            support_search_family_types
            and all(label in support_search_family_types for label in support_search_family_requirements)
        ),
        "node_to_surface_proxy_family_surface_pass": bool(
            node_to_surface_proxy_family_types
            and all(label in node_to_surface_proxy_family_types for label in support_search_family_requirements)
        ),
        "contact_family_surface_pass": bool(contact_family_count >= 6),
    }


def build_structural_contact_validation_payload(out_path: str) -> dict[str, object]:
    categories = {
        "gap": _validate_gap(),
        "uplift": _validate_uplift(),
        "compression_only": _validate_compression_only(),
        "bearing": _validate_bearing(),
        "friction": _validate_friction(),
        "pounding": _validate_pounding(),
    }
    event_sequence = _validate_event_sequence()
    validated_count = sum(1 for row in categories.values() if bool(row.get("validated", False)))
    link_model_types = sorted(
        {
            str(row.get("link_model_type", "")).strip()
            for row in categories.values()
            if str(row.get("link_model_type", "")).strip()
        }
    )
    foundation_catalog = describe_foundation_link_library()
    device_catalog = describe_device_library()
    foundation_support_model_types = sorted(str(item).strip() for item in foundation_catalog if str(item).strip())
    device_model_types = sorted(str(item).strip() for item in device_catalog if str(item).strip())
    support_link_model_types = sorted(set(link_model_types) | set(foundation_support_model_types) | set(device_model_types))
    support_search_surface = _build_support_search_surface(
        link_model_types=link_model_types,
        foundation_catalog=foundation_catalog,
        device_catalog=device_catalog,
    )
    contract_pass = (
        validated_count == len(categories)
        and int(event_sequence["contact_uplift_event_sequence_mismatch"]) == 0
        and bool(support_search_surface["contact_family_surface_pass"])
        and bool(support_search_surface["support_search_family_surface_pass"])
        and bool(support_search_surface["node_to_surface_proxy_family_surface_pass"])
    )
    checks = {
        "contact_validation_pass": bool(validated_count == len(categories)),
        "event_sequence_pass": bool(int(event_sequence["contact_uplift_event_sequence_mismatch"]) == 0),
        "support_search_surface_pass": bool(support_search_surface["support_search_surface_pass"]),
        "node_to_surface_proxy_pass": bool(support_search_surface["node_to_surface_proxy_pass"]),
        "contact_family_surface_pass": bool(support_search_surface["contact_family_surface_pass"]),
        "support_search_family_surface_pass": bool(support_search_surface["support_search_family_surface_pass"]),
        "node_to_surface_proxy_family_surface_pass": bool(
            support_search_surface["node_to_surface_proxy_family_surface_pass"]
        ),
    }
    summary_line = (
        f"Structural contact validation: {'PASS' if contract_pass else 'CHECK'} | "
        f"validated={validated_count}/{len(categories)} | "
        f"event_sequence={int(event_sequence['contact_uplift_event_sequence_mismatch'])} | "
        f"contact={len(link_model_types)} | "
        f"foundation={len(foundation_support_model_types)} | "
        f"device={len(device_model_types)} | "
        f"support_search={len(support_search_surface['support_search_model_types'])} | "
        f"node_surface_proxy={len(support_search_surface['node_to_surface_proxy_model_types'])}"
    )
    return {
        "schema_version": "1.0",
        "run_id": "phase1-structural-contact-validation",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {"out": out_path},
        "checks": checks,
        "summary": {
            "validated_category_count": validated_count,
            "required_category_count": len(categories),
            "contact_uplift_event_sequence_mismatch": int(event_sequence["contact_uplift_event_sequence_mismatch"]),
            "link_model_types": link_model_types,
            "implementation_catalog": describe_special_link_library(),
            "foundation_support_model_types": foundation_support_model_types,
            "device_model_types": device_model_types,
            "support_link_model_types": support_link_model_types,
            "support_library_group_counts": {
                "contact": len(link_model_types),
                "foundation": len(foundation_support_model_types),
                "device": len(device_model_types),
            },
            "support_implementation_catalogs": {
                "special_link_library": describe_special_link_library(),
                "foundation_link_library": foundation_catalog,
                "device_library": device_catalog,
            },
            "support_search_model_types": support_search_surface["support_search_model_types"],
            "node_to_surface_proxy_model_types": support_search_surface["node_to_surface_proxy_model_types"],
            "contact_search_surface_types": support_search_surface["contact_search_surface_types"],
            "contact_family_count": int(support_search_surface["contact_family_count"]),
            "search_surface_mode_counts": support_search_surface["search_surface_mode_counts"],
            "search_family_counts": support_search_surface["search_family_counts"],
            "support_search_family_types": support_search_surface["support_search_family_types"],
            "node_to_surface_proxy_family_types": support_search_surface["node_to_surface_proxy_family_types"],
            "support_search_family_requirements": support_search_surface["support_search_family_requirements"],
            "search_ready_group_counts": support_search_surface["search_ready_group_counts"],
            "support_depth_score": support_search_surface["support_depth_score"],
            "support_search_evidence_rows": support_search_surface["support_search_evidence_rows"],
        },
        "categories": categories,
        "event_sequence": event_sequence,
        "summary_line": summary_line,
        "limitations": [
            "This validation covers deterministic constitutive link behavior and contact-uplift chronology, not full finite-element general contact solve parity.",
            "Friction and pounding are validated against closed-form branch expectations for the implemented link laws.",
        ],
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_STRUCTURAL_CONTACT_VALIDATION_FAIL",
        "reason": "validated special-link constitutive library" if contract_pass else "one or more structural-contact link validations failed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/structural_contact_validation_report.json")
    args = parser.parse_args()
    input_payload = {"out": str(args.out)}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_structural_contact_validation")
        payload = build_structural_contact_validation_payload(str(out))
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote structural contact validation report: {out}")
        if not payload["contract_pass"]:
            raise SystemExit(1)
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-structural-contact-validation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": str(exc),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
