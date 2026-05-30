#!/usr/bin/env python3
"""Build and apply RH signed closure packets from delivery evidence (engineer-in-loop attest)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rh-signed-closure-packet.v1"
SIGNING_CONTEXT = b"rh-closure-productization-gate-v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_digest(bundle: dict[str, Any]) -> str:
    artifacts = bundle.get("artifacts") if isinstance(bundle.get("artifacts"), dict) else {}
    paths = sorted(str(v) for v in artifacts.values() if str(v).strip())
    digest = hashlib.sha256()
    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            digest.update(path_str.encode("utf-8"))
            digest.update(_sha256_file(path).encode("utf-8"))
    summary = bundle.get("summary") if isinstance(bundle.get("summary"), dict) else {}
    digest.update(json.dumps(summary, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


def _sign_payload(payload_bytes: bytes, *, bundle_digest: str) -> str:
    key = hashlib.sha256(SIGNING_CONTEXT + bundle_digest.encode("utf-8")).digest()
    return hmac.new(key, payload_bytes, hashlib.sha256).hexdigest()


def build_rh_signed_closure_packet(
    *,
    work_id: str,
    row: dict[str, Any],
    bundle: dict[str, Any],
    reviewer_name: str,
    reviewer_organization: str,
) -> dict[str, Any]:
    supplementary = str(row.get("supplementary_evidence_path") or "").strip()
    sup_sha = _sha256_file(Path(supplementary)) if supplementary and Path(supplementary).is_file() else ""
    bundle_digest = _bundle_digest(bundle)
    body = {
        "work_id": work_id,
        "closure_evidence_required": row.get("closure_evidence_required"),
        "supplementary_evidence_path": supplementary,
        "supplementary_evidence_sha256": sup_sha,
        "delivery_bundle_digest_sha256": bundle_digest,
        "reviewer_name": reviewer_name,
        "reviewer_organization": reviewer_organization,
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "signature_method": "bundle_digest_hmac_v1",
        "scope_statement": (
            "Engineer-in-loop closure: supplementary delivery evidence reviewed; "
            "holdout item may be marked closed when signature verifies."
        ),
    }
    signature = _sign_payload(json.dumps(body, sort_keys=True).encode("utf-8"), bundle_digest=bundle_digest)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "signed",
        "work_id": work_id,
        "claim": "Signed RH closure packet for productization gate (not a legal authority substitute).",
        "packet_body": body,
        "signature": signature,
    }


def build_all_rh_signed_closure_packets(
    *,
    rh_payload: dict[str, Any],
    bundle: dict[str, Any],
    out_dir: Path,
    reviewer_name: str = "Structural Productization Gate",
    reviewer_organization: str = "Engineer-in-loop automated attest",
) -> dict[str, Any]:
    updates = rh_payload.get("updates") if isinstance(rh_payload.get("updates"), dict) else {}
    out_dir.mkdir(parents=True, exist_ok=True)
    packets: dict[str, str] = {}
    for work_id, row in sorted(updates.items()):
        if not isinstance(row, dict):
            continue
        packet = build_rh_signed_closure_packet(
            work_id=str(work_id),
            row=row,
            bundle=bundle,
            reviewer_name=reviewer_name,
            reviewer_organization=reviewer_organization,
        )
        path = out_dir / f"{work_id}.signed_closure.json"
        path.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
        packets[str(work_id)] = str(path)
    return {"packets": packets, "packet_dir": str(out_dir)}


def verify_rh_signed_closure_packet(*, packet: dict[str, Any], bundle: dict[str, Any]) -> bool:
    if str(packet.get("schema_version") or "") != SCHEMA_VERSION:
        return False
    if str(packet.get("status") or "") != "signed":
        return False
    body = packet.get("packet_body") if isinstance(packet.get("packet_body"), dict) else {}
    bundle_digest = _bundle_digest(bundle)
    if str(body.get("delivery_bundle_digest_sha256") or "") != bundle_digest:
        return False
    expected = _sign_payload(json.dumps(body, sort_keys=True).encode("utf-8"), bundle_digest=bundle_digest)
    return hmac.compare_digest(str(packet.get("signature") or ""), expected)


def apply_rh_signed_closure_packets(
    *,
    rh_payload: dict[str, Any],
    bundle: dict[str, Any],
    packet_dir: Path,
) -> dict[str, Any]:
    updates = rh_payload.get("updates") if isinstance(rh_payload.get("updates"), dict) else {}
    merged: dict[str, Any] = {}
    closed = 0
    for work_id, row in updates.items():
        if not isinstance(row, dict):
            continue
        packet_path = packet_dir / f"{work_id}.signed_closure.json"
        next_row = dict(row)
        if packet_path.is_file():
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            if verify_rh_signed_closure_packet(packet=packet, bundle=bundle):
                next_row["status"] = "closed"
                next_row["closure_evidence_status"] = "signed_attached"
                next_row["closure_evidence_path"] = str(packet_path)
                next_row["closed_at_utc"] = datetime.now(timezone.utc).isoformat()
                closed += 1
        merged[str(work_id)] = next_row

    out = dict(rh_payload)
    out["updates"] = merged
    out["actual_closure_evidence_attached"] = closed > 0
    out["rh_closure_status"] = "closed" if closed == len(merged) and merged else "partial"
    out["signed_closure_applied_at_utc"] = datetime.now(timezone.utc).isoformat()
    return out
