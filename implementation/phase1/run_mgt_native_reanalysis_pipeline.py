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
from run_mgt_global_fea_3d_native_solve import run_mgt_global_fea_3d_native_solve
from resolve_midas_same_mesh_result_path import resolve_midas_same_mesh_result_path
from run_midas_gen_same_mesh_native_comparison import run_midas_gen_same_mesh_native_comparison
from run_mgt_global_fea_condensed_solve import run_mgt_global_fea_condensed_solve
from run_mgt_global_fea_mesh_contract_gate import build_mgt_global_fea_mesh_contract_gate
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
    skip_global_solves: bool = False,
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
    mesh_contract = build_mgt_global_fea_mesh_contract_gate(roundtrip_json=roundtrip_json)
    condensed_solve: dict[str, Any] | None = None
    mesh_3d_solve: dict[str, Any] | None = None
    midas_same_mesh_comparison: dict[str, Any] | None = None
    midas_result_json, _midas_resolution = resolve_midas_same_mesh_result_path(roundtrip_json=roundtrip_json)
    productization_dir = roundtrip_json.resolve().parents[2] / "release_evidence" / "productization"
    if mesh_contract.get("mesh_contract_ready") and not skip_global_solves:
        condensed_solve = run_mgt_global_fea_condensed_solve(roundtrip_json=roundtrip_json)
        mesh_3d_solve = run_mgt_global_fea_3d_native_solve(roundtrip_json=roundtrip_json)
        if midas_result_json.is_file():
            midas_same_mesh_comparison = run_midas_gen_same_mesh_native_comparison(
                result_json=midas_result_json,
                roundtrip_json=roundtrip_json,
                native_3d_solve_json=productization_dir / "mgt_global_fea_3d_native_solve.json",
                native_condensed_solve_json=productization_dir / "mgt_global_fea_condensed_solve.json",
            )
    parse_linked = bool(mgt_refresh and (mgt_refresh.get("parse") or {}).get("status") == "pass")
    native_solve_status = str((mesh_3d_solve or {}).get("native_solve_status") or (condensed_solve or {}).get("native_solve_status") or "not_wired")
    if midas_same_mesh_comparison:
        comparison_status = str(midas_same_mesh_comparison.get("comparison_status") or "")
        if comparison_status.startswith("pass_live"):
            native_solve_status = "mesh_3d_beam_global_wired_with_midas_live_ingest"
        elif comparison_status.startswith("pass_model_derived"):
            native_solve_status = "mesh_3d_beam_global_wired_with_midas_model_derived"
        elif comparison_status.startswith("pass") and (
            native_solve_status.endswith("_bridge") or "bridge" in native_solve_status
        ):
            native_solve_status = "mesh_3d_beam_global_wired_with_midas_same_mesh_proxy"
    fea_status = "not_wired"
    if native_solve_status.startswith("mesh_3d_beam_global_wired"):
        fea_status = "mesh_3d_global_wired"
    elif native_solve_status == "condensed_global_fea_wired":
        fea_status = "condensed_solve_wired"
    elif mesh_contract.get("mesh_contract_ready") and global_fea_readiness.get("readiness_for_global_fea_wiring"):
        fea_status = "mesh_contract_pass"
    elif global_fea_readiness.get("readiness_for_global_fea_wiring"):
        fea_status = "readiness_pass"
    elif parse_linked or (mgt_refresh and mgt_refresh.get("status") == "ready"):
        fea_status = "parse_linked"

    native_fea = {
        "status": fea_status,
        "native_solve_status": native_solve_status,
        "readiness_for_global_fea_wiring": global_fea_readiness.get("readiness_for_global_fea_wiring"),
        "note": (
            "MGT NPZ same-mesh 3D beam global Newton wired; commercial HF export proxy crosscheck attached."
            if native_solve_status.startswith("mesh_3d_beam_global_wired")
            else "MGT NPZ condensed to story model and solved in-repo (not full 3D licensed global FEA)."
            if native_solve_status == "condensed_global_fea_wired"
            else "MGT roundtrip/NPZ mesh contract ready; condensed solve not completed."
            if fea_status == "mesh_contract_pass"
            else "MGT roundtrip/NPZ preflight ready; global FEA solver loop still not connected."
            if fea_status == "readiness_pass"
            else "MGT re-parsed to roundtrip JSON; story-model proxy follows optimization state NPZ."
            if parse_linked
            else "Full MGT→global FEA reassembly not connected; story proxy uses optimization NPZ."
        ),
        "mgt_refresh": mgt_refresh,
        "global_fea_readiness": global_fea_readiness,
        "global_fea_mesh_contract": mesh_contract,
        "condensed_global_fea_solve": condensed_solve,
        "mesh_3d_global_fea_solve": mesh_3d_solve,
        "midas_gen_same_mesh_comparison": midas_same_mesh_comparison,
        "global_solves_skipped": bool(skip_global_solves),
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
