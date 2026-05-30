#!/usr/bin/env python3
"""MGT native reanalysis pipeline (integrity + story proxy; FEA loop not wired)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from design_optimization.io import load_json
from build_gpu_solver_claim_receipt import build_gpu_solver_claim_receipt
from run_story_model_reanalysis import build_mgt_reanalysis_provenance, run_story_model_reanalysis
from run_mgt_global_fea_readiness_gate import build_mgt_global_fea_readiness_gate
from sync_mgt_roundtrip_provenance import refresh_optimized_roundtrip_from_mgt


SCHEMA_VERSION = "mgt-native-reanalysis-pipeline.v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_mgt_roundtrip_integrity(
    *,
    roundtrip_json: Path,
    mgt_path: Path | None = None,
) -> dict[str, Any]:
    provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json, mgt_path=mgt_path)
    resolved = Path(str(provenance.get("mgt_path") or ""))
    expected_sha = str(provenance.get("mgt_sha256") or "").strip().lower()
    actual_sha = _sha256_file(resolved) if resolved.is_file() else ""
    if not resolved.is_file():
        integrity_status = "missing_mgt"
        sha_ok = False
    elif not expected_sha:
        integrity_status = "verified_without_expected_sha"
        sha_ok = True
    elif actual_sha == expected_sha:
        integrity_status = "verified"
        sha_ok = True
    else:
        integrity_status = "sha_mismatch"
        sha_ok = False
    return {
        **provenance,
        "sha256_verified": sha_ok,
        "sha256_actual": actual_sha,
        "integrity_status": integrity_status,
    }


def run_mgt_native_reanalysis_pipeline(
    *,
    roundtrip_json: Path,
    changes_json: Path,
    state_npz: Path,
    mgt_path: Path | None = None,
    refresh_parse: bool = False,
    sync_provenance: bool = True,
) -> dict[str, Any]:
    changes_payload = load_json(changes_json)
    mgt_refresh: dict[str, Any] | None = None
    resolved_mgt = mgt_path
    if sync_provenance or refresh_parse:
        provenance = build_mgt_reanalysis_provenance(roundtrip_json=roundtrip_json, mgt_path=mgt_path)
        resolved_mgt = Path(str(provenance.get("mgt_path") or ""))
        if refresh_parse or sync_provenance:
            mgt_refresh = refresh_optimized_roundtrip_from_mgt(
                mgt_path=resolved_mgt,
                roundtrip_json=roundtrip_json,
                npz_out=roundtrip_json.with_suffix(".npz"),
                parse_refresh=refresh_parse,
                sync_provenance_only=not refresh_parse,
            )

    integrity = verify_mgt_roundtrip_integrity(roundtrip_json=roundtrip_json, mgt_path=resolved_mgt)

    blockers: list[str] = []
    if not integrity.get("mgt_exists"):
        blockers.append("mgt_file_missing")
    elif integrity.get("integrity_status") == "sha_mismatch":
        blockers.append("mgt_sha256_mismatch")

    story_receipt: dict[str, Any] | None = None
    gpu_receipt: dict[str, Any] | None = None
    if integrity.get("mgt_exists") and state_npz.is_file():
        story_receipt = run_story_model_reanalysis(state_npz_path=state_npz, changes_payload=changes_payload)
        gpu_receipt = build_gpu_solver_claim_receipt(state_npz_path=state_npz)
        if story_receipt.get("status") == "blocked":
            blockers.extend(f"story_{item}" for item in story_receipt.get("blockers") or [])

    global_fea_readiness = build_mgt_global_fea_readiness_gate(
        roundtrip_json=roundtrip_json,
        mgt_path=resolved_mgt,
    )
    parse_linked = bool(mgt_refresh and (mgt_refresh.get("parse") or {}).get("status") == "pass")
    fea_status = "not_wired"
    if global_fea_readiness.get("readiness_for_global_fea_wiring"):
        fea_status = "readiness_pass"
    elif parse_linked or (mgt_refresh and mgt_refresh.get("status") == "ready"):
        fea_status = "parse_linked"

    native_fea = {
        "status": fea_status,
        "native_solve_status": "not_wired",
        "readiness_for_global_fea_wiring": global_fea_readiness.get("readiness_for_global_fea_wiring"),
        "note": (
            "MGT roundtrip/NPZ preflight ready; global FEA solver loop still not connected."
            if fea_status == "readiness_pass"
            else "MGT re-parsed to roundtrip JSON; story-model proxy follows optimization state NPZ."
            if parse_linked
            else "Full MGT→global FEA reassembly not connected; story proxy uses optimization NPZ."
        ),
        "mgt_refresh": mgt_refresh,
        "global_fea_readiness": global_fea_readiness,
    }

    if "mgt_file_missing" in blockers:
        status = "blocked"
    elif story_receipt and story_receipt.get("status") == "pass" and "mgt_sha256_mismatch" not in blockers:
        status = "story_proxy_pass"
    elif story_receipt and story_receipt.get("status") == "pass":
        status = "story_proxy_pass_with_mgt_warn"
    else:
        status = "story_proxy_warn"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "claim": "MGT integrity + story-model proxy reanalysis; not native FEA certification.",
        "roundtrip_json": str(roundtrip_json),
        "changes_json": str(changes_json),
        "state_npz": str(state_npz),
        "mgt_integrity": integrity,
        "native_fea": native_fea,
        "story_model_reanalysis": story_receipt,
        "gpu_solver_claim": gpu_receipt,
        "blockers": blockers,
        "mgt_refresh": mgt_refresh,
    }
