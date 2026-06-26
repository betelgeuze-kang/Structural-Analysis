#!/usr/bin/env python3
"""Build the Open Benchmark Developer Preview readiness artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
for candidate in (SCRIPT_DIR, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_product_readiness_snapshot import (  # noqa: E402
    DEFAULT_OUT as PRODUCT_READINESS_SNAPSHOT,
    SCHEMA_VERSION as PRODUCT_SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
)
from release_evidence_metadata import engine_version, git_head, input_checksums  # noqa: E402
from structural_analysis.benchmark.acquisition import build_phase3_acquisition_plan  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "developer_preview_readiness.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_DATASET_LICENSE_MANIFEST = PRODUCTIZATION / "developer_preview_dataset_license_manifest.json"
DEFAULT_PHASE1_CORE_API_CONTRACT = PRODUCTIZATION / "phase1_core_api_contract_summary.json"
SCHEMA_VERSION = "developer-preview-readiness.v1"
FOUR_CATEGORIES = ("numerical", "benchmark", "software product", "future commercial")
PHASE3_BENCHMARK_LANES = (
    "analytic-small",
    "element-patch",
    "opensees-medium",
    "opensees-megatall",
    "buildingsmart-clean-ifc",
    "buildingsmart-dirty-ifc",
    "ifc-query-and-gui",
    "commercial-cross-solver",
    "large-model-performance",
)
REPO_GENERATED_SEED_LANES = (
    "analytic-small",
    "element-patch",
    "nonlinear-material-mesh",
)

INCLUDED_SCOPE = [
    "IFC/MGT/neutral JSON import for public or locally acquired benchmark models",
    "linear static, modal, buckling, and validated bounded nonlinear static paths",
    "residual, reaction, energy, provenance, and reproducibility audit reports",
    "Open benchmark scorecards and commercial-tool comparison imports",
    "local desktop/web GUI review workflow for benchmark evidence",
]
EXCLUDED_SCOPE = [
    "permit or code-compliance automation",
    "structural engineer replacement",
    "customer SLA or production support commitment",
    "multi-tenant SaaS, account, permission, or license-server operation",
    "customer shadow evidence as a Developer Preview blocker",
    "product/legal commercial license approval as a Developer Preview blocker",
    "30-run commercial CI streak or external approval receipts as Developer Preview blockers",
    (
        "AI/GNN/surrogate predictions as independent truth before deterministic "
        "reference solver, residual/Jacobian/Newton closure, and benchmark truth are fixed"
    ),
]
FREEZE_POLICY = {
    "new_feature_development": "frozen_until_developer_preview_baseline_is_clean",
    "ai_training": "frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed",
    "gpu_hip": "performance_track_after_cpu_reference_parity",
}
REUSE_POLICY = (
    "derived_readiness_judgment_from_product_snapshot_and_dataset_license_manifest; "
    "does_not_create_authoritative_closure_evidence"
)
INPUT_CHECKSUM_POLICY = (
    "product_snapshot_readiness_semantic_subset_excludes_self_referential_"
    "developer_preview_metadata"
)
SCOPE_BOUNDARY_README = Path("README.md")
SCOPE_BOUNDARY_REPORTS = (
    Path("docs/commercialization-gap-current-state.md"),
)
SCOPE_BOUNDARY_DOCS = (
    SCOPE_BOUNDARY_README,
    *SCOPE_BOUNDARY_REPORTS,
)
SCOPE_BOUNDARY_GUI = Path("src/App.tsx")
SCOPE_INCLUDED_ANCHORS = {
    "public_open_benchmark_import": (
        "public/open benchmark import",
        "공개/open benchmark import",
    ),
    "deterministic_analysis_reporting": (
        "deterministic analysis/reporting",
        "결정론적 해석·리포팅",
    ),
    "benchmark_scorecard": ("benchmark scorecard",),
    "local_gui_review": ("local GUI review",),
}
SCOPE_EXCLUDED_ANCHORS = {
    "permit_automation": ("permit automation", "인허가 자동화"),
    "engineer_replacement": ("engineer replacement", "기술사 대체"),
    "saas_account_license_server": ("SaaS/account/license server", "SaaS/accounts/license server"),
    "commercial_sla": ("commercial SLA",),
    "ai_gnn_truth_claim": ("AI/GNN truth", "AI/GNN/surrogate truth"),
}
FUTURE_COMMERCIAL_ANCHORS = {
    "customer_shadow": ("customer shadow",),
    "license_approval": ("license approval", "license/legal approval", "라이선스/법무 승인"),
    "commercial_sla": ("commercial SLA", "상용 SLA"),
    "ci_streak": ("30-run CI streak",),
    "external_approval_receipt": ("external approval receipt", "external approval receipts"),
}
FUTURE_COMMERCIAL_SCOPE_BLOCKERS = (
    "commercial_sla::production_support_commitment_missing",
    "license_server::operation_readiness_missing",
)


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_optional_text(repo_root: Path, path: Path) -> str:
    resolved = path if path.is_absolute() else repo_root / path
    try:
        return resolved.read_text(encoding="utf-8")
    except Exception:
        return ""


def _anchor_coverage(text: str, anchors: dict[str, tuple[str, ...]]) -> dict[str, bool]:
    lowered = text.lower()
    return {
        key: any(anchor.lower() in lowered for anchor in alternatives)
        for key, alternatives in anchors.items()
    }


def _scope_boundary_sync(repo_root: Path) -> dict[str, Any]:
    def surface_contract(path: Path) -> dict[str, Any]:
        text = _read_optional_text(repo_root, path)
        included = _anchor_coverage(text, SCOPE_INCLUDED_ANCHORS)
        excluded = _anchor_coverage(text, SCOPE_EXCLUDED_ANCHORS)
        future = _anchor_coverage(text, FUTURE_COMMERCIAL_ANCHORS)
        return {
            "present": bool(text),
            "included_scope_anchor_count": sum(included.values()),
            "included_scope_anchor_total": len(included),
            "excluded_scope_anchor_count": sum(excluded.values()),
            "excluded_scope_anchor_total": len(excluded),
            "future_commercial_boundary_anchor_count": sum(future.values()),
            "future_commercial_boundary_anchor_total": len(future),
            "contract_pass": bool(
                text and all(included.values()) and all(excluded.values()) and all(future.values())
            ),
            "included_scope_anchors": included,
            "excluded_scope_anchors": excluded,
            "future_commercial_boundary_anchors": future,
        }

    readme_surface = surface_contract(SCOPE_BOUNDARY_README)
    report_surfaces = {path.as_posix(): surface_contract(path) for path in SCOPE_BOUNDARY_REPORTS}
    doc_surfaces: dict[str, dict[str, Any]] = {
        SCOPE_BOUNDARY_README.as_posix(): readme_surface,
        **report_surfaces,
    }
    gui_text = _read_optional_text(repo_root, SCOPE_BOUNDARY_GUI)
    gui_contract = {
        "present": bool(gui_text),
        "consumes_scope_record": "getRecord(resource.data, 'scope')" in gui_text,
        "consumes_included_scope": "getArray(scope, 'included')" in gui_text,
        "consumes_excluded_scope": "getArray(scope, 'excluded')" in gui_text,
        "consumes_closure_visibility_record": (
            "getRecord(resource.data, 'gap_ledger_closure_requirement_visibility')"
            in gui_text
        ),
        "consumes_failed_closure_requirement_ids": (
            "getArray(closureVisibility, 'nonclosed_failed_closure_requirement_ids')"
            in gui_text
        ),
        "renders_scope_summary": "scope=${scopeSummary}" in gui_text,
        "renders_exclusion_summary": "excludes=${exclusionSummary}" in gui_text,
        "renders_closure_requirement_summary": "closure requirements=${closureRequirementSummary}" in gui_text,
        "renders_closure_visibility_boundary": "visibility only; no G1/G6/G7 closure" in gui_text,
        "future_commercial_boundary_present": all(
            any(anchor in gui_text for anchor in alternatives)
            for alternatives in FUTURE_COMMERCIAL_ANCHORS.values()
        ),
    }
    gui_contract["contract_pass"] = all(gui_contract.values())
    contract_pass = all(row["contract_pass"] for row in doc_surfaces.values()) and bool(
        gui_contract["contract_pass"]
    )
    return {
        "status": "ready" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "surface_groups": {
            "readme": {
                "path": SCOPE_BOUNDARY_README.as_posix(),
                **readme_surface,
            },
            "reports": {
                "surface_count": len(report_surfaces),
                "contract_pass_count": sum(1 for row in report_surfaces.values() if row["contract_pass"]),
                "surfaces": report_surfaces,
            },
            "gui": {
                "path": SCOPE_BOUNDARY_GUI.as_posix(),
                **gui_contract,
            },
        },
        "doc_surfaces": doc_surfaces,
        "gui_surface": {
            "path": SCOPE_BOUNDARY_GUI.as_posix(),
            **gui_contract,
        },
        "claim_boundary": (
            "This receipt checks that Developer Preview scope and exclusions remain visible "
            "in README, report surfaces, and that the GUI consumes the generated readiness "
            "scope instead of relying only on hardcoded Commercial Release wording."
        ),
    }


def _gap_ledger_closure_requirement_visibility(
    product_snapshot: dict[str, Any],
) -> dict[str, Any]:
    components = _as_dict(product_snapshot.get("components"))
    commercial_gap = _as_dict(components.get("commercial_gap_ledger_status"))
    audit = _as_dict(components.get("gap_ledger_evidence_audit"))
    split_summary = _as_dict(audit.get("ledger_split_summary"))
    ledgers: dict[str, dict[str, Any]] = {}
    total_failed_ids: list[str] = []
    total_requirement_count = 0
    total_pass_count = 0
    total_fail_count = 0
    total_nonclosed_failed_rows = 0
    for ledger_name in ("commercial_solver", "ai_engine"):
        row = _as_dict(split_summary.get(ledger_name))
        failed_ids = [
            str(item)
            for item in _as_list(row.get("nonclosed_failed_closure_requirement_ids"))
            if str(item)
        ]
        requirement_count = _as_int(row.get("closure_requirement_count"))
        pass_count = _as_int(row.get("closure_requirement_pass_count"))
        fail_count = _as_int(row.get("closure_requirement_fail_count"))
        nonclosed_failed_rows = _as_int(
            row.get("nonclosed_rows_with_failed_closure_requirements_count")
        )
        total_requirement_count += requirement_count
        total_pass_count += pass_count
        total_fail_count += fail_count
        total_nonclosed_failed_rows += nonclosed_failed_rows
        total_failed_ids.extend(failed_ids)
        ledgers[ledger_name] = {
            "row_count": _as_int(row.get("row_count")),
            "nonclosed_row_count": _as_int(row.get("nonclosed_row_count")),
            "closure_requirement_count": requirement_count,
            "closure_requirement_pass_count": pass_count,
            "closure_requirement_fail_count": fail_count,
            "nonclosed_rows_with_failed_closure_requirements_count": nonclosed_failed_rows,
            "nonclosed_failed_closure_requirement_ids": failed_ids,
        }
    return {
        "source": "product_readiness_snapshot.components.gap_ledger_evidence_audit",
        "source_status": str(audit.get("status", "missing")),
        "source_contract_pass": bool(audit.get("contract_pass") is True),
        "source_full_gap_ledger_ready": bool(audit.get("full_gap_ledger_ready") is True),
        "ai_engine_guardrail_rows_ready": bool(
            commercial_gap.get("ai_engine_guardrail_rows_ready") is True
        ),
        "autonomous_ai_engine_claim_ready": bool(
            commercial_gap.get("autonomous_ai_engine_claim_ready") is True
        ),
        "autonomous_ai_engine_claim_blockers": [
            str(item)
            for item in _as_list(commercial_gap.get("autonomous_ai_engine_claim_blockers"))
            if str(item)
        ],
        "closure_requirement_count": total_requirement_count,
        "closure_requirement_pass_count": total_pass_count,
        "closure_requirement_fail_count": total_fail_count,
        "nonclosed_rows_with_failed_closure_requirements_count": total_nonclosed_failed_rows,
        "nonclosed_failed_closure_requirement_ids": sorted(dict.fromkeys(total_failed_ids)),
        "ledgers": ledgers,
        "claim_boundary": (
            "This is a visibility summary for existing gap-ledger closure requirements. "
            "It does not add Developer Preview blockers, close G1/G6/G7, create external "
            "receipts, promote commercial readiness, or promote autonomous AI engine claims."
        ),
    }


def _category_for_blocker(blocker: str) -> str:
    text = blocker.lower()
    if (
        text.startswith("customer_shadow::")
        or text.startswith("license::")
        or text.startswith("ci_streak::")
        or text.startswith("self_hosted_runner::")
        or text.startswith("external_benchmark::")
        or text.startswith("pm_release::github_sync::")
        or text.startswith("pm_release::security::license")
        or "license_status_not_configured" in text
        or "external_receipt" in text
        or "external_submission" in text
        or "approval_receipt" in text
        or "commercial_sla" in text
        or "license_server" in text
        or "30_consecutive" in text
        or "github_actions_30" in text
    ):
        return "future commercial"
    if (
        text.startswith("g1")
        or "::g1" in text
        or "residual" in text
        or "jacobian" in text
        or "newton" in text
        or "full_load" in text
        or "full_mesh" in text
        or "fallback" in text
        or "load_scale" in text
        or "material_newton" in text
    ):
        return "numerical"
    if (
        text.startswith("fresh_full_validation::")
        or text.startswith("fresh_full_validation:")
        or "fresh_validation" in text
        or "benchmark_factory" in text
        or "analytic" in text
        or "patch" in text
        or "opensees" in text
        or "ifc" in text
        or "dataset_license" in text
        or "corpus" in text
    ):
        return "benchmark"
    return "software product"


def _group_blockers(blockers: list[str]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[str]] = {category: [] for category in FOUR_CATEGORIES}
    for blocker in blockers:
        grouped[_category_for_blocker(blocker)].append(blocker)
    return {
        category: {
            "blocked": bool(items),
            "blocker_count": len(items),
            "blockers": items,
        }
        for category, items in grouped.items()
    }


def _dataset_license_manifest(repo_root: Path, manifest_path: Path) -> dict[str, Any]:
    payload = _load_json(repo_root, manifest_path)
    if payload:
        return payload
    return {
        "schema_version": "developer-preview-dataset-license-manifest.v1",
        "status": "missing",
        "contract_pass": False,
        "blockers": ["dataset_license_manifest_missing"],
        "source_path": str(manifest_path),
    }


def _manifest_ready(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        and str(payload.get("status", "")).lower() in {"ready", "review"}
        and not payload.get("blockers")
    )


def _source_file_rows(repo_root: Path, paths: list[Path]) -> list[dict[str, Any]]:
    checksums = input_checksums(paths, repo_root=repo_root)
    rows: list[dict[str, Any]] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else repo_root / raw_path
        row: dict[str, Any] = {
            "path": raw_path.as_posix(),
            "present": path.exists(),
            "checksum": checksums.get(str(raw_path), "missing"),
        }
        if path.exists() and path.is_file():
            row["size_bytes"] = path.stat().st_size
        rows.append(row)
    return rows


def _input_artifact_summary(
    *,
    path: Path,
    payload: dict[str, Any],
    checksums: dict[str, str],
) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "present": bool(payload),
        "schema_version": str(payload.get("schema_version", "missing")),
        "status": str(payload.get("status", "missing")),
        "source_commit_sha": payload.get("source_commit_sha"),
        "input_checksum": checksums.get(str(path), "missing"),
    }


def _stable_payload_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _product_snapshot_readiness_input(payload: dict[str, Any]) -> dict[str, Any]:
    state_consistency = _as_dict(payload.get("state_consistency"))
    worktree = _as_dict(state_consistency.get("worktree"))
    components = _as_dict(payload.get("components"))
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "schema_valid": payload.get("schema_valid"),
        "evidence_fresh": payload.get("evidence_fresh"),
        "release_ready": payload.get("release_ready"),
        "blockers": payload.get("blockers", []),
        "root_blockers": _as_dict(payload.get("root_blockers")),
        "components": {
            "fresh_full_validation": _as_dict(components.get("fresh_full_validation")),
            "g1": _as_dict(components.get("g1")),
        },
        "phase3_release_control_cleanup_plan": _as_dict(
            worktree.get("phase3_release_control_cleanup_plan")
        ),
    }


def _developer_preview_input_checksums(
    *,
    repo_root: Path,
    product_snapshot_path: Path,
    product_snapshot: dict[str, Any],
    dataset_license_manifest_path: Path,
    phase1_core_api_contract_path: Path,
) -> dict[str, str]:
    dataset_checksums = input_checksums(
        [dataset_license_manifest_path],
        repo_root=repo_root,
    )
    phase1_checksums = input_checksums(
        [phase1_core_api_contract_path],
        repo_root=repo_root,
    )
    product_checksum = (
        _stable_payload_sha256(_product_snapshot_readiness_input(product_snapshot))
        if product_snapshot
        else "missing"
    )
    return dict(
        sorted(
            {
                str(product_snapshot_path): product_checksum,
                str(dataset_license_manifest_path): dataset_checksums.get(
                    str(dataset_license_manifest_path),
                    "missing",
                ),
                str(phase1_core_api_contract_path): phase1_checksums.get(
                    str(phase1_core_api_contract_path),
                    "missing",
                ),
            }.items()
        )
    )


def _acquisition_policy_for_lanes(acquisition_plan: dict[str, Any], lanes: list[str]) -> dict[str, Any]:
    wanted = set(lanes)
    rows = [
        row
        for row in acquisition_plan.get("rows", [])
        if isinstance(row, dict) and wanted.intersection(str(lane) for lane in row.get("lanes", []))
    ]
    blockers = sorted(
        {
            str(blocker)
            for row in rows
            for blocker in row.get("blockers", [])
            if str(blocker)
        }
    )
    return {
        "source_count": len(rows),
        "source_ids": [str(row.get("source_id", "")) for row in rows],
        "ready_for_phase3_quantity_credit": False,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "blockers": blockers,
        "rows": rows,
    }


def build_developer_preview_readiness(
    *,
    repo_root: Path = ROOT,
    product_snapshot_path: Path = PRODUCT_READINESS_SNAPSHOT,
    dataset_license_manifest_path: Path = DEFAULT_DATASET_LICENSE_MANIFEST,
    phase1_core_api_contract_path: Path = DEFAULT_PHASE1_CORE_API_CONTRACT,
    source_commit_sha: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    product_snapshot = _load_json(repo_root, product_snapshot_path)
    if not product_snapshot:
        product_snapshot = build_snapshot(repo_root=repo_root, source_commit_sha=source_commit_sha)
    manifest = _dataset_license_manifest(repo_root, dataset_license_manifest_path)
    phase1_core_api = _load_json(repo_root, phase1_core_api_contract_path)
    blockers = [
        *[str(item) for item in product_snapshot.get("blockers", []) if str(item)],
        *FUTURE_COMMERCIAL_SCOPE_BLOCKERS,
    ]
    if not _manifest_ready(manifest):
        blockers.extend(str(item) for item in manifest.get("blockers", []) if str(item))
        if not manifest.get("blockers"):
            blockers.append("dataset_license_manifest:not_ready")
    categories = _group_blockers(sorted(dict.fromkeys(blockers)))
    developer_blockers = [
        blocker
        for category in ("numerical", "benchmark", "software product")
        for blocker in categories[category]["blockers"]
    ]
    future_commercial_blockers = categories["future commercial"]["blockers"]
    evidence_fresh = bool(product_snapshot.get("evidence_fresh"))
    schema_valid = bool(product_snapshot.get("schema_valid"))
    developer_preview_ready = bool(schema_valid and evidence_fresh and not developer_blockers)
    product_state = _as_dict(product_snapshot.get("state_consistency"))
    product_worktree = _as_dict(product_state.get("worktree"))
    product_components = _as_dict(product_snapshot.get("components"))
    fresh_full_validation_component = _as_dict(
        product_components.get("fresh_full_validation")
    )
    g1_component = _as_dict(product_components.get("g1"))
    scope_boundary_sync = _scope_boundary_sync(repo_root)
    closure_requirement_visibility = _gap_ledger_closure_requirement_visibility(
        product_snapshot
    )
    input_checksum_map = _developer_preview_input_checksums(
        repo_root=repo_root,
        product_snapshot_path=product_snapshot_path,
        product_snapshot=product_snapshot,
        dataset_license_manifest_path=dataset_license_manifest_path,
        phase1_core_api_contract_path=phase1_core_api_contract_path,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha or git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "input_checksums": input_checksum_map,
        "reused_evidence": False,
        "reuse_policy": REUSE_POLICY,
        "input_checksum_policy": INPUT_CHECKSUM_POLICY,
        "input_artifacts": {
            "product_readiness_snapshot": _input_artifact_summary(
                path=product_snapshot_path,
                payload=product_snapshot,
                checksums=input_checksum_map,
            ),
            "dataset_license_manifest": _input_artifact_summary(
                path=dataset_license_manifest_path,
                payload=manifest,
                checksums=input_checksum_map,
            ),
            "phase1_core_api_contract": _input_artifact_summary(
                path=phase1_core_api_contract_path,
                payload=phase1_core_api,
                checksums=input_checksum_map,
            ),
        },
        "product_snapshot_schema_version": product_snapshot.get("schema_version", PRODUCT_SNAPSHOT_SCHEMA_VERSION),
        "product_snapshot_status": product_snapshot.get("status", "missing"),
        "developer_preview_ready": developer_preview_ready,
        "commercial_release_ready": bool(product_snapshot.get("release_ready")),
        "status": "ready" if developer_preview_ready else "blocked",
        "reason_code": "PASS" if developer_preview_ready else "ERR_DEVELOPER_PREVIEW_BLOCKED",
        "blocker_count": len(developer_blockers),
        "blockers": developer_blockers,
        "future_commercial_blocker_count": len(future_commercial_blockers),
        "future_commercial_blockers": future_commercial_blockers,
        "categories": categories,
        "scope": {
            "product_name": "Structural Analysis Open Benchmark Developer Preview",
            "included": INCLUDED_SCOPE,
            "excluded": EXCLUDED_SCOPE,
            "freeze_policy": FREEZE_POLICY,
        },
        "dataset_license_manifest": {
            "path": str(dataset_license_manifest_path),
            "status": str(manifest.get("status", "missing")),
            "contract_pass": bool(manifest.get("contract_pass")),
            "blockers": manifest.get("blockers", []),
            "dataset_count": manifest.get("dataset_count", 0),
        },
        "root_blocker_evidence": {
            "product_snapshot_root_blockers": _as_dict(product_snapshot.get("root_blockers")),
            "phase3_release_control_cleanup_plan": _as_dict(
                product_worktree.get("phase3_release_control_cleanup_plan")
            ),
            "g1": g1_component,
            "fresh_full_validation": fresh_full_validation_component,
        },
        "gap_ledger_closure_requirement_visibility": closure_requirement_visibility,
        "scope_boundary_sync": scope_boundary_sync,
        "claim_boundary": (
            "Developer Preview is an open benchmark workstation preview, not a commercial "
            "structural solver beta. Customer shadow, commercial license/legal approval, "
            "license-server operation, commercial SLA, 30-run CI streak, and external "
            "approval receipts remain visible as future Commercial Release blockers. "
            "Remote GitHub sync/push approval is a release-publication handoff and does "
            "not block the local Developer Preview evidence bar. "
            "AI/GNN/surrogate truth claims stay frozen until the deterministic reference "
            "solver, residual/Jacobian/Newton closure, and benchmark truth are fixed."
        ),
        "artifacts": {
            "product_readiness_snapshot": str(product_snapshot_path),
            "dataset_license_manifest": str(dataset_license_manifest_path),
            "phase1_core_api_contract": str(phase1_core_api_contract_path),
        },
    }


def build_dataset_license_manifest(*, repo_root: Path = ROOT) -> dict[str, Any]:
    phase3_acquisition_plan = build_phase3_acquisition_plan()
    analytic_source_files = [
        Path("implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_manifest.json"),
        Path("src/structural_analysis/benchmark/factory.py"),
        Path("src/structural_analysis/benchmark/cli.py"),
        Path("scripts/build_phase3_benchmark_factory_artifacts.py"),
    ]
    opensees_source_files = [
        Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl"),
        Path("implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl"),
        Path("implementation/phase1/opensees_topology_report.json"),
        Path("implementation/phase1/release_evidence/productization/phase3_opensees_medium_source_license_receipt.json"),
        Path("implementation/phase1/release_evidence/productization/phase4_commercial_comparison_import_template.json"),
        Path("implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_contract.json"),
        Path("implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_ingest_validator.json"),
        Path("src/structural_analysis/benchmark/acquisition.py"),
        Path("scripts/build_phase3_opensees_source_license_receipt.py"),
        Path("scripts/build_phase4_commercial_comparison_import_template.py"),
        Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
        Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
    ]
    analytic_source_file_rows = _source_file_rows(repo_root, analytic_source_files)
    opensees_source_file_rows = _source_file_rows(repo_root, opensees_source_files)
    sources = [
        {
            "source_id": "analytic-small",
            "truth_class": "analytic_truth",
            "license": "repo_generated",
            "redistribution_allowed": True,
            "commercial_use_allowed": True,
            "developer_preview_bundle_policy": "repo_generated_cases_may_be_bundled",
            "checksum_status": "complete_repo_generated_seed_manifest_and_factory_sources",
            "source_checksum_policy": (
                "Repo-generated analytic/component/material-mesh seed cases carry per-case "
                "checksums in the Phase 3 seed manifest and source-file checksums for the "
                "generator path."
            ),
            "source_files": analytic_source_file_rows,
            "expected_outputs_status": "attached_for_seed_cases",
            "selected_benchmark_lanes": list(REPO_GENERATED_SEED_LANES),
            "status": "planned",
        },
        {
            "source_id": "opensees-megatall",
            "truth_class": "independent_reference",
            "license": "user_acquired_review_required",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "developer_preview_bundle_policy": "not_bundled_user_acquisition_required",
            "checksum_status": "local_medium_candidate_checksums_attached_authoritative_source_pending",
            "source_checksum_policy": (
                "Local OpenSees medium candidate files are checksummed for parser/topology "
                "work only. Authoritative upstream source URL, license text, Mega-Tall "
                "acquisition, and reference-output checksums remain pending."
            ),
            "source_files": opensees_source_file_rows,
            "phase3_acquisition_policy": _acquisition_policy_for_lanes(
                phase3_acquisition_plan,
                ["opensees-medium", "opensees-megatall", "large-model-performance"],
            ),
            "supporting_receipt": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_opensees_medium_source_license_receipt.json"
            ),
            "expected_outputs_status": "missing_for_phase3_reference_comparison",
            "selected_benchmark_lanes": ["opensees-medium", "opensees-megatall", "large-model-performance"],
            "status": "acquisition_script_required",
        },
        {
            "source_id": "buildingsmart-ifc-samples",
            "truth_class": "geometry_and_import_truth",
            "license": "upstream_license_review_required",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "developer_preview_bundle_policy": "not_bundled_until_upstream_license_review",
            "checksum_status": "pending_not_bundled_upstream_files",
            "source_checksum_policy": (
                "Store only upstream identity, acquisition instructions, and checksums after "
                "license review; do not bundle sample IFC files before review."
            ),
            "source_files": [],
            "phase3_acquisition_policy": _acquisition_policy_for_lanes(
                phase3_acquisition_plan,
                ["buildingsmart-clean-ifc", "buildingsmart-dirty-ifc"],
            ),
            "supporting_receipt": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_source_license_receipt.json"
            ),
            "acquisition_receipt": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_buildingsmart_ifc_acquisition_receipt.json"
            ),
            "dirty_acquisition_receipt": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"
            ),
            "import_health_execution_receipt": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_import_health_execution_receipt.json"
            ),
            "expected_outputs_status": "authored_import_health_and_negative_contracts_pending_execution",
            "selected_benchmark_lanes": ["buildingsmart-clean-ifc", "buildingsmart-dirty-ifc"],
            "status": "manifest_only_until_license_review",
        },
        {
            "source_id": "ifc-query-and-gui-public-corpus",
            "truth_class": "query_and_gui_task_truth",
            "license": "per_file_upstream_license_review_required",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "developer_preview_bundle_policy": "not_bundled_until_per_file_license_review",
            "checksum_status": "pending_not_bundled_query_task_files",
            "source_checksum_policy": (
                "Record per-file source identity, license review, checksums, and expected "
                "query answers before any IFC query/GUI task corpus can count toward Phase 3."
            ),
            "source_files": [],
            "phase3_acquisition_policy": _acquisition_policy_for_lanes(
                phase3_acquisition_plan,
                ["ifc-query-and-gui"],
            ),
            "supporting_receipt": (
                "implementation/phase1/release_evidence/productization/"
                "phase3_ifc_source_license_receipt.json"
            ),
            "expected_outputs_status": "missing_query_answers_and_gui_task_expectations",
            "selected_benchmark_lanes": ["ifc-query-and-gui"],
            "status": "manifest_only_until_per_file_license_review",
        },
        {
            "source_id": "commercial-cross-solver-imports",
            "truth_class": "comparison_reference",
            "license": "operator_supplied_not_bundled",
            "redistribution_allowed": False,
            "commercial_use_allowed": False,
            "developer_preview_bundle_policy": "not_bundled_operator_attachment_required",
            "checksum_status": "pending_operator_supplied_attachment",
            "source_checksum_policy": (
                "Record checksums only after an operator attaches local commercial-tool "
                "exports; never treat templates or proxy rows as bundled reference data."
            ),
            "source_files": [],
            "import_template": (
                "implementation/phase1/release_evidence/productization/"
                "phase4_commercial_comparison_import_template.json"
            ),
            "operator_reference_contract": (
                "implementation/phase1/release_evidence/productization/"
                "phase4_commercial_operator_reference_contract.json"
            ),
            "operator_reference_ingest_validator": (
                "implementation/phase1/release_evidence/productization/"
                "phase4_commercial_operator_reference_ingest_validator.json"
            ),
            "phase3_acquisition_policy": _acquisition_policy_for_lanes(
                phase3_acquisition_plan,
                ["commercial-cross-solver"],
            ),
            "expected_outputs_status": (
                "authored_import_template_and_operator_contract_pending_reference_outputs"
            ),
            "selected_benchmark_lanes": ["commercial-cross-solver"],
            "status": "template_and_contract_only",
        },
    ]
    checksum_status_counts: dict[str, int] = {}
    for row in sources:
        status = str(row["checksum_status"])
        checksum_status_counts[status] = checksum_status_counts.get(status, 0) + 1
    covered_lanes = sorted({lane for row in sources for lane in row["selected_benchmark_lanes"]})
    repo_generated_source_ids = [
        str(row["source_id"])
        for row in sources
        if row["developer_preview_bundle_policy"] == "repo_generated_cases_may_be_bundled"
    ]
    non_bundled_source_ids = [
        str(row["source_id"])
        for row in sources
        if row["developer_preview_bundle_policy"] != "repo_generated_cases_may_be_bundled"
    ]
    authoritative_checksum_complete_source_ids = [
        str(row["source_id"])
        for row in sources
        if str(row["checksum_status"]).startswith("complete_")
    ]
    authoritative_checksum_pending_source_ids = [
        str(row["source_id"])
        for row in sources
        if row["source_id"] not in authoritative_checksum_complete_source_ids
    ]
    expected_outputs_attached_source_ids = [
        str(row["source_id"])
        for row in sources
        if str(row["expected_outputs_status"]).startswith("attached_")
    ]
    expected_outputs_pending_source_ids = [
        str(row["source_id"])
        for row in sources
        if row["source_id"] not in expected_outputs_attached_source_ids
    ]
    redistribution_allowed_source_ids = [
        str(row["source_id"]) for row in sources if row["redistribution_allowed"] is True
    ]
    redistribution_pending_source_ids = [
        str(row["source_id"]) for row in sources if row["redistribution_allowed"] is not True
    ]
    required_phase3_lanes = set(PHASE3_BENCHMARK_LANES)
    covered_lane_set = set(covered_lanes)
    phase3_lane_coverage_contract_pass = required_phase3_lanes.issubset(covered_lane_set)
    extra_seed_lanes = sorted(covered_lane_set.difference(required_phase3_lanes))
    repo_generated_seed_contract_pass = bool(
        phase3_lane_coverage_contract_pass
        and repo_generated_source_ids
        and sorted(repo_generated_source_ids) == sorted(redistribution_allowed_source_ids)
        and set(repo_generated_source_ids).issubset(authoritative_checksum_complete_source_ids)
        and set(repo_generated_source_ids).issubset(expected_outputs_attached_source_ids)
    )
    external_corpus_blockers = [
        "phase3_external_corpus:authoritative_source_checksums_pending="
        f"{len(authoritative_checksum_pending_source_ids)}",
        "phase3_external_corpus:license_or_redistribution_review_pending",
        "phase3_external_corpus:expected_outputs_pending",
    ]
    manifest_policy_contract = {
        "status": "ready",
        "contract_pass": True,
        "policy_fixed": True,
        "phase3_lane_coverage_contract_pass": phase3_lane_coverage_contract_pass,
        "required_phase3_corpus_lanes": sorted(PHASE3_BENCHMARK_LANES),
        "additional_repo_generated_seed_lanes": extra_seed_lanes,
        "developer_preview_seed_contract": {
            "status": "ready" if repo_generated_seed_contract_pass else "blocked",
            "contract_pass": repo_generated_seed_contract_pass,
            "bundle_eligible_source_ids": repo_generated_source_ids,
            "required_checks": [
                "repo_generated_license",
                "source_checksums",
                "per_case_seed_checksums",
                "expected_outputs_attached",
                "non_bundled_external_sources_visible",
            ],
        },
        "repo_generated_bundle_source_ids": repo_generated_source_ids,
        "non_bundled_source_ids": non_bundled_source_ids,
        "redistribution_allowed_source_ids": redistribution_allowed_source_ids,
        "redistribution_pending_source_ids": redistribution_pending_source_ids,
        "authoritative_checksum_complete_source_ids": authoritative_checksum_complete_source_ids,
        "authoritative_checksum_pending_source_ids": authoritative_checksum_pending_source_ids,
        "expected_outputs_attached_source_ids": expected_outputs_attached_source_ids,
        "expected_outputs_pending_source_ids": expected_outputs_pending_source_ids,
        "pending_counts": {
            "authoritative_source_checksums_pending": len(
                authoritative_checksum_pending_source_ids
            ),
            "license_or_redistribution_pending": len(redistribution_pending_source_ids),
            "expected_outputs_pending": len(expected_outputs_pending_source_ids),
        },
        "claim_boundary": (
            "The Developer Preview dataset/license manifest is fixed for the bundled "
            "repo-generated seed corpus. External OpenSees, buildingSMART, IFC query, "
            "and commercial/operator sources remain non-bundled until authoritative "
            "checksum, license, and expected-output evidence exists."
        ),
    }
    phase3_external_corpus_readiness = {
        "status": "blocked",
        "contract_pass": False,
        "blockers": external_corpus_blockers,
        "authoritative_checksum_pending_source_ids": authoritative_checksum_pending_source_ids,
        "redistribution_pending_source_ids": redistribution_pending_source_ids,
        "expected_outputs_pending_source_ids": expected_outputs_pending_source_ids,
        "claim_boundary": (
            "These blockers prevent full Phase 3 corpus quantity credit and Developer "
            "Preview RC final-gate promotion, but they do not block the seed-only "
            "dataset/license manifest deliverable."
        ),
    }
    blockers = [] if repo_generated_seed_contract_pass else [
        "dataset_license_manifest:repo_generated_seed_contract_not_ready"
    ]
    return {
        "schema_version": "developer-preview-dataset-license-manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": git_head(repo_root),
        "engine_version": engine_version(repo_root),
        "input_checksums": input_checksums(
            [
                Path("implementation/phase1/open_data/midas/midas_native_corpus_manifest.json"),
                Path("implementation/phase1/real_project_corpus_seed_manifest.json"),
                Path("implementation/phase1/release_evidence/productization/phase3_benchmark_acquisition_plan.json"),
                Path("implementation/phase1/release_evidence/productization/phase3_buildingsmart_ifc_acquisition_receipt.json"),
                Path("implementation/phase1/release_evidence/productization/phase3_buildingsmart_dirty_ifc_acquisition_receipt.json"),
                Path("implementation/phase1/release_evidence/productization/phase3_ifc_source_license_receipt.json"),
                Path("implementation/phase1/release_evidence/productization/phase3_ifc_import_health_execution_receipt.json"),
                Path("implementation/phase1/release_evidence/productization/phase4_commercial_comparison_import_template.json"),
                Path("implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_contract.json"),
                Path("implementation/phase1/release_evidence/productization/phase4_commercial_operator_reference_ingest_validator.json"),
                Path("src/structural_analysis/benchmark/acquisition.py"),
                Path("scripts/build_phase3_benchmark_acquisition_artifacts.py"),
                Path("scripts/build_phase3_buildingsmart_ifc_acquisition_receipt.py"),
                Path("scripts/build_phase3_buildingsmart_dirty_ifc_acquisition_receipt.py"),
                Path("scripts/build_phase3_ifc_source_license_receipt.py"),
                Path("scripts/build_phase3_ifc_import_health_execution_receipt.py"),
                Path("scripts/build_phase4_commercial_comparison_import_template.py"),
                Path("scripts/build_phase4_commercial_operator_reference_contract.py"),
                Path("scripts/build_phase4_commercial_operator_reference_ingest_validator.py"),
            ],
            repo_root=repo_root,
        ),
        "reused_evidence": False,
        "status": "ready" if repo_generated_seed_contract_pass else "blocked",
        "contract_pass": repo_generated_seed_contract_pass,
        "dataset_count": len(sources),
        "truth_classes": sorted({str(row["truth_class"]) for row in sources}),
        "checksum_status_counts": dict(sorted(checksum_status_counts.items())),
        "manifest_policy_contract": manifest_policy_contract,
        "phase3_external_corpus_readiness": phase3_external_corpus_readiness,
        "phase3_lane_coverage": {
            "covered_lane_count": len(covered_lanes),
            "required_lane_count": len(PHASE3_BENCHMARK_LANES),
            "covered_lanes": covered_lanes,
            "missing_lanes": sorted(set(PHASE3_BENCHMARK_LANES).difference(covered_lanes)),
            "additional_repo_generated_seed_lanes": extra_seed_lanes,
            "contract_pass": phase3_lane_coverage_contract_pass,
        },
        "phase3_acquisition_plan": {
            "status": phase3_acquisition_plan.get("status"),
            "contract_pass": bool(phase3_acquisition_plan.get("contract_pass")),
            "non_seed_lane_count": phase3_acquisition_plan.get("non_seed_lane_count"),
            "non_seed_source_count": phase3_acquisition_plan.get("non_seed_source_count"),
            "ready_source_count": phase3_acquisition_plan.get("ready_source_count"),
            "all_non_seed_lanes_have_acquisition_policy": bool(
                phase3_acquisition_plan.get("all_non_seed_lanes_have_acquisition_policy")
            ),
            "all_non_seed_sources_have_license_checksum_and_expected_outputs": bool(
                phase3_acquisition_plan.get(
                    "all_non_seed_sources_have_license_checksum_and_expected_outputs"
                )
            ),
        },
        "sources": sources,
        "blockers": blockers,
        "claim_boundary": (
            "This manifest fixes Developer Preview dataset/license policy for the bundled "
            "repo-generated seed corpus. It does not bundle upstream OpenSees, "
            "buildingSMART, IFC query, or commercial solver data and does not grant "
            "commercial redistribution rights."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    categories = payload.get("categories")
    categories = categories if isinstance(categories, dict) else {}
    scope = payload.get("scope")
    scope = scope if isinstance(scope, dict) else {}
    included = scope.get("included") if isinstance(scope.get("included"), list) else []
    excluded = scope.get("excluded") if isinstance(scope.get("excluded"), list) else []
    freeze_policy = scope.get("freeze_policy") if isinstance(scope.get("freeze_policy"), dict) else {}
    closure_visibility = _as_dict(payload.get("gap_ledger_closure_requirement_visibility"))
    failed_requirement_ids = [
        str(item)
        for item in _as_list(closure_visibility.get("nonclosed_failed_closure_requirement_ids"))
        if str(item)
    ]
    lines = [
        "# Open Benchmark Developer Preview Readiness",
        "",
        f"- `status`: `{payload.get('status')}`",
        f"- `developer_preview_ready`: `{payload.get('developer_preview_ready')}`",
        f"- `commercial_release_ready`: `{payload.get('commercial_release_ready')}`",
        f"- `blocker_count`: `{payload.get('blocker_count')}`",
        f"- `future_commercial_blocker_count`: `{payload.get('future_commercial_blocker_count')}`",
        f"- `source_commit_sha`: `{payload.get('source_commit_sha')}`",
        f"- `reuse_policy`: `{payload.get('reuse_policy')}`",
        f"- `input_checksum_policy`: `{payload.get('input_checksum_policy')}`",
        "",
        "## Blocker Categories",
        "",
        "| Category | Count | Developer Preview Blocking |",
        "|---|---:|---|",
    ]
    for category in FOUR_CATEGORIES:
        row = categories.get(category)
        row = row if isinstance(row, dict) else {}
        lines.append(
            f"| {category} | {int(row.get('blocker_count', 0) or 0)} | "
            f"{'no, future commercial only' if category == 'future commercial' else 'yes'} |"
        )
    lines.extend(
        [
            "",
            "## Gap Ledger Closure Requirement Visibility",
            "",
            f"- `source_status`: `{closure_visibility.get('source_status', 'missing')}`",
            f"- `source_full_gap_ledger_ready`: `{closure_visibility.get('source_full_gap_ledger_ready', False)}`",
            f"- `closure_requirements`: `{closure_visibility.get('closure_requirement_pass_count', 0)}/"
            f"{closure_visibility.get('closure_requirement_count', 0)}`",
            f"- `failed_closure_requirements`: `{closure_visibility.get('closure_requirement_fail_count', 0)}`",
            f"- `nonclosed_rows_with_failed_closure_requirements`: "
            f"`{closure_visibility.get('nonclosed_rows_with_failed_closure_requirements_count', 0)}`",
        ]
    )
    if failed_requirement_ids:
        lines.extend(["", "Failed requirement IDs:"])
        lines.extend(f"- `{item}`" for item in failed_requirement_ids)
    if closure_visibility.get("claim_boundary"):
        lines.extend(["", str(closure_visibility.get("claim_boundary"))])
    lines.extend(
        [
            "",
            "## Scope Boundary Summary",
            "",
            (
                "Developer Preview scope: public/open benchmark import, "
                "deterministic analysis/reporting, benchmark scorecard, and local GUI review."
            ),
            (
                "Excluded scope: permit automation, engineer replacement, "
                "SaaS/account/license server, commercial SLA, and AI/GNN/surrogate truth claims."
            ),
            (
                "Future Commercial Release blockers: customer shadow, license approval, "
                "commercial SLA, 30-run CI streak, and external approval receipts."
            ),
        ]
    )
    lines.extend(["", "## Included Scope", ""])
    lines.extend(f"- {item}" for item in included if isinstance(item, str))
    lines.extend(["", "## Excluded Scope", ""])
    lines.extend(f"- {item}" for item in excluded if isinstance(item, str))
    lines.extend(["", "## Freeze Policy", ""])
    for key in ("new_feature_development", "ai_training", "gpu_hip"):
        if key in freeze_policy:
            lines.append(f"- `{key}`: `{freeze_policy[key]}`")
    lines.extend(
        [
            "",
            "## Claim Boundary",
            "",
            str(payload.get("claim_boundary", "")),
            "",
        ]
    )
    return "\n".join(lines)


def _strip_volatile(payload: Any, path: tuple[str, ...] = ()) -> Any:
    if isinstance(payload, dict):
        return {
            key: _strip_volatile(value, (*path, key))
            for key, value in payload.items()
            if key not in {"generated_at"}
            and not (path == () and key == "source_commit_sha")
        }
    if isinstance(payload, list):
        return [_strip_volatile(item, path) for item in payload]
    return payload


def _strip_volatile_markdown(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith("- `source_commit_sha`:")
    )


def check_developer_preview_readiness(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    out_md_path: Path = DEFAULT_OUT_MD,
    product_snapshot_path: Path = PRODUCT_READINESS_SNAPSHOT,
    dataset_license_manifest_path: Path = DEFAULT_DATASET_LICENSE_MANIFEST,
) -> tuple[bool, str]:
    resolved_out = out_path if out_path.is_absolute() else repo_root / out_path
    resolved_out_md = out_md_path if out_md_path.is_absolute() else repo_root / out_md_path
    if not resolved_out.exists():
        return False, f"developer_preview_readiness_missing:{out_path.as_posix()}"
    try:
        existing = json.loads(resolved_out.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"developer_preview_readiness_unreadable:{out_path.as_posix()}:{exc.__class__.__name__}"
    if not isinstance(existing, dict):
        return False, f"developer_preview_readiness_invalid_object:{out_path.as_posix()}"
    generated = build_developer_preview_readiness(
        repo_root=repo_root,
        product_snapshot_path=product_snapshot_path,
        dataset_license_manifest_path=dataset_license_manifest_path,
    )
    if _strip_volatile(existing) != _strip_volatile(generated):
        return False, "developer_preview_readiness_semantic_mismatch"
    expected_markdown = _markdown(generated)
    if not resolved_out_md.exists():
        return False, f"developer_preview_readiness_report_missing:{out_md_path.as_posix()}"
    existing_markdown = resolved_out_md.read_text(encoding="utf-8")
    if _strip_volatile_markdown(existing_markdown) != _strip_volatile_markdown(expected_markdown):
        return False, "developer_preview_readiness_report_mismatch"
    return True, "developer_preview_readiness_consistent"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--dataset-license-manifest", type=Path, default=DEFAULT_DATASET_LICENSE_MANIFEST)
    parser.add_argument("--write-dataset-license-manifest", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        ok, message = check_developer_preview_readiness(
            repo_root=ROOT,
            out_path=args.out,
            out_md_path=args.out_md,
            product_snapshot_path=PRODUCT_READINESS_SNAPSHOT,
            dataset_license_manifest_path=args.dataset_license_manifest,
        )
        if not ok:
            print(f"Developer Preview readiness check FAILED: {message}", file=sys.stderr)
            return 2
        print(f"Developer Preview readiness check: {message}")
        return 0
    if args.write_dataset_license_manifest:
        manifest = build_dataset_license_manifest(repo_root=ROOT)
        manifest_path = args.dataset_license_manifest if args.dataset_license_manifest.is_absolute() else ROOT / args.dataset_license_manifest
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    payload = build_developer_preview_readiness(
        repo_root=ROOT,
        dataset_license_manifest_path=args.dataset_license_manifest,
    )
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        out_md = args.out_md if args.out_md.is_absolute() else ROOT / args.out_md
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else f"Developer Preview readiness: {payload['status']}")
    return 1 if args.fail_blocked and not payload["developer_preview_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
