#!/usr/bin/env python3
"""Build PocketMD Lite contract, report seed, API, handoff, and product surface."""

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

DEFAULT_CONTRACT_OUT = PRODUCTIZATION / "pocketmd_lite_contract.json"
DEFAULT_SURVIVAL_REPORT_OUT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_READONLY_API_OUT = PRODUCTIZATION / "pocketmd_lite_readonly_api.json"
DEFAULT_HANDOFF_OUT = PRODUCTIZATION / "pocketmd_lite_delivery_handoff.json"
DEFAULT_SURFACE_OUT = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"

CONTRACT_SCHEMA_VERSION = "pocketmd-lite-contract.v1"
SURVIVAL_REPORT_SCHEMA_VERSION = "pocketmd-lite-topk-survival-report.v1"
READONLY_API_SCHEMA_VERSION = "pocketmd-lite-readonly-api.v1"
HANDOFF_SCHEMA_VERSION = "pocketmd-lite-delivery-handoff.v1"
SURFACE_SCHEMA_VERSION = "pocketmd-lite-science-product-surface.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _input_paths() -> list[Path]:
    return [Path("scripts/build_pocketmd_lite_product_surface.py")]


def _metadata(*, repo_root: Path, reused_evidence: bool, reuse_policy: str) -> dict[str, Any]:
    return release_evidence_metadata(
        input_paths=_input_paths(),
        reused_evidence=reused_evidence,
        reuse_policy=reuse_policy,
        repo_root=repo_root,
    )


def _metric_contracts() -> list[dict[str, Any]]:
    return [
        {
            "metric_id": "local_min_survival_rate",
            "description": "fraction of top-k candidates that remain in a local minimum after Lite refinement",
            "required": True,
            "direction": "higher_is_better",
        },
        {
            "metric_id": "contact_persistence_rate",
            "description": "fraction of declared receptor-ligand contacts retained after Lite refinement",
            "required": True,
            "direction": "higher_is_better",
        },
        {
            "metric_id": "h_bond_persistence_rate",
            "description": "fraction of declared H-bond contacts retained after Lite refinement",
            "required": True,
            "direction": "higher_is_better",
        },
        {
            "metric_id": "clash_relief_rate",
            "description": "fraction of candidates with reduced severe-clash count after Lite refinement",
            "required": True,
            "direction": "higher_is_better",
        },
        {
            "metric_id": "uncertainty_width_median",
            "description": "median uncertainty interval width for candidate-level Lite refinement deltas",
            "required": True,
            "direction": "lower_is_better",
        },
    ]


def _operator_intake_schema() -> dict[str, Any]:
    return {
        "case_key": "cases",
        "required_case_fields": [
            "case_id",
            "source_family",
            "top_k_rank",
            "candidate_id",
            "pre_refinement_energy_proxy",
            "post_refinement_energy_proxy",
            "local_min_survived",
            "contact_persistence_rate",
            "h_bond_persistence_rate",
            "clash_count_before",
            "clash_count_after",
            "uncertainty_interval",
            "provenance_ref",
            "source_checksum",
        ],
        "top_k_only_policy": (
            "Only candidates selected in the upstream top-k pose or design ranking may be "
            "included. Broad all-atom rescoring, long MD, FEP, and de novo docking claims "
            "remain out of scope."
        ),
        "template": {
            "case_id": "pocketmd_lite_case_001",
            "source_family": "CASF/PDBBind or GPCR operator intake",
            "top_k_rank": 1,
            "candidate_id": "",
            "pre_refinement_energy_proxy": None,
            "post_refinement_energy_proxy": None,
            "local_min_survived": None,
            "contact_persistence_rate": None,
            "h_bond_persistence_rate": None,
            "clash_count_before": None,
            "clash_count_after": None,
            "uncertainty_interval": {"low": None, "high": None, "unit": "energy_proxy_delta"},
            "provenance_ref": "",
            "source_checksum": "",
        },
    }


