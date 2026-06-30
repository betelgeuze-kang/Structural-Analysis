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
from materialize_pocketmd_lite_topk_survival_report import build_phase4_exit_gate  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_CONTRACT_OUT = PRODUCTIZATION / "pocketmd_lite_contract.json"
DEFAULT_SURVIVAL_REPORT_OUT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_READONLY_API_OUT = PRODUCTIZATION / "pocketmd_lite_readonly_api.json"
DEFAULT_HANDOFF_OUT = PRODUCTIZATION / "pocketmd_lite_delivery_handoff.json"
DEFAULT_OPERATOR_INTAKE_OUT = PRODUCTIZATION / "pocketmd_lite_operator_intake_packet.json"
DEFAULT_OPERATOR_INTAKE_MD_OUT = DEFAULT_OPERATOR_INTAKE_OUT.with_suffix(".md")
DEFAULT_SURFACE_OUT = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"

CONTRACT_SCHEMA_VERSION = "pocketmd-lite-contract.v1"
SURVIVAL_REPORT_SCHEMA_VERSION = "pocketmd-lite-topk-survival-report.v1"
MATERIALIZER_SCHEMA_VERSION = "pocketmd-lite-topk-survival-materialization.v1"
READONLY_API_SCHEMA_VERSION = "pocketmd-lite-readonly-api.v1"
HANDOFF_SCHEMA_VERSION = "pocketmd-lite-delivery-handoff.v1"
OPERATOR_INTAKE_PACKET_SCHEMA_VERSION = "pocketmd-lite-operator-intake-packet.v1"
SURFACE_SCHEMA_VERSION = "pocketmd-lite-science-product-surface.v1"

POCKETMD_LITE_ROUTE = "/product/pocketmd-lite"
POCKETMD_LITE_HANDOFF_ROUTE = "/product/pocketmd-lite/handoff"
POCKETMD_LITE_OPERATOR_INTAKE_ROUTE = "/product/pocketmd-lite/operator-intake"
POCKETMD_LITE_MINIMUM_REFINEMENT_CASE_COUNT = 1
POCKETMD_LITE_MINIMUM_TOP_K_CANDIDATE_COUNT = 1


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_pocketmd_lite_product_surface.py"),
        Path("scripts/materialize_pocketmd_lite_topk_survival_report.py"),
    ]


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


def _materializer_contract() -> dict[str, Any]:
    return {
        "schema_version": MATERIALIZER_SCHEMA_VERSION,
        "script": "scripts/materialize_pocketmd_lite_topk_survival_report.py",
        "status": "ready_for_operator_intake",
        "input_contract": str(DEFAULT_CONTRACT_OUT),
        "required_intake_key": "cases",
        "outputs": {
            "topk_survival_report": str(DEFAULT_SURVIVAL_REPORT_OUT),
            "science_product_surface": str(DEFAULT_SURFACE_OUT),
        },
        "command": (
            "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
            "--intake <operator-pocketmd-lite-intake.json> "
            f"--contract {DEFAULT_CONTRACT_OUT} "
            f"--out-report {DEFAULT_SURVIVAL_REPORT_OUT} "
            f"--out-surface {DEFAULT_SURFACE_OUT} "
            "--fail-blocked"
        ),
    }


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


