from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_QUALITY_GATE = Path("implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json")
DEFAULT_OUT = Path("implementation/phase1/commercialization_status/real_drawing_solver_exact_promotion_queue.json")
DEFAULT_OUT_MD = Path("implementation/phase1/commercialization_status/real_drawing_solver_exact_promotion_queue.md")
DEFAULT_IFC_RECONSTRUCTION_PLAN = Path(
    "implementation/phase1/commercialization_status/real_drawing_ifc_solver_exact_reconstruction_plan.json"
)
DEFAULT_TARGET_SOLVER_EXACT_ASSET_COUNT = 10


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object at {path}")
    return payload


def _load_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return _load_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")


def _flags(row: dict[str, Any]) -> set[str]:
    return {str(flag) for flag in (row.get("quality_flags") or []) if str(flag)}


def _claim_flags(row: dict[str, Any]) -> list[str]:
    return sorted(str(flag) for flag in (row.get("claim_quality_flags") or []) if str(flag))


def _promotion_family(row: dict[str, Any]) -> str:
    route = str(row.get("route") or "")
    quality_tier = str(row.get("quality_tier") or "")
    flags = _flags(row)
    file_type = str(row.get("file_type") or "")
    geometry_claim_status = str(row.get("geometry_claim_status") or "")
    load_model_status = str(row.get("load_model_status") or "")
    if bool(row.get("solver_exact", False)) and "sampled_dense_model" in flags:
        return "solver_exact_lod_completion"
    if geometry_claim_status == "ifc_geometry_exact_ready" and load_model_status == "source_ifc_load_model_missing":
        return "ifc_load_model_evidence_closure"
    if "proxy_node_glyph_fallback" in flags:
        return "ifc_node_glyph_topology_rebuild"
    if "sparse_preview" in flags and not bool(row.get("solver_exact", False)):
        return "archive_sparse_preview_expansion"
    if route == "midas_binary_decoded_preview_bridge" and file_type == ".zip":
        return "archive_preview_exactness_verification"
    if "ifc_proxy" in route or "proxy_layout_not_true_geometry" in flags or quality_tier == "proxy_preview_review":
        return "ifc_coordinate_geometry_reconstruction"
    return "manual_solver_exact_review"


def _family_priority(family: str) -> int:
    return {
        "archive_preview_exactness_verification": 10,
        "archive_sparse_preview_expansion": 20,
        "ifc_load_model_evidence_closure": 30,
        "ifc_node_glyph_topology_rebuild": 35,
        "ifc_coordinate_geometry_reconstruction": 40,
        "solver_exact_lod_completion": 50,
        "manual_solver_exact_review": 60,
    }.get(family, 90)


def _family_action(family: str) -> str:
    return {
        "archive_preview_exactness_verification": "verify decoded archive preview against native solver topology and flip solver_exact when topology is complete",
        "archive_sparse_preview_expansion": "expand sparse decoded archive preview into complete solver topology before solver_exact promotion",
        "ifc_load_model_evidence_closure": "attach IFC load-case extraction or engineer-signed zero-load evidence before analysis claims",
        "ifc_node_glyph_topology_rebuild": "rebuild IFC fallback node glyph layout into edge-backed structural topology",
        "ifc_coordinate_geometry_reconstruction": "extract IFC placement/shape coordinates and replace proxy layout with recovered structural geometry",
        "solver_exact_lod_completion": "add full-detail paging or LOD evidence so sampled solver-exact asset can support full-detail claims",
        "manual_solver_exact_review": "perform manual engineer review and map the asset to a solver-exact conversion route",
    }.get(family, "perform manual solver-exact promotion review")


def _family_evidence(family: str) -> list[str]:
    if family == "archive_preview_exactness_verification":
        return [
            "native_archive_decode_manifest",
            "node_element_count_match",
            "viewer_sidecar_rebuild_receipt",
        ]
    if family == "archive_sparse_preview_expansion":
        return [
            "expanded_archive_decode_manifest",
            "non_sparse_segment_count_delta",
            "solver_exact_regression_receipt",
        ]
    if family == "ifc_load_model_evidence_closure":
        return [
            "ifc_load_case_extraction_or_engineer_signed_zero_load_receipt",
            "solver_graph_json_npz_receipt",
            "viewer_sidecar_rebuild_receipt",
        ]
    if family == "ifc_node_glyph_topology_rebuild":
        return [
            "ifc_relationship_edge_extraction_receipt",
            "node_glyph_fallback_removed",
            "viewer_sidecar_rebuild_receipt",
        ]
    if family == "ifc_coordinate_geometry_reconstruction":
        return [
            "ifc_placement_coordinate_extraction_receipt",
            "proxy_layout_flag_removed",
            "solver_exact_or_engineer_signed_geometry_receipt",
        ]
    if family == "solver_exact_lod_completion":
        return [
            "full_detail_lod_manifest",
            "sampled_dense_model_flag_removed_or_explained",
            "viewer_performance_regression_receipt",
        ]
    return ["manual_solver_exact_review_receipt"]