def build_contract(*, repo_root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        **_metadata(
            repo_root=repo_root,
            reused_evidence=False,
            reuse_policy="pocketmd_lite_contract_generated_from_goal_contract",
        ),
        "status": "contract_ready_operator_evidence_required",
        "contract_pass": True,
        "product_surface_ready": False,
        "product_capability_id": "pocketmd_lite_top_k_refinement",
        "scope": "top_k_lite_refinement_only",
        "top_k_policy": {
            "default_top_k": 5,
            "max_top_k": 20,
            "requires_upstream_ranked_candidates": True,
            "candidate_scope": "top_k_candidates_only",
        },
        "reported_metrics": _metric_contracts(),
        "operator_intake_schema": _operator_intake_schema(),
        "blocked_claims": [
            "broad_all_atom_md_claim",
            "free_energy_perturbation_claim",
            "long_timescale_md_claim",
            "de_novo_binding_mode_claim",
        ],
        "claim_boundary": (
            "PocketMD Lite is a bounded top-k refinement surface. It reports local-min "
            "survival, contact persistence, H-bond persistence, clash relief, and "
            "uncertainty for already-ranked candidates only. It does not claim broad "
            "all-atom MD, FEP, long-timescale dynamics, or autonomous docking accuracy."
        ),
    }


def build_topk_survival_report(*, repo_root: Path = ROOT) -> dict[str, Any]:
    blockers = [
        "pocketmd_lite_topk_candidate_rows_missing",
        "pocketmd_lite_local_min_survival_rows_missing",
        "pocketmd_lite_contact_hbond_persistence_rows_missing",
        "pocketmd_lite_uncertainty_rows_missing",
    ]
    return {
        "schema_version": SURVIVAL_REPORT_SCHEMA_VERSION,
        **_metadata(
            repo_root=repo_root,
            reused_evidence=False,
            reuse_policy="pocketmd_lite_survival_report_seed_from_contract",
        ),
        "status": "operator_evidence_required",
        "contract_pass": False,
        "product_surface_ready": False,
        "real_refinement_case_count": 0,
        "top_k_candidate_count": 0,
        "rows": [],
        "summary": {
            "local_min_survival_rate": None,
            "contact_persistence_rate_median": None,
            "h_bond_persistence_rate_median": None,
            "clash_relief_rate": None,
            "uncertainty_width_median": None,
            "top_k_candidate_count": 0,
            "real_refinement_case_count": 0,
            "blocker_count": len(blockers),
        },
        "required_metrics": [row["metric_id"] for row in _metric_contracts()],
        "blockers": blockers,
        "next_actions": [
            "attach_top_k_candidate_refinement_rows",
            "compute_local_min_survival_report",
            "compute_contact_and_h_bond_persistence",
            "compute_clash_relief_and_uncertainty_summary",
            "regenerate_pocketmd_lite_science_product_surface",
        ],
        "claim_boundary": (
            "This report is a seed shape for PocketMD Lite evidence. With zero real "
            "refinement rows it is intentionally blocked and cannot support a product "
            "claim."
        ),
    }


def build_readonly_api(*, repo_root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema_version": READONLY_API_SCHEMA_VERSION,
        **_metadata(
            repo_root=repo_root,
            reused_evidence=False,
            reuse_policy="pocketmd_lite_readonly_api_contract_generated_from_repo_code",
        ),
        "status": "ready_for_seed_artifacts",
        "contract_pass": True,
        "mutation_allowed": False,
        "endpoints": [
            {
                "endpoint_id": "get_pocketmd_lite_contract",
                "method": "GET",
                "artifact": str(DEFAULT_CONTRACT_OUT),
            },
            {
                "endpoint_id": "get_topk_survival_report",
                "method": "GET",
                "artifact": str(DEFAULT_SURVIVAL_REPORT_OUT),
            },
            {
                "endpoint_id": "get_science_product_surface",
                "method": "GET",
                "artifact": str(DEFAULT_SURFACE_OUT),
            },
            {
                "endpoint_id": "list_operator_required_fields",
                "method": "GET",
                "artifact": str(DEFAULT_CONTRACT_OUT),
                "json_pointer": "/operator_intake_schema/required_case_fields",
            },
        ],
        "forbidden_operations": [
            "run_md_simulation",
            "mutate_candidate_rows",
            "promote_all_atom_or_fep_claim",
            "write_operator_evidence",
        ],
        "claim_boundary": (
            "The read-only API only exposes local contract and report artifacts. It does "
            "not run refinement, mutate evidence, or promote blocked science claims."
        ),
    }


