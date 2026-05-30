#!/usr/bin/env python3
"""Validate productization delivery evidence artifact contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "validate-productization-delivery-evidence.v1"

REQUIRED_FILES = (
    "delivery_evidence_bundle.json",
    "gap_closure_status.json",
    "commercial_solver_cross_validation.json",
    "proxy_solver_divergence_gate.json",
    "post_optimization_reanalysis_gate.json",
    "story_model_reanalysis.json",
    "mgt_native_reanalysis_pipeline.json",
    "mgt_global_fea_readiness_gate.json",
    "gpu_solver_claim_receipt.json",
    "gpu_newton_certification_checklist.json",
    "rh_closure_checklist.json",
    "rh_signed_closure_packet_template.json",
    "residual_holdout_closure_updates.json",
    "mgt_roundtrip_assembly_fingerprint.json",
    "ml_multi_objective_status.json",
    "mgt_global_fea_mesh_contract_gate.json",
    "rh_engineer_review_packet_template.html",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _has_schema_version(payload: dict[str, Any]) -> bool:
    if str(payload.get("schema_version") or "").strip():
        return True
    for key in ("story_model_reanalysis", "mgt_provenance", "gpu_solver_claim"):
        inner = payload.get(key)
        if isinstance(inner, dict) and str(inner.get("schema_version") or "").strip():
            return True
    return False


def validate_productization_delivery_evidence(
    *,
    productization_dir: Path,
    require_bundle_ready: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    missing: list[str] = []
    checked: dict[str, str] = {}

    for name in REQUIRED_FILES:
        path = productization_dir / name
        if not path.is_file():
            missing.append(name)
            continue
        if path.suffix.lower() == ".html":
            checked[name] = "present"
            continue
        payload = _load(path)
        if not _has_schema_version(payload):
            errors.append(f"{name}:missing_schema_version")
        checked[name] = str(payload.get("status") or payload.get("delivery_status") or "present")

    bundle = _load(productization_dir / "delivery_evidence_bundle.json")
    gap = _load(productization_dir / "gap_closure_status.json")
    if require_bundle_ready and bundle.get("status") != "ready":
        errors.append("delivery_evidence_bundle_not_ready")
    if gap.get("delivery_status") not in {"ready", "review_required"}:
        errors.append("gap_closure_status_invalid_delivery_status")

    ok = not missing and not errors
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if ok else "fail",
        "productization_dir": str(productization_dir),
        "files_checked": len(checked),
        "files_missing": missing,
        "file_status": checked,
        "errors": errors,
        "bundle_status": bundle.get("status"),
        "delivery_status": gap.get("delivery_status"),
        "authority_holdout_status": gap.get("authority_holdout_status"),
    }