def _operator_gate_unblock_plan(
    *,
    required_case_fields: list[str],
    materializer_command: str,
) -> list[dict[str, Any]]:
    return [
        {
            "slot_id": "top_k_refinement_rows",
            "title": "Top-k candidate local refinement rows",
            "status": "operator_input_required",
            "unblocks_phase4_criteria": [
                "top_k_refinement_rows_present",
                "local_min_survival_materialized",
                "contact_persistence_materialized",
                "h_bond_persistence_materialized",
                "clash_relief_materialized",
                "uncertainty_summary_materialized",
                "report_blockers_resolved",
            ],
            "preserves_phase4_criteria": ["broad_all_atom_fep_claims_locked"],
            "minimum_evidence": {
                "real_refinement_case_count": POCKETMD_LITE_MINIMUM_REFINEMENT_CASE_COUNT,
                "top_k_candidate_count": POCKETMD_LITE_MINIMUM_TOP_K_CANDIDATE_COUNT,
                "candidate_scope": "upstream_ranked_top_k_candidates_only",
                "required_case_fields": required_case_fields,
                "receipt_fields": ["provenance_ref", "source_checksum"],
            },
            "materialization_steps": [
                "materialize_pocketmd_lite_topk_survival_report",
                "refresh_product_capabilities_surface",
                "refresh_goal_bottleneck_roadmap_surface",
            ],
            "materialization_command": materializer_command,
            "validation_command": materializer_command,
        }
    ]


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
        "materializer": _materializer_contract(),
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
    summary = {
        "local_min_survival_rate": None,
        "contact_persistence_rate_median": None,
        "h_bond_persistence_rate_median": None,
        "clash_relief_rate": None,
        "uncertainty_width_median": None,
        "top_k_candidate_count": 0,
        "real_refinement_case_count": 0,
        "blocker_count": len(blockers),
    }
    phase4_exit_gate = build_phase4_exit_gate(
        summary=summary,
        blockers=blockers,
        product_surface_ready=False,
        first_blocked_target="top_k_refinement_operator_intake",
    )
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
        "summary": summary,
        "materializer": _materializer_contract(),
        "required_metrics": [row["metric_id"] for row in _metric_contracts()],
        "phase4_exit_gate": phase4_exit_gate,
        "blockers": blockers,
        "next_actions": [
            "attach_top_k_candidate_refinement_rows",
            "run_pocketmd_lite_topk_survival_materializer",
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
        "read_model_ready": True,
        "route": POCKETMD_LITE_ROUTE,
        "read_model": {
            "route": POCKETMD_LITE_ROUTE,
            "alternate_routes": [
                POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
                POCKETMD_LITE_HANDOFF_ROUTE,
                "/product/capabilities",
            ],
            "artifact": str(DEFAULT_READONLY_API_OUT),
            "mutation_allowed": False,
        },
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
                "endpoint_id": "get_pocketmd_lite_operator_intake_packet",
                "method": "GET",
                "artifact": str(DEFAULT_OPERATOR_INTAKE_OUT),
            },
            {
                "endpoint_id": "get_pocketmd_lite_delivery_handoff",
                "method": "GET",
                "artifact": str(DEFAULT_HANDOFF_OUT),
            },
            {
                "endpoint_id": "list_operator_required_fields",
                "method": "GET",
                "artifact": str(DEFAULT_OPERATOR_INTAKE_OUT),
                "json_pointer": "/required_case_fields",
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
        "read_model_ready": True,
        "route": POCKETMD_LITE_HANDOFF_ROUTE,
        "read_model": {
            "route": POCKETMD_LITE_HANDOFF_ROUTE,
            "alternate_routes": [
                POCKETMD_LITE_ROUTE,
                POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
                "/product/capabilities",
            ],
            "artifact": str(DEFAULT_HANDOFF_OUT),
            "mutation_allowed": False,
        },
        "evidence_artifacts": {
            "contract": str(DEFAULT_CONTRACT_OUT),
            "topk_survival_report": str(DEFAULT_SURVIVAL_REPORT_OUT),
            "readonly_api": str(DEFAULT_READONLY_API_OUT),
            "operator_intake_packet": str(DEFAULT_OPERATOR_INTAKE_OUT),
            "operator_intake_packet_markdown": str(DEFAULT_OPERATOR_INTAKE_MD_OUT),
            "science_product_surface": str(DEFAULT_SURFACE_OUT),
        },
        "phase4_exit_gate_reference": {
            "source_artifact": str(DEFAULT_SURVIVAL_REPORT_OUT),
            "json_pointer": "/phase4_exit_gate",
            "required_status": "ready",
            "required_criteria": [
                "top_k_refinement_rows_present",
                "local_min_survival_materialized",
                "contact_persistence_materialized",
                "h_bond_persistence_materialized",
                "clash_relief_materialized",
                "uncertainty_summary_materialized",
                "report_blockers_resolved",
                "broad_all_atom_fep_claims_locked",
            ],
        },
        "operator_intake_reference": {
            "source_artifact": str(DEFAULT_OPERATOR_INTAKE_OUT),
            "markdown_artifact": str(DEFAULT_OPERATOR_INTAKE_MD_OUT),
            "route": POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
            "required_slot_id": "top_k_refinement_rows",
            "case_key": "cases",
        },
        "operator_next_actions": [
            "fill_pocketmd_lite_operator_intake_packet",
            "attach_top_k_candidate_refinement_rows",
            "run_pocketmd_lite_topk_survival_materializer",
            "review_local_min_contact_hbond_clash_uncertainty_summary",
            "regenerate_pm_release_gate_report",
        ],
        "acceptance_criteria": [
            "topk_survival_report.real_refinement_case_count > 0",
            "topk_survival_report.blockers == []",
            "topk_survival_report.phase4_exit_gate.status == ready",
            "science_product_surface.contract_pass == true",
            "science_product_surface.locked == false",
            "broad_all_atom_md_claim remains locked unless separately evidenced",
        ],
        "materializer": _materializer_contract(),
        "claim_boundary": (
            "This handoff prepares the bounded PocketMD Lite evidence path only. It is "
            "not an approval to claim broad MD/FEP readiness."
        ),
    }


