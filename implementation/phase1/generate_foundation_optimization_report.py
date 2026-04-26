#!/usr/bin/env python3
"""Generate a mat foundation/pile optimization readiness report for release tracking."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re


REASONS = {
    "PASS": "foundation member optimization artifact is attached and dataset contains foundation elements",
    "ERR_INPUT": "required optimization input report is missing or invalid",
    "ERR_DATASET_ABSENT": "design-optimization dataset lacks foundation element groups",
    "ERR_NO_FOUNDATION_OPTIMIZATION_ARTIFACT": "foundation member groups exist but no optimization artifact is attached",
    "ERR_FOUNDATION_SCOPE_ONLY": "foundation scope is attached, but no active foundation optimization evidence is present",
    "ERR_UPSTREAM_FOUNDATION_SCOPE_NOT_PROMOTED": "upstream model carries foundation labels, but the active design-optimization dataset does not expose them",
    "ERR_FOUNDATION_PARSER_DROP_SUSPECTED": "raw source carries foundation labels, but parsed model/dataset does not expose them",
}


FOUNDATION_KEYWORDS = {
    "foundation",
    "mat",
    "raft",
    "pile",
    "caisson",
    "pilecap",
    "pile_cap",
    "footing",
    "ground",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "y", "yes", "true", "on"}:
            return True
        if v in {"0", "n", "no", "false", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _normalize_foundation_key(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[-\s/]+", "_", text)
    return text


def _default_artifact_path(dataset_path: Path) -> Path:
    return dataset_path.with_name("foundation_optimization_artifact.json")


def _get_foundation_member_counts(type_counts: dict[str, object]) -> tuple[int, dict[str, int]]:
    if not isinstance(type_counts, dict):
        return 0, {}
    foundation_counts: dict[str, int] = {}
    total = 0
    for raw_key, raw_value in type_counts.items():
        key = _normalize_foundation_key(raw_key)
        if key in FOUNDATION_KEYWORDS:
            val = _safe_int(raw_value, 0)
            foundation_counts[key] = val
            total += val
    return total, foundation_counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--design-optimization-dataset",
        default="implementation/phase1/release/design_optimization/design_optimization_dataset_report.json",
    )
    p.add_argument(
        "--foundation-optimization-artifact",
        default="",
        help="Optional foundation-specific optimization result JSON path",
    )
    p.add_argument("--out", default="implementation/phase1/release/design_optimization/foundation_optimization_report.json")
    args = p.parse_args()

    dataset_path = Path(args.design_optimization_dataset)
    dataset = _load_json(dataset_path)
    artifact_path = (
        Path(args.foundation_optimization_artifact)
        if str(args.foundation_optimization_artifact).strip()
        else _default_artifact_path(dataset_path)
    )
    foundation_artifact = _load_json(artifact_path) if artifact_path and artifact_path.exists() else {}
    dataset_summary = dataset.get("summary", {})
    member_type_counts = {}
    if isinstance(dataset_summary, dict):
        raw_counts = dataset_summary.get("member_type_counts", {})
        if isinstance(raw_counts, dict):
            member_type_counts = raw_counts

    foundation_member_count, foundation_type_counts = _get_foundation_member_counts(member_type_counts)
    dataset_contract = _safe_bool(dataset.get("contract_pass", False))
    artifact_contract = _safe_bool(foundation_artifact.get("contract_pass", False))
    artifact_summary = foundation_artifact.get("summary", {}) if isinstance(foundation_artifact.get("summary"), dict) else {}
    artifact_present = bool(artifact_path and artifact_path.exists() and foundation_artifact)
    foundation_artifact_rows = _safe_int(artifact_summary.get("optimized_foundation_member_count", 0))
    foundation_artifact_group_rows = _safe_int(artifact_summary.get("optimized_foundation_group_count", foundation_artifact_rows))
    blocked_foundation_group_count = _safe_int(artifact_summary.get("blocked_foundation_group_count", 0))
    artifact_foundation_count = _safe_int(artifact_summary.get("foundation_member_type_count", 0))
    upstream_foundation_label_count = _safe_int(artifact_summary.get("upstream_foundation_label_count", 0))
    raw_source_foundation_label_count = _safe_int(artifact_summary.get("raw_source_foundation_label_count", 0))
    artifact_foundation_type_counts = artifact_summary.get("foundation_member_type_counts", {}) if isinstance(artifact_summary.get("foundation_member_type_counts"), dict) else {}
    artifact_scan_mode = str(artifact_summary.get("candidate_scan_mode", "") or "")
    artifact_evidence_mode = str(artifact_summary.get("optimization_evidence_mode", "") or "")
    upstream_provenance_mode = str(artifact_summary.get("upstream_foundation_provenance_mode", "") or "")
    scope_source = "dataset_summary"
    if foundation_member_count <= 0 and artifact_foundation_count > 0:
        foundation_member_count = int(artifact_foundation_count)
        if artifact_foundation_type_counts:
            foundation_type_counts = {str(k): _safe_int(v, 0) for k, v in artifact_foundation_type_counts.items()}
        scope_source = "artifact_scan"
    elif foundation_member_count <= 0 and artifact_scan_mode == "npz_full_empty":
        scope_source = "artifact_empty_scan"

    if not dataset and not isinstance(dataset.get("summary"), dict):
        reason_code = "ERR_INPUT"
        reason = "design-optimization dataset report is missing or invalid"
        mode = "input_missing"
        contract_pass = False
    elif foundation_member_count <= 0 and upstream_provenance_mode == "parser_drop_suspected":
        reason_code = "ERR_FOUNDATION_PARSER_DROP_SUSPECTED"
        reason = (
            "Raw MIDAS source still contains foundation-like labels, but the parsed model and active "
            f"design-optimization dataset expose none. raw_labels={raw_source_foundation_label_count}, "
            f"parsed_labels={upstream_foundation_label_count}, scan={artifact_scan_mode or 'unknown'}."
        )
        mode = "foundation_scope_lost_between_raw_source_and_parsed_model"
        contract_pass = False
    elif foundation_member_count <= 0 and upstream_foundation_label_count > 0:
        reason_code = "ERR_UPSTREAM_FOUNDATION_SCOPE_NOT_PROMOTED"
        reason = (
            "Upstream MIDAS model carries foundation-like labels, but the active design-optimization "
            "dataset does not expose those members/groups."
        )
        mode = "upstream_foundation_scope_not_promoted_into_dataset"
        contract_pass = False
    elif foundation_member_count <= 0:
        reason_code = "ERR_DATASET_ABSENT"
        reason = (
            "Active design-optimization dataset has no foundation groups after full NPZ scan. "
            "Foundation optimization scope is not represented."
            if scope_source == "artifact_empty_scan"
            else "Active design-optimization dataset has no foundation groups. Foundation optimization scope is not represented."
        )
        mode = "rule_engine_present_but_dataset_absent"
        contract_pass = False
    elif not artifact_present:
        reason_code = "ERR_NO_FOUNDATION_OPTIMIZATION_ARTIFACT"
        reason = (
            "Foundation members are represented but no dedicated optimization artifact is attached "
            "for mat/pile/SSI-aware optimization."
        )
        mode = "foundation_members_present_but_no_active_optimization"
        contract_pass = False
    elif foundation_artifact_group_rows <= 0:
        reason_code = "ERR_FOUNDATION_SCOPE_ONLY"
        reason = (
            "Foundation scope was detected, but no foundation-specific cost-reduction action or "
            "mat/pile optimization evidence is attached yet."
        )
        mode = "foundation_scope_detected_but_no_active_optimization"
        contract_pass = False
    elif artifact_contract:
        reason_code = "PASS"
        reason = "foundation optimization artifact is attached and dataset contains foundation members"
        mode = "active_foundation_member_optimization"
        contract_pass = True
    else:
        reason_code = "ERR_FOUNDATION_SCOPE_ONLY"
        reason = (
            "Foundation optimization artifact exists but does not yet satisfy the active "
            "foundation optimization contract."
        )
        mode = "foundation_scope_detected_but_no_active_optimization"
        contract_pass = False

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-foundation-optimization-readiness",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "design_optimization_dataset": str(args.design_optimization_dataset),
            "foundation_optimization_artifact": str(artifact_path) if artifact_path else "",
        },
        "summary": {
            "optimization_mode": mode,
            "foundation_member_type_count": int(foundation_member_count),
            "foundation_member_type_counts": foundation_type_counts,
            "design_opt_member_count": int(dataset_summary.get("member_count", 0) or 0),
            "design_opt_group_count": int(dataset_summary.get("group_count", 0) or 0),
            "dataset_contract_pass": bool(dataset_contract),
            "foundation_artifact_present": bool(artifact_present),
            "foundation_artifact_contract_pass": bool(artifact_contract),
            "foundation_artifact_optimized_count": int(foundation_artifact_rows),
            "foundation_artifact_optimized_group_count": int(foundation_artifact_group_rows),
            "foundation_artifact_blocked_group_count": int(blocked_foundation_group_count),
            "foundation_scope_source": scope_source,
            "foundation_artifact_scan_mode": artifact_scan_mode,
            "foundation_artifact_evidence_mode": artifact_evidence_mode,
            "upstream_foundation_label_count": int(upstream_foundation_label_count),
            "raw_source_foundation_label_count": int(raw_source_foundation_label_count),
            "upstream_foundation_provenance_mode": upstream_provenance_mode,
        },
        "source_provenance": {
            "dataset_report": str(args.design_optimization_dataset),
            "foundation_artifact": str(artifact_path) if artifact_path else "",
            "artifact_scan_mode": artifact_scan_mode,
            "artifact_evidence_mode": artifact_evidence_mode,
            "upstream_provenance_mode": upstream_provenance_mode,
            "upstream_foundation_label_count": int(upstream_foundation_label_count),
            "raw_source_foundation_label_count": int(raw_source_foundation_label_count),
        },
        "checks": {
            "foundation_members_present": int(foundation_member_count) > 0,
            "foundation_artifact_present": bool(artifact_present),
            "foundation_artifact_contract_pass": bool(artifact_contract),
            "dataset_contract_pass": bool(dataset_contract),
            "foundation_optimization_evidence_present": int(foundation_artifact_group_rows) > 0,
            "upstream_foundation_label_present": int(upstream_foundation_label_count) > 0,
            "raw_source_foundation_label_present": int(raw_source_foundation_label_count) > 0,
            "foundation_scope_ready": bool(contract_pass),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
        "artifact_inputs": {
            "dataset": str(args.design_optimization_dataset),
            "foundation_optimization_artifact": str(artifact_path) if artifact_path else "",
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote foundation optimization report: {out}")


if __name__ == "__main__":
    main()