def _ifc_reconstruction_plan_by_asset(plan_path: Path | None) -> dict[str, dict[str, Any]]:
    plan = _load_json_if_exists(plan_path)
    items = plan.get("ifc_reconstruction_items") if isinstance(plan.get("ifc_reconstruction_items"), list) else []
    return {
        str(item.get("asset_ref") or ""): item
        for item in items
        if isinstance(item, dict) and str(item.get("asset_ref") or "")
    }


def _promotion_delta(row: dict[str, Any], family: str) -> int:
    if bool(row.get("solver_exact", False)):
        return 0
    if family in {
        "archive_preview_exactness_verification",
        "archive_sparse_preview_expansion",
        "ifc_load_model_evidence_closure",
        "ifc_node_glyph_topology_rebuild",
        "ifc_coordinate_geometry_reconstruction",
        "manual_solver_exact_review",
    }:
        return 1
    return 0


def _effort_label(family: str) -> str:
    if family == "archive_preview_exactness_verification":
        return "low"
    if family == "archive_sparse_preview_expansion":
        return "medium"
    if family == "ifc_load_model_evidence_closure":
        return "low"
    if family == "ifc_node_glyph_topology_rebuild":
        return "medium_high"
    if family == "ifc_coordinate_geometry_reconstruction":
        return "high"
    if family == "solver_exact_lod_completion":
        return "medium"
    return "unknown"


def _asset_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    family = str(row.get("promotion_family") or "")
    delta_sort = 0 if _safe_int(row.get("expected_solver_exact_delta"), 0) > 0 else 1
    return (_family_priority(family), delta_sort, str(row.get("asset_ref") or ""))