def build_operator_intake_packet(
    *,
    contract: dict[str, Any],
    topk_survival_report: dict[str, Any],
    surface: dict[str, Any],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    operator_schema = contract.get("operator_intake_schema", {})
    required_case_fields = list(operator_schema.get("required_case_fields", []))
    template = dict(operator_schema.get("template", {}))
    blockers = list(topk_survival_report.get("blockers", []) or surface.get("blockers", []))
    first_blocked_target = str(
        surface.get("first_blocked_target") or "top_k_refinement_operator_intake"
    )
    materializer_command = (
        "python3 scripts/materialize_pocketmd_lite_topk_survival_report.py "
        f"--intake <operator-pocketmd-lite-intake.json> "
        f"--contract {DEFAULT_CONTRACT_OUT} "
        f"--out-report {DEFAULT_SURVIVAL_REPORT_OUT} "
        f"--out-surface {DEFAULT_SURFACE_OUT} --fail-blocked"
    )
    gate_unblock_plan = _operator_gate_unblock_plan(
        required_case_fields=required_case_fields,
        materializer_command=materializer_command,
    )
    return {
        "schema_version": OPERATOR_INTAKE_PACKET_SCHEMA_VERSION,
        **_metadata(
            repo_root=repo_root,
            reused_evidence=False,
            reuse_policy="pocketmd_lite_operator_intake_packet_generated_from_contract",
        ),
        "packet_id": "pocketmd_lite_operator_intake_packet",
        "status": "ready_for_operator_input",
        "reason_code": "PASS_INTAKE_PACKET",
        "contract_pass": True,
        "read_model_ready": True,
        "route": POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
        "read_model": {
            "route": POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
            "alternate_routes": [
                POCKETMD_LITE_ROUTE,
                POCKETMD_LITE_HANDOFF_ROUTE,
                "/product/capabilities",
            ],
            "artifact": str(DEFAULT_OPERATOR_INTAKE_OUT),
            "mutation_allowed": False,
        },
        "mutation_allowed": False,
        "owner_input_required": True,
        "product_surface_ready": False,
        "broad_all_atom_md_claim_safe": False,
        "broad_fep_claim_safe": False,
        "required_slot_count": 1,
        "required_case_fields": required_case_fields,
        "required_metrics": [row["metric_id"] for row in contract.get("reported_metrics", [])],
        "top_k_policy": contract.get("top_k_policy", {}),
        "input_slots": [
            {
                "slot_id": "top_k_refinement_rows",
                "status": "operator_input_required",
                "required": True,
                "case_key": operator_schema.get("case_key", "cases"),
                "required_case_fields": required_case_fields,
                "template": template,
                "owner_actions": [
                    "attach already-ranked top-k candidate refinement rows",
                    "fill local_min_survived as a boolean for every candidate",
                    "fill contact_persistence_rate and h_bond_persistence_rate as fractions",
                    "fill clash_count_before and clash_count_after as non-negative integers",
                    "fill uncertainty_interval with low, high, and unit",
                    "keep source_checksum and provenance_ref tied to local operator evidence",
                ],
            }
        ],
        "gate_unblock_plan": gate_unblock_plan,
        "gate_unblock_plan_count": len(gate_unblock_plan),
        "minimum_refinement_case_count": POCKETMD_LITE_MINIMUM_REFINEMENT_CASE_COUNT,
        "minimum_top_k_candidate_count": POCKETMD_LITE_MINIMUM_TOP_K_CANDIDATE_COUNT,
        "current_surface_status": {
            "artifact": str(DEFAULT_SURFACE_OUT),
            "status": str(surface.get("status") or ""),
            "first_blocked_target": first_blocked_target,
            "root_cause_tags": [str(row) for row in surface.get("root_cause_tags", [])],
            "blocker_count": len(blockers),
        },
        "materialization_sequence": [
            {
                "step_id": "fill_pocketmd_lite_operator_intake_packet",
                "command": "create <operator-pocketmd-lite-intake.json> from packet template",
                "produces": "<operator-pocketmd-lite-intake.json>",
            },
            {
                "step_id": "materialize_pocketmd_lite_topk_survival_report",
                "schema_version": MATERIALIZER_SCHEMA_VERSION,
                "command": materializer_command,
                "produces": str(DEFAULT_SURVIVAL_REPORT_OUT),
            },
            {
                "step_id": "refresh_product_capabilities_surface",
                "schema_version": "product-capabilities-surface.v1",
                "command": (
                    "python3 scripts/build_product_capabilities_surface.py "
                    "--out implementation/phase1/release_evidence/surface/"
                    "product_capabilities_surface.json"
                ),
                "produces": (
                    "implementation/phase1/release_evidence/surface/"
                    "product_capabilities_surface.json"
                ),
            },
            {
                "step_id": "refresh_goal_bottleneck_roadmap_surface",
                "schema_version": "goal-bottleneck-roadmap-surface.v1",
                "command": (
                    "python3 scripts/build_goal_bottleneck_roadmap_surface.py "
                    "--out implementation/phase1/release_evidence/productization/"
                    "goal_bottleneck_roadmap_surface.json"
                ),
                "produces": (
                    "implementation/phase1/release_evidence/productization/"
                    "goal_bottleneck_roadmap_surface.json"
                ),
            },
        ],
        "acceptance_criteria": [
            "pocketmd_lite_topk_survival_report.real_refinement_case_count > 0",
            "pocketmd_lite_topk_survival_report.blockers == []",
            "pocketmd_lite_topk_survival_report.phase4_exit_gate.status == ready",
            "pocketmd_lite_topk_survival_report.product_surface_ready == true",
            "pocketmd_lite_science_product_surface.locked == false",
            "broad_all_atom_md_claim and free_energy_perturbation_claim remain locked unless separately evidenced",
        ],
        "linked_artifacts": {
            "contract": str(DEFAULT_CONTRACT_OUT),
            "topk_survival_report": str(DEFAULT_SURVIVAL_REPORT_OUT),
            "readonly_api": str(DEFAULT_READONLY_API_OUT),
            "delivery_handoff": str(DEFAULT_HANDOFF_OUT),
            "science_product_surface": str(DEFAULT_SURFACE_OUT),
            "operator_intake_packet": str(DEFAULT_OPERATOR_INTAKE_OUT),
            "operator_intake_packet_markdown": str(DEFAULT_OPERATOR_INTAKE_MD_OUT),
        },
        "next_actions": [
            "fill_pocketmd_lite_operator_intake_packet",
            "attach_top_k_candidate_refinement_rows",
            "run_pocketmd_lite_topk_survival_materializer",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_roadmap_surface",
        ],
        "summary": {
            "required_slot_count": 1,
            "required_case_field_count": len(required_case_fields),
            "gate_unblock_plan_count": len(gate_unblock_plan),
            "minimum_refinement_case_count": POCKETMD_LITE_MINIMUM_REFINEMENT_CASE_COUNT,
            "minimum_top_k_candidate_count": POCKETMD_LITE_MINIMUM_TOP_K_CANDIDATE_COUNT,
            "current_blocker_count": len(blockers),
            "first_blocked_target": first_blocked_target,
            "product_surface_ready": False,
        },
        "summary_line": (
            "PocketMD Lite operator intake packet: READY | slots=1 | "
            f"first_blocked_target={first_blocked_target}"
        ),
        "claim_boundary": (
            "This packet is an owner-facing intake contract for bounded PocketMD Lite "
            "top-k refinement rows. It does not run MD, infer missing metrics, or "
            "unlock broad all-atom MD/FEP claims."
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
    phase4_exit_gate = topk_survival_report.get("phase4_exit_gate")
    if not isinstance(phase4_exit_gate, dict):
        report_summary = topk_survival_report.get("summary")
        phase4_exit_gate = build_phase4_exit_gate(
            summary=report_summary if isinstance(report_summary, dict) else {},
            blockers=[str(row) for row in topk_survival_report.get("blockers", [])],
            product_surface_ready=False,
            first_blocked_target="top_k_refinement_operator_intake",
        )
    operator_schema = contract.get("operator_intake_schema", {})
    required_case_fields = list(operator_schema.get("required_case_fields", []))
    gate_unblock_plan = _operator_gate_unblock_plan(
        required_case_fields=required_case_fields,
        materializer_command=_materializer_contract()["command"],
    )
    first_gate = gate_unblock_plan[0] if gate_unblock_plan else {}
    first_operator_evidence_gap = {
        "slot_priority": 1,
        "slot_id": str(first_gate.get("slot_id") or "top_k_refinement_rows"),
        "status": str(first_gate.get("status") or "operator_input_required"),
        "phase4_blocked": True,
        "blocked_phase4_criteria": [
            str(row) for row in first_gate.get("unblocks_phase4_criteria", [])
        ],
        "preserves_phase4_criteria": [
            str(row) for row in first_gate.get("preserves_phase4_criteria", [])
        ],
        "first_next_action": "attach top-k candidate refinement rows",
        "minimum_evidence": dict(first_gate.get("minimum_evidence") or {}),
        "materialization_steps": [
            str(row) for row in first_gate.get("materialization_steps", [])
        ],
        "materialization_command": str(first_gate.get("materialization_command") or ""),
        "validation_command": str(first_gate.get("validation_command") or ""),
    }
    operator_handoff_summary = {
        "route": POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
        "artifact": str(DEFAULT_OPERATOR_INTAKE_OUT),
        "first_blocker": "pocketmd_lite_topk_candidate_rows_missing",
        "first_blocked_target": "top_k_refinement_operator_intake",
        "first_next_action": first_operator_evidence_gap["first_next_action"],
        "required_slot_count": 1,
        "blocked_operator_slot_count": 1,
        "minimum_evidence": dict(first_operator_evidence_gap["minimum_evidence"]),
        "materialization_steps": list(
            first_operator_evidence_gap["materialization_steps"]
        ),
        "materialization_command": first_operator_evidence_gap[
            "materialization_command"
        ],
        "validation_command": first_operator_evidence_gap["validation_command"],
    }
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
        "first_blocker": "pocketmd_lite_topk_candidate_rows_missing",
        "root_cause_tags": ["operator_refinement_rows_required"],
        "blockers": blockers,
        "phase4_exit_gate": phase4_exit_gate,
        "operator_intake_route": POCKETMD_LITE_OPERATOR_INTAKE_ROUTE,
        "operator_intake_required_slot_count": 1,
        "operator_evidence_gap_count": 1,
        "first_operator_evidence_gap": first_operator_evidence_gap,
        "operator_evidence_gap_register": [first_operator_evidence_gap],
        "operator_gate_unblock_plan": gate_unblock_plan,
        "operator_handoff_summary": operator_handoff_summary,
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
            "operator_intake_packet": str(DEFAULT_OPERATOR_INTAKE_OUT),
            "operator_intake_packet_markdown": str(DEFAULT_OPERATOR_INTAKE_MD_OUT),
        },
        "materializer": _materializer_contract(),
        "readiness_summary": {
            "contract_ready": bool(contract.get("contract_pass")),
            "readonly_api_ready": bool(readonly_api.get("contract_pass")),
            "handoff_ready": bool(delivery_handoff.get("contract_pass")),
            "real_refinement_case_count": int(
                topk_survival_report.get("real_refinement_case_count") or 0
            ),
            "top_k_candidate_count": int(topk_survival_report.get("top_k_candidate_count") or 0),
            "blocked_claim_count": len(contract.get("blocked_claims", [])),
            "phase4_exit_gate_status": str(phase4_exit_gate.get("status") or ""),
            "phase4_failed_criterion_count": int(
                phase4_exit_gate.get("failed_criterion_count") or 0
            ),
            "phase4_failed_criteria": [
                str(row) for row in phase4_exit_gate.get("failed_criteria", [])
            ],
        },
        "goal_roadmap_linkage": {
            "phase": "Phase 4",
            "roadmap_item": "PocketMD Lite science product surface",
            "bottleneck": "pocketmd_lite_science_product_surface_locked",
            "next_goal_actions": [
                "fill_pocketmd_lite_operator_intake_packet",
                "run_pocketmd_lite_topk_survival_materializer",
                "publish_pocketmd_lite_readonly_api",
                "regenerate_product_capabilities_surface",
                "regenerate_goal_bottleneck_action_board",
            ],
        },
        "next_actions": [
            "fill_pocketmd_lite_operator_intake_packet",
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
    operator_intake_packet = build_operator_intake_packet(
        contract=contract,
        topk_survival_report=topk_survival_report,
        surface=surface,
        repo_root=repo_root,
    )
    return {
        "contract": contract,
        "topk_survival_report": topk_survival_report,
        "readonly_api": readonly_api,
        "delivery_handoff": delivery_handoff,
        "operator_intake_packet": operator_intake_packet,
        "surface": surface,
    }


def _operator_intake_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PocketMD Lite Operator Intake Packet",
        "",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `status`: `{payload['status']}`",
        f"- `product_surface_ready`: `{payload['product_surface_ready']}`",
        f"- `first_blocked_target`: `{payload['summary']['first_blocked_target']}`",
        f"- `claim_boundary`: {payload['claim_boundary']}",
        "",
        "| Slot | Status | Required Fields |",
        "|---|---|---|",
    ]
    for slot in payload["input_slots"]:
        lines.append(
            f"| `{slot['slot_id']}` | `{slot['status']}` | "
            f"`{', '.join(slot['required_case_fields'])}` |"
        )
    lines.extend(["", "## Gate Unblock Plan", "", "| Slot | Criteria | Minimum Evidence |"])
    lines.append("|---|---|---|")
    for row in payload["gate_unblock_plan"]:
        criteria = ", ".join(
            f"`{criterion}`" for criterion in row["unblocks_phase4_criteria"]
        )
        minimum = json.dumps(row["minimum_evidence"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| `{row['slot_id']}` | {criteria} | `{minimum}` |")
    lines.extend(["", "## Materialization Sequence", ""])
    for step in payload["materialization_sequence"]:
        lines.append(f"- `{step['step_id']}`: `{step['command']}`")
    lines.extend(["", "## Acceptance Criteria", ""])
    for criterion in payload["acceptance_criteria"]:
        lines.append(f"- `{criterion}`")
    lines.append("")
    return "\n".join(lines)


def write_pocketmd_lite_artifacts(
    *,
    repo_root: Path = ROOT,
    contract_out: Path = DEFAULT_CONTRACT_OUT,
    survival_report_out: Path = DEFAULT_SURVIVAL_REPORT_OUT,
    readonly_api_out: Path = DEFAULT_READONLY_API_OUT,
    handoff_out: Path = DEFAULT_HANDOFF_OUT,
    operator_intake_out: Path = DEFAULT_OPERATOR_INTAKE_OUT,
    operator_intake_md_out: Path = DEFAULT_OPERATOR_INTAKE_MD_OUT,
    surface_out: Path = DEFAULT_SURFACE_OUT,
) -> dict[str, dict[str, Any]]:
    artifacts = build_pocketmd_lite_artifacts(repo_root=repo_root)
    outputs = {
        "contract": contract_out,
        "topk_survival_report": survival_report_out,
        "readonly_api": readonly_api_out,
        "delivery_handoff": handoff_out,
        "operator_intake_packet": operator_intake_out,
        "surface": surface_out,
    }
    for key, raw_path in outputs.items():
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_text(artifacts[key]), encoding="utf-8")
    md_path = (
        operator_intake_md_out
        if operator_intake_md_out.is_absolute()
        else repo_root / operator_intake_md_out
    )
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(
        _operator_intake_markdown(artifacts["operator_intake_packet"]),
        encoding="utf-8",
    )
    return artifacts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-out", type=Path, default=DEFAULT_CONTRACT_OUT)
    parser.add_argument("--survival-report-out", type=Path, default=DEFAULT_SURVIVAL_REPORT_OUT)
    parser.add_argument("--readonly-api-out", type=Path, default=DEFAULT_READONLY_API_OUT)
    parser.add_argument("--handoff-out", type=Path, default=DEFAULT_HANDOFF_OUT)
    parser.add_argument("--operator-intake-out", type=Path, default=DEFAULT_OPERATOR_INTAKE_OUT)
    parser.add_argument("--operator-intake-md-out", type=Path, default=DEFAULT_OPERATOR_INTAKE_MD_OUT)
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
        operator_intake_out=args.operator_intake_out,
        operator_intake_md_out=args.operator_intake_md_out,
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