def build_delivery_handoff(*, repo_root: Path = ROOT) -> dict[str, Any]:
    return {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        **_metadata(
            repo_root=repo_root,
            reused_evidence=False,
            reuse_policy="pocketmd_lite_delivery_handoff_generated_from_goal_contract",
        ),
        "status": "handoff_ready_operator_evidence_required",
        "contract_pass": True,
        "owner": "science_product_owner",
        "product_capability_id": "pocketmd_lite_top_k_refinement",
        "evidence_artifacts": {
            "contract": str(DEFAULT_CONTRACT_OUT),
            "topk_survival_report": str(DEFAULT_SURVIVAL_REPORT_OUT),
            "readonly_api": str(DEFAULT_READONLY_API_OUT),
            "science_product_surface": str(DEFAULT_SURFACE_OUT),
        },
        "operator_next_actions": [
            "attach_top_k_candidate_refinement_rows",
            "run_pocketmd_lite_topk_survival_materializer",
            "review_local_min_contact_hbond_clash_uncertainty_summary",
            "regenerate_pm_release_gate_report",
        ],
        "acceptance_criteria": [
            "topk_survival_report.real_refinement_case_count > 0",
            "topk_survival_report.blockers == []",
            "science_product_surface.contract_pass == true",
            "science_product_surface.locked == false",
            "broad_all_atom_md_claim remains locked unless separately evidenced",
        ],
        "claim_boundary": (
            "This handoff prepares the bounded PocketMD Lite evidence path only. It is "
            "not an approval to claim broad MD/FEP readiness."
        ),
    }