def _promotion_item(
    row: dict[str, Any],
    index: int,
    *,
    ifc_reconstruction_plan_by_asset: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    family = _promotion_family(row)
    asset_ref = str(row.get("asset_ref") or "")
    item = {
        "promotion_id": f"RP-{index:03d}",
        "asset_ref": asset_ref,
        "file_type": str(row.get("file_type") or ""),
        "route": str(row.get("route") or ""),
        "status": str(row.get("status") or ""),
        "quality_tier": str(row.get("quality_tier") or ""),
        "quality_flags": sorted(_flags(row)),
        "claim_quality_flags": _claim_flags(row),
        "geometry_exact_ready": bool(row.get("geometry_exact_ready", False)),
        "ifc_geometry_exact_ready": bool(row.get("ifc_geometry_exact_ready", False)),
        "geometry_claim_status": str(row.get("geometry_claim_status") or ""),
        "load_model_status": str(row.get("load_model_status") or ""),
        "load_model_ready": bool(row.get("load_model_ready", False)),
        "analysis_claim_ready": bool(row.get("analysis_claim_ready", False)),
        "load_evidence_status": str(row.get("load_evidence_status") or ""),
        "load_evidence_contract_pass": bool(row.get("load_evidence_contract_pass", False)),
        "load_case_group_count": _safe_int(row.get("load_case_group_count"), 0),
        "structural_load_count": _safe_int(row.get("structural_load_count"), 0),
        "structural_action_count": _safe_int(row.get("structural_action_count"), 0),
        "connected_structural_action_count": _safe_int(row.get("connected_structural_action_count"), 0),
        "zero_load_signature_required": bool(row.get("zero_load_signature_required", False)),
        "engineer_zero_load_signature_attached": bool(row.get("engineer_zero_load_signature_attached", False)),
        "zero_load_attestation_scope": str(row.get("zero_load_attestation_scope") or ""),
        "segment_count": _safe_int(row.get("segment_count"), 0),
        "renderable_segment_count": _safe_int(row.get("renderable_segment_count"), 0),
        "node_count": _safe_int(row.get("node_count"), 0),
        "element_count": _safe_int(row.get("element_count"), 0),
        "current_solver_exact": bool(row.get("solver_exact", False)),
        "promotion_family": family,
        "priority_rank": _family_priority(family),
        "effort_label": _effort_label(family),
        "expected_solver_exact_delta": _promotion_delta(row, family),
        "owner_lane": (
            "archive_decoder_owner"
            if family.startswith("archive_")
            else "ifc_load_owner"
            if family == "ifc_load_model_evidence_closure"
            else "ifc_geometry_owner"
            if family.startswith("ifc_")
            else "viewer_performance_owner"
            if family == "solver_exact_lod_completion"
            else "structural_review_owner"
        ),
        "recommended_action": _family_action(family),
        "closure_evidence_required": _family_evidence(family),
        "closure_status": "pending",
    }
    plan_item = (ifc_reconstruction_plan_by_asset or {}).get(asset_ref)
    if isinstance(plan_item, dict):
        required_evidence = [
            str(value)
            for value in (plan_item.get("required_evidence") or [])
            if str(value)
        ]
        open_evidence = [
            str(value)
            for value in (plan_item.get("open_evidence") or [])
            if str(value)
        ]
        attached_evidence = [
            str(value)
            for value in (plan_item.get("attached_evidence") or [])
            if str(value)
        ]
        metrics = plan_item.get("metrics") if isinstance(plan_item.get("metrics"), dict) else {}
        item.update(
            {
                "blocker_family": str(plan_item.get("blocker_family") or ""),
                "blocker_reason_code": str(plan_item.get("blocker_reason_code") or ""),
                "reconstruction_plan_status": "open",
                "commercial_claim_blocked": bool(plan_item.get("commercial_claim_blocked", False)),
                "geometry_claim_status": str(
                    plan_item.get("geometry_claim_status") or item.get("geometry_claim_status") or ""
                ),
                "load_model_status": str(plan_item.get("load_model_status") or item.get("load_model_status") or ""),
                "analysis_claim_ready": bool(
                    plan_item.get("analysis_claim_ready", item.get("analysis_claim_ready", False))
                ),
                "load_evidence_status": str(
                    plan_item.get("load_evidence_status") or item.get("load_evidence_status") or ""
                ),
                "load_evidence_contract_pass": bool(
                    plan_item.get("load_evidence_contract_pass", item.get("load_evidence_contract_pass", False))
                ),
                "load_case_group_count": _safe_int(
                    plan_item.get("load_case_group_count", item.get("load_case_group_count", 0)),
                    0,
                ),
                "structural_load_count": _safe_int(
                    plan_item.get("structural_load_count", item.get("structural_load_count", 0)),
                    0,
                ),
                "structural_action_count": _safe_int(
                    plan_item.get("structural_action_count", item.get("structural_action_count", 0)),
                    0,
                ),
                "connected_structural_action_count": _safe_int(
                    plan_item.get(
                        "connected_structural_action_count",
                        item.get("connected_structural_action_count", 0),
                    ),
                    0,
                ),
                "zero_load_signature_required": bool(
                    plan_item.get("zero_load_signature_required", item.get("zero_load_signature_required", False))
                ),
                "engineer_zero_load_signature_attached": bool(
                    plan_item.get(
                        "engineer_zero_load_signature_attached",
                        item.get("engineer_zero_load_signature_attached", False),
                    )
                ),
                "zero_load_attestation_scope": str(
                    plan_item.get("zero_load_attestation_scope") or item.get("zero_load_attestation_scope") or ""
                ),
                "edge_coverage_ratio": metrics.get("edge_coverage_ratio", 0),
                "attached_evidence": attached_evidence,
                "open_evidence": open_evidence,
            }
        )
        if open_evidence:
            item["closure_evidence_required"] = open_evidence
        elif required_evidence:
            item["closure_evidence_required"] = required_evidence
        if open_evidence or required_evidence:
            item["recommended_action"] = str(plan_item.get("commercialization_recommendation") or item["recommended_action"])
    return item


def build_promotion_queue(
    quality_gate_path: Path = DEFAULT_QUALITY_GATE,
    *,
    target_solver_exact_asset_count: int = DEFAULT_TARGET_SOLVER_EXACT_ASSET_COUNT,
    ifc_reconstruction_plan_path: Path | None = DEFAULT_IFC_RECONSTRUCTION_PLAN,
) -> dict[str, Any]:
    if not quality_gate_path.exists():
        return {
            "schema_version": "real-drawing-solver-exact-promotion-queue.v1",
            "source_quality_gate": str(quality_gate_path),
            "source_ifc_reconstruction_plan": str(ifc_reconstruction_plan_path or ""),
            "contract_pass": False,
            "reason_code": "ERR_REAL_DRAWING_QUALITY_GATE_MISSING",
            "summary": {
                "target_solver_exact_asset_count": int(target_solver_exact_asset_count),
                "current_solver_exact_asset_count": 0,
                "planned_unlock_batch_count": 0,
                "planned_solver_exact_asset_count_after_unlock_batch": 0,
                "promotion_candidate_count": 0,
                "promotion_delta_available": 0,
            },
            "promotion_items": [],
            "planned_unlock_batch": [],
        }

    gate = _load_json(quality_gate_path)
    gate_summary = gate.get("summary") if isinstance(gate.get("summary"), dict) else {}
    asset_rows = [
        row
        for row in (gate.get("asset_quality_rows") or [])
        if isinstance(row, dict) and str(row.get("asset_ref") or "")
    ]
    current_solver_exact_count = _safe_int(gate_summary.get("solver_exact_asset_count"), 0)
    target_solver_exact_asset_count = int(target_solver_exact_asset_count)
    required_delta = max(0, target_solver_exact_asset_count - current_solver_exact_count)
    ifc_plan_by_asset = _ifc_reconstruction_plan_by_asset(ifc_reconstruction_plan_path)

    candidate_rows = [
        row
        for row in asset_rows
        if str(row.get("quality_tier") or "") != "solver_exact_ready"
    ]
    items = [
        _promotion_item(row, index, ifc_reconstruction_plan_by_asset=ifc_plan_by_asset)
        for index, row in enumerate(candidate_rows, start=1)
    ]
    items = sorted(items, key=_asset_sort_key)
    for index, item in enumerate(items, start=1):
        item["promotion_id"] = f"RP-{index:03d}"

    unlock_batch: list[dict[str, Any]] = []
    accumulated_delta = 0
    for item in items:
        delta = _safe_int(item.get("expected_solver_exact_delta"), 0)
        if accumulated_delta >= required_delta:
            break
        if delta <= 0:
            continue
        unlock_batch.append(
            {
                "promotion_id": item["promotion_id"],
                "asset_ref": item["asset_ref"],
                "promotion_family": item["promotion_family"],
                "expected_solver_exact_delta": delta,
                "recommended_action": item["recommended_action"],
                "blocker_reason_code": str(item.get("blocker_reason_code") or ""),
                "closure_evidence_required": item.get("closure_evidence_required", []),
            }
        )
        accumulated_delta += delta

    family_counts = Counter(str(item.get("promotion_family") or "") for item in items)
    effort_counts = Counter(str(item.get("effort_label") or "") for item in items)
    promotion_delta_available = sum(_safe_int(item.get("expected_solver_exact_delta"), 0) for item in items)
    planned_solver_exact_after = current_solver_exact_count + accumulated_delta
    sufficient_unlock_batch = accumulated_delta >= required_delta
    contract_pass = bool(gate.get("contract_pass", False)) and (bool(items) or required_delta == 0)
    if not gate.get("contract_pass", False):
        reason_code = "ERR_SOURCE_QUALITY_GATE_NOT_PASSING"
    elif required_delta == 0:
        reason_code = "PASS_SOLVER_EXACT_TARGET_REACHED"
        contract_pass = True
    elif not items:
        reason_code = "PASS_NO_PROMOTION_ITEMS"
        contract_pass = True
    elif not sufficient_unlock_batch:
        reason_code = "PASS_PROMOTION_QUEUE_OPEN_TARGET_NOT_YET_COVERED"
    else:
        reason_code = "PASS_PROMOTION_QUEUE_OPEN"
    return {
        "schema_version": "real-drawing-solver-exact-promotion-queue.v1",
        "source_quality_gate": str(quality_gate_path),
        "source_ifc_reconstruction_plan": str(ifc_reconstruction_plan_path or ""),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "quality_gate_reason_code": str(gate.get("reason_code") or ""),
        "structure_viewer_href": str(gate.get("structure_viewer_href") or ""),
        "recommended_claim": (
            "Solver-exact target is already reached; continue closing review-only quality flags before full exact claims."
            if required_delta == 0
            else "Promote the planned unlock batch before claiming more than engineer-in-loop review readiness."
            if items
            else "No real drawing solver-exact promotion work is currently open."
        ),
        "summary": {
            "asset_count": _safe_int(gate_summary.get("asset_count"), len(asset_rows)),
            "current_solver_exact_asset_count": current_solver_exact_count,
            "target_solver_exact_asset_count": target_solver_exact_asset_count,
            "required_solver_exact_delta": required_delta,
            "promotion_candidate_count": len(items),
            "promotion_delta_available": promotion_delta_available,
            "planned_unlock_batch_count": len(unlock_batch),
            "planned_unlock_batch_expected_delta": accumulated_delta,
            "planned_solver_exact_asset_count_after_unlock_batch": planned_solver_exact_after,
            "sufficient_unlock_batch_for_target": sufficient_unlock_batch,
            "family_counts": dict(sorted(family_counts.items())),
            "effort_counts": dict(sorted(effort_counts.items())),
        },
        "planned_unlock_batch": unlock_batch,
        "promotion_items": items,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    planned = report.get("planned_unlock_batch") if isinstance(report.get("planned_unlock_batch"), list) else []
    items = report.get("promotion_items") if isinstance(report.get("promotion_items"), list) else []
    lines = [
        "# Real Drawing Solver-Exact Promotion Queue",
        "",
        f"- Contract: {report.get('reason_code')}",
        f"- Viewer: `{report.get('structure_viewer_href', '')}`",
        f"- Current solver-exact assets: {summary.get('current_solver_exact_asset_count', 0)}",
        f"- Target solver-exact assets: {summary.get('target_solver_exact_asset_count', 0)}",
        f"- Planned unlock batch: {summary.get('planned_unlock_batch_count', 0)} assets",
        f"- Planned solver-exact after batch: {summary.get('planned_solver_exact_asset_count_after_unlock_batch', 0)}",
        "",
        "## Planned Unlock Batch",
        "",
    ]
    if planned:
        lines.extend(["| ID | Asset | Family | Delta | Action |", "| --- | --- | --- | ---: | --- |"])
        for item in planned:
            lines.append(
                "| {pid} | {asset} | {family} | {delta} | {action} |".format(
                    pid=item.get("promotion_id", ""),
                    asset=item.get("asset_ref", ""),
                    family=item.get("promotion_family", ""),
                    delta=item.get("expected_solver_exact_delta", 0),
                    action=str(item.get("recommended_action", "")).replace("|", "/"),
                )
            )
    else:
        lines.append("No planned unlock batch is available.")
    lines.extend(
        [
            "",
            "## Full Queue",
            "",
            "| ID | Asset | Family | Effort | Delta | Blocker | Flags |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for item in items:
        flags = [
            *[str(flag) for flag in item.get("quality_flags", [])],
            *[f"claim:{flag}" for flag in item.get("claim_quality_flags", [])],
        ]
        lines.append(
            "| {pid} | {asset} | {family} | {effort} | {delta} | {blocker} | {flags} |".format(
                pid=item.get("promotion_id", ""),
                asset=item.get("asset_ref", ""),
                family=item.get("promotion_family", ""),
                effort=item.get("effort_label", ""),
                delta=item.get("expected_solver_exact_delta", 0),
                blocker=str(item.get("blocker_reason_code", "")).replace("|", "/"),
                flags=", ".join(flags),
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quality-gate", type=Path, default=DEFAULT_QUALITY_GATE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--ifc-reconstruction-plan", type=Path, default=DEFAULT_IFC_RECONSTRUCTION_PLAN)
    parser.add_argument("--target-solver-exact-assets", type=int, default=DEFAULT_TARGET_SOLVER_EXACT_ASSET_COUNT)
    parser.add_argument("--json", action="store_true", help="Print the promotion queue JSON to stdout.")
    parser.add_argument(
        "--fail-on-uncovered-target",
        action="store_true",
        help="Return exit code 2 when the planned unlock batch cannot cover the target delta.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_promotion_queue(
        args.quality_gate,
        target_solver_exact_asset_count=args.target_solver_exact_assets,
        ifc_reconstruction_plan_path=args.ifc_reconstruction_plan,
    )
    _write_json(args.out, report)
    _write_text(args.out_md, render_markdown(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    if args.fail_on_uncovered_target and not bool(
        report.get("summary", {}).get("sufficient_unlock_batch_for_target", False)
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
