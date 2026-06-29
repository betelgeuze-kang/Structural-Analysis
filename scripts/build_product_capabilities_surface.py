#!/usr/bin/env python3
"""Build the product capabilities evidence surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OUT = SURFACE_DIR / "product_capabilities_surface.json"
DEFAULT_PUBLIC_BENCHMARK = PRODUCTIZATION / "public_benchmark_source_of_truth.json"
DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE = (
    PRODUCTIZATION / "public_benchmark_operator_intake_packet.json"
)
DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD = (
    PRODUCTIZATION / "public_benchmark_operator_intake_packet.md"
)
DEFAULT_POCKETMD_SURFACE = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_POCKETMD_CONTRACT = PRODUCTIZATION / "pocketmd_lite_contract.json"
DEFAULT_POCKETMD_TOPK_REPORT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET = (
    PRODUCTIZATION / "pocketmd_lite_operator_intake_packet.json"
)
DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD = (
    PRODUCTIZATION / "pocketmd_lite_operator_intake_packet.md"
)
DEFAULT_H_BOND_SURFACE = SURFACE_DIR / "h_bond_backmap_evidence_surface.json"
DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET = (
    PRODUCTIZATION / "h_bond_backmap_operator_intake_packet.json"
)
DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET_MD = (
    PRODUCTIZATION / "h_bond_backmap_operator_intake_packet.md"
)
DEFAULT_GPCR_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_GPCR_PRODUCT_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_product_report.json"
DEFAULT_GPCR_OPERATOR_INTAKE_PACKET = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.json"
DEFAULT_GPCR_OPERATOR_INTAKE_PACKET_MD = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.md"

STRUCTURAL_SURFACE_PATHS = (
    SURFACE_DIR / "element_material_breadth_gate_report.json",
    SURFACE_DIR / "general_fe_contact_benchmark_gate_report.json",
    SURFACE_DIR / "material_constitutive_gate_report.json",
    SURFACE_DIR / "solver_breadth_report.json",
    SURFACE_DIR / "solver_truthfulness_gate_report.json",
    SURFACE_DIR / "steel_composite_constitutive_gate_report.json",
    SURFACE_DIR / "structural_contact_gate_report.json",
    SURFACE_DIR / "surface_interaction_benchmark_gate_report.json",
)

SCHEMA_VERSION = "product-capabilities-surface.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _truthy_contract(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass")
        or payload.get("pass")
        or str(payload.get("status", "")).strip().lower() == "ready"
    )


def _payload_blocked(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("locked") is True
        or payload.get("claim_locked") is True
        or _as_list(payload.get("blockers"))
        or not _truthy_contract(payload)
    )


def _state(payload: dict[str, Any], *, ready_flag: bool | None = None) -> str:
    if ready_flag is not None:
        return "ready" if ready_flag else "blocked"
    return "blocked" if _payload_blocked(payload) else "ready"


def _next_actions(payload: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(payload.get("next_actions"))]


def _blockers(payload: dict[str, Any]) -> list[str]:
    return [str(row) for row in _as_list(payload.get("blockers"))]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _surface_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(payload.get("summary"))
    return summary if summary else _as_dict(payload.get("readiness_summary"))


def _capability_row(
    *,
    capability_id: str,
    title: str,
    capability_kind: str,
    state: str,
    evidence_artifacts: list[Path],
    contract_pass: bool,
    blocker_count: int,
    next_actions: list[str],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "capability_id": capability_id,
        "title": title,
        "capability_kind": capability_kind,
        "state": state,
        "contract_pass": contract_pass,
        "blocker_count": blocker_count,
        "evidence_artifacts": [str(path) for path in evidence_artifacts],
        "next_actions": next_actions,
        "summary": summary or {},
    }


def _structural_solver_capability(repo_root: Path) -> dict[str, Any]:
    payloads = [_load_json(repo_root, path) for path in STRUCTURAL_SURFACE_PATHS]
    present_payloads = [payload for payload in payloads if payload]
    ready_count = sum(1 for payload in present_payloads if not _payload_blocked(payload))
    return _capability_row(
        capability_id="structural_solver_restricted_alpha_surface",
        title="Restricted alpha structural solver evidence",
        capability_kind="engineering_core",
        state="ready" if present_payloads and ready_count == len(STRUCTURAL_SURFACE_PATHS) else "blocked",
        evidence_artifacts=list(STRUCTURAL_SURFACE_PATHS),
        contract_pass=bool(present_payloads and ready_count == len(STRUCTURAL_SURFACE_PATHS)),
        blocker_count=len(STRUCTURAL_SURFACE_PATHS) - ready_count,
        next_actions=[] if ready_count == len(STRUCTURAL_SURFACE_PATHS) else ["refresh_structural_solver_surface_receipts"],
        summary={
            "surface_count": len(STRUCTURAL_SURFACE_PATHS),
            "present_surface_count": len(present_payloads),
            "ready_surface_count": ready_count,
        },
    )


def _public_benchmark_capability(repo_root: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, DEFAULT_PUBLIC_BENCHMARK)
    operator_intake = _load_json(repo_root, DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE)
    source_operator_summary = _as_dict(payload.get("operator_intake_packet"))
    ready = bool(payload.get("public_benchmark_ready"))
    return _capability_row(
        capability_id="public_benchmark_harness",
        title="Public benchmark harness",
        capability_kind="external_science_evidence",
        state=_state(payload, ready_flag=ready),
        evidence_artifacts=[
            DEFAULT_PUBLIC_BENCHMARK,
            DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE,
            DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD,
        ],
        contract_pass=bool(_truthy_contract(payload) and ready),
        blocker_count=len(_blockers(payload)),
        next_actions=_dedupe(_next_actions(payload) + _next_actions(operator_intake)),
        summary={
            "status": str(payload.get("status") or ""),
            "tier_beta_ready": bool(payload.get("tier_beta_ready")),
            "public_benchmark_ready": ready,
            "operator_intake_packet_status": str(
                operator_intake.get("status") or source_operator_summary.get("status") or ""
            ),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count")
                or source_operator_summary.get("required_slot_count")
                or 0
            ),
            "operator_intake_artifact": str(DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE),
            "operator_intake_markdown_artifact": str(DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD),
            "subset_manifest_summary": _as_dict(payload.get("subset_manifest_summary")),
            "enrichment_scorecard_summary": _as_dict(payload.get("enrichment_scorecard_summary")),
        },
    )


def _pocketmd_capability(repo_root: Path) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_POCKETMD_SURFACE)
    contract = _load_json(repo_root, DEFAULT_POCKETMD_CONTRACT)
    topk_report = _load_json(repo_root, DEFAULT_POCKETMD_TOPK_REPORT)
    operator_intake = _load_json(repo_root, DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET)
    ready = bool(surface.get("product_surface_ready") and surface.get("contract_pass"))
    return _capability_row(
        capability_id="pocketmd_lite_top_k_refinement",
        title="PocketMD Lite top-k refinement",
        capability_kind="science_product_surface",
        state=_state(surface, ready_flag=ready),
        evidence_artifacts=[
            DEFAULT_POCKETMD_CONTRACT,
            DEFAULT_POCKETMD_TOPK_REPORT,
            DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET,
            DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD,
            DEFAULT_POCKETMD_SURFACE,
        ],
        contract_pass=bool(_truthy_contract(contract) and ready),
        blocker_count=len(_blockers(surface)),
        next_actions=_dedupe(_next_actions(operator_intake) + _next_actions(surface)),
        summary={
            "surface_status": str(surface.get("status") or ""),
            "product_surface_ready": ready,
            "real_refinement_case_count": _surface_summary(surface).get("real_refinement_case_count", 0),
            "top_k_candidate_count": _surface_summary(surface).get("top_k_candidate_count", 0),
            "topk_report_status": str(topk_report.get("status") or ""),
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
        },
    )


def _single_surface_capability(
    *,
    repo_root: Path,
    path: Path,
    capability_id: str,
    title: str,
    capability_kind: str,
    next_action_fallback: str,
) -> dict[str, Any]:
    payload = _load_json(repo_root, path)
    state = _state(payload)
    return _capability_row(
        capability_id=capability_id,
        title=title,
        capability_kind=capability_kind,
        state=state,
        evidence_artifacts=[path],
        contract_pass=state == "ready",
        blocker_count=len(_blockers(payload)),
        next_actions=_next_actions(payload) or ([] if state == "ready" else [next_action_fallback]),
        summary={
            "status": str(payload.get("status") or ""),
            "reason_code": str(payload.get("reason_code") or ""),
            "first_blocked_target": str(payload.get("first_blocked_target") or ""),
            "root_cause_tags": [str(row) for row in _as_list(payload.get("root_cause_tags"))],
        },
    )


def _h_bond_capability(repo_root: Path) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_H_BOND_SURFACE)
    operator_intake = _load_json(repo_root, DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET)
    state = _state(surface)
    return _capability_row(
        capability_id="h_bond_backmap_evidence",
        title="H-bond backmap evidence",
        capability_kind="science_evidence_surface",
        state=state,
        evidence_artifacts=[
            DEFAULT_H_BOND_SURFACE,
            DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET,
            DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET_MD,
        ],
        contract_pass=state == "ready",
        blocker_count=len(_blockers(surface)),
        next_actions=_dedupe(
            _next_actions(operator_intake)
            + _next_actions(surface)
            + ([] if state == "ready" else ["fill_h_bond_backmap_operator_intake_packet"])
        ),
        summary={
            "status": str(surface.get("status") or ""),
            "reason_code": str(surface.get("reason_code") or ""),
            "first_blocked_target": str(surface.get("first_blocked_target") or ""),
            "root_cause_tags": [str(row) for row in _as_list(surface.get("root_cause_tags"))],
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
            "required_receipts": [str(row) for row in _as_list(surface.get("required_receipts"))],
            "claim_locked": bool(surface.get("claim_locked", True)),
        },
    )


def _gpcr_capability(repo_root: Path) -> dict[str, Any]:
    surface = _load_json(repo_root, DEFAULT_GPCR_SURFACE)
    product_report = _load_json(repo_root, DEFAULT_GPCR_PRODUCT_REPORT)
    operator_intake = _load_json(repo_root, DEFAULT_GPCR_OPERATOR_INTAKE_PACKET)
    phase3_exit_gate = _as_dict(
        product_report.get("phase3_exit_gate") or surface.get("phase3_exit_gate")
    )
    state = _state(surface)
    return _capability_row(
        capability_id="gpcr_hard_decoy_evidence",
        title="GPCR hard-decoy evidence",
        capability_kind="science_evidence_surface",
        state=state,
        evidence_artifacts=[
            DEFAULT_GPCR_SURFACE,
            DEFAULT_GPCR_PRODUCT_REPORT,
            DEFAULT_GPCR_OPERATOR_INTAKE_PACKET,
            DEFAULT_GPCR_OPERATOR_INTAKE_PACKET_MD,
        ],
        contract_pass=state == "ready",
        blocker_count=len(_blockers(surface)),
        next_actions=_dedupe(
            _next_actions(product_report)
            + _next_actions(operator_intake)
            + _next_actions(surface)
            + ([] if state == "ready" else ["run_gpcr_hard_decoy_suite_materializer"])
        ),
        summary={
            "status": str(surface.get("status") or ""),
            "reason_code": str(surface.get("reason_code") or ""),
            "first_blocked_target": str(surface.get("first_blocked_target") or ""),
            "root_cause_tags": [str(row) for row in _as_list(surface.get("root_cause_tags"))],
            "product_report_route": str(product_report.get("route") or "/product/gpcr-hard-decoy-suite-report"),
            "product_report_ready": bool(product_report.get("read_model_ready")),
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
            "broad_gpcr_family_claim_safe": bool(surface.get("broad_gpcr_family_claim_safe")),
            "phase3_exit_gate_status": str(phase3_exit_gate.get("status") or ""),
            "phase3_failed_criterion_count": int(
                phase3_exit_gate.get("failed_criterion_count") or 0
            ),
            "phase3_failed_criteria": [
                str(row) for row in _as_list(phase3_exit_gate.get("failed_criteria"))
            ],
        },
    )


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_product_capabilities_surface.py"),
        DEFAULT_PUBLIC_BENCHMARK,
        DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE,
        DEFAULT_PUBLIC_BENCHMARK_OPERATOR_INTAKE_MD,
        DEFAULT_POCKETMD_CONTRACT,
        DEFAULT_POCKETMD_TOPK_REPORT,
        DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET,
        DEFAULT_POCKETMD_OPERATOR_INTAKE_PACKET_MD,
        DEFAULT_POCKETMD_SURFACE,
        DEFAULT_GPCR_PRODUCT_REPORT,
        DEFAULT_GPCR_OPERATOR_INTAKE_PACKET,
        DEFAULT_GPCR_OPERATOR_INTAKE_PACKET_MD,
        DEFAULT_H_BOND_SURFACE,
        DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET,
        DEFAULT_H_BOND_OPERATOR_INTAKE_PACKET_MD,
        DEFAULT_GPCR_SURFACE,
        *STRUCTURAL_SURFACE_PATHS,
    ]


def build_product_capabilities_surface(*, repo_root: Path = ROOT) -> dict[str, Any]:
    capability_rows = [
        _structural_solver_capability(repo_root),
        _public_benchmark_capability(repo_root),
        _h_bond_capability(repo_root),
        _gpcr_capability(repo_root),
        _pocketmd_capability(repo_root),
    ]
    ready_count = sum(1 for row in capability_rows if row["state"] == "ready")
    blocked_rows = [row for row in capability_rows if row["state"] != "ready"]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=False,
            reuse_policy="product_capabilities_surface_aggregates_science_and_release_evidence",
            repo_root=repo_root,
        ),
        "surface_id": "product_capabilities_surface",
        "surface_kind": "product_capabilities_surface",
        "surface_scope": "product_capability_discovery",
        "status": "ready",
        "reason_code": "PASS",
        "contract_pass": True,
        "locked": False,
        "claim_locked": False,
        "product_capabilities_ready": False,
        "capability_count": len(capability_rows),
        "ready_capability_count": ready_count,
        "blocked_capability_count": len(blocked_rows),
        "capability_rows": capability_rows,
        "blockers": [],
        "first_blocked_target": "",
        "root_cause_tags": [],
        "read_model": {
            "route": "/product/capabilities",
            "artifact": str(DEFAULT_OUT),
            "mutation_allowed": False,
        },
        "next_actions": [
            "work_capability_rows_with_state_blocked",
            "regenerate_pm_release_gate_report",
            "regenerate_goal_bottleneck_action_board",
        ],
        "summary_line": (
            "Product capabilities surface: READY | "
            f"capabilities={len(capability_rows)} | ready={ready_count} | "
            f"blocked={len(blocked_rows)}"
        ),
        "claim_boundary": (
            "This surface is a read-only capability discovery map over existing evidence. "
            "It does not promote beta, GPCR, PocketMD, benchmark, or release claims beyond "
            "the referenced artifacts."
        ),
    }


def write_product_capabilities_surface(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_product_capabilities_surface(repo_root=repo_root)
    resolved = out if out.is_absolute() else repo_root / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_product_capabilities_surface(repo_root=args.repo_root, out=args.out)
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