def build_surface(
    *,
    contract: dict[str, Any],
    topk_survival_report: dict[str, Any],
    readonly_api: dict[str, Any],
    delivery_handoff: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    blockers = [
        "pocketmd_lite_topk_refinement_rows_required",
        "pocketmd_lite_survival_report_blocked",
        "pocketmd_lite_broad_all_atom_fep_claim_locked",
    ]
    return {
        "schema_version": SURFACE_SCHEMA_VERSION,
        **_metadata(
            repo_root=repo_root,
            reused_evidence=False,
            reuse_policy="pocketmd_lite_science_product_surface_from_contract_seed",
        ),
        "surface_id": "pocketmd_lite_science_product_surface",
        "science_surface_family": "pocketmd_lite",
        "surface_scope": "pocketmd_lite_top_k_refinement",
        "surface_kind": "science_product_surface",
        "product_capability_id": "pocketmd_lite_top_k_refinement",
        "status": "locked",
        "reason_code": "ERR_POCKETMD_LITE_PRODUCT_SURFACE_LOCKED",
        "contract_pass": False,
        "locked": True,
        "claim_locked": True,
        "product_surface_ready": False,
        "first_blocked_target": "top_k_refinement_operator_intake",
        "root_cause_tags": ["operator_refinement_rows_required"],
        "blockers": blockers,
        "required_receipts": [
            "top_k_candidate_refinement_rows",
            "local_min_survival_report",
            "contact_persistence_report",
            "h_bond_persistence_report",
            "clash_relief_report",
            "uncertainty_summary",
        ],
        "linked_artifacts": {
            "contract": str(DEFAULT_CONTRACT_OUT),
            "topk_survival_report": str(DEFAULT_SURVIVAL_REPORT_OUT),
            "readonly_api": str(DEFAULT_READONLY_API_OUT),
            "delivery_handoff": str(DEFAULT_HANDOFF_OUT),
        },
        "readiness_summary": {
            "contract_ready": bool(contract.get("contract_pass")),
            "readonly_api_ready": bool(readonly_api.get("contract_pass")),
            "handoff_ready": bool(delivery_handoff.get("contract_pass")),
            "real_refinement_case_count": int(
                topk_survival_report.get("real_refinement_case_count") or 0
            ),
            "top_k_candidate_count": int(topk_survival_report.get("top_k_candidate_count") or 0),
            "blocked_claim_count": len(contract.get("blocked_claims", [])),
        },
        "goal_roadmap_linkage": {
            "phase": "Phase 4",
            "roadmap_item": "PocketMD Lite science product surface",
            "bottleneck": "pocketmd_lite_science_product_surface_locked",
            "next_goal_actions": [
                "run_pocketmd_lite_topk_survival_materializer",
                "publish_pocketmd_lite_readonly_api",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_action_board",
            ],
        },
        "next_actions": [
            "attach_top_k_candidate_refinement_rows",
            "run_pocketmd_lite_topk_survival_materializer",
            "regenerate_pocketmd_lite_science_product_surface",
            "regenerate_pm_release_gate_report",
        ],
        "summary_line": (
            "PocketMD Lite science product surface: LOCKED | "
            "top-k refinement operator rows required"
        ),
        "claim_boundary": (
            "PocketMD Lite is exposed as a bounded science product surface for top-k "
            "local refinement evidence only. Broad all-atom MD, FEP, long-timescale "
            "dynamics, and de novo binding claims remain locked."
        ),
    }


def build_pocketmd_lite_artifacts(*, repo_root: Path = ROOT) -> dict[str, dict[str, Any]]:
    contract = build_contract(repo_root=repo_root)
    topk_survival_report = build_topk_survival_report(repo_root=repo_root)
    readonly_api = build_readonly_api(repo_root=repo_root)
    delivery_handoff = build_delivery_handoff(repo_root=repo_root)
    surface = build_surface(
        contract=contract,
        topk_survival_report=topk_survival_report,
        readonly_api=readonly_api,
        delivery_handoff=delivery_handoff,
        repo_root=repo_root,
    )
    return {
        "contract": contract,
        "topk_survival_report": topk_survival_report,
        "readonly_api": readonly_api,
        "delivery_handoff": delivery_handoff,
        "surface": surface,
    }


def write_pocketmd_lite_artifacts(
    *,
    repo_root: Path = ROOT,
    contract_out: Path = DEFAULT_CONTRACT_OUT,
    survival_report_out: Path = DEFAULT_SURVIVAL_REPORT_OUT,
    readonly_api_out: Path = DEFAULT_READONLY_API_OUT,
    handoff_out: Path = DEFAULT_HANDOFF_OUT,
    surface_out: Path = DEFAULT_SURFACE_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_pocketmd_lite_artifacts(repo_root=repo_root)
    outputs = {
        "contract": contract_out,
        "topk_survival_report": survival_report_out,
        "readonly_api": readonly_api_out,
        "delivery_handoff": handoff_out,
        "surface": surface_out,
    }
    for key, raw_path in outputs.items():
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(artifacts[key]), encoding="utf-8")
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-out", type=Path, default=DEFAULT_CONTRACT_OUT)
    parser.add_argument("--survival-report-out", type=Path, default=DEFAULT_SURVIVAL_REPORT_OUT)
    parser.add_argument("--readonly-api-out", type=Path, default=DEFAULT_READONLY_API_OUT)
    parser.add_argument("--handoff-out", type=Path, default=DEFAULT_HANDOFF_OUT)
    parser.add_argument("--surface-out", type=Path, default=DEFAULT_SURFACE_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts = write_pocketmd_lite_artifacts(
        repo_root=args.repo_root,
        contract_out=args.contract_out,
        survival_report_out=args.survival_report_out,
        readonly_api_out=args.readonly_api_out,
        handoff_out=args.handoff_out,
        surface_out=args.surface_out,
    )
    if args.json:
        print(_json_text({"artifacts": artifacts}), end="")
    else:
        surface = artifacts["surface"]
        print(
            "pocketmd-lite-product-surface: "
            f"{surface['status']} | "
            f"real_cases={surface['readiness_summary']['real_refinement_case_count']} | "
            f"bottleneck={surface['goal_roadmap_linkage']['bottleneck']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
