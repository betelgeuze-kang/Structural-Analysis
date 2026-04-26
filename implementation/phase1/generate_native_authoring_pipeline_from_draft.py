#!/usr/bin/env python3
"""Materialize the native authoring pipeline from a frontend draft JSON."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.generate_native_authoring_workspace_ops_bundle import (
        build_native_authoring_workspace_ops_bundle,
    )
except ImportError:  # pragma: no cover
    from generate_native_authoring_workspace_ops_bundle import (  # type: ignore
        build_native_authoring_workspace_ops_bundle,
    )


DEFAULT_OUT_DIR = Path("implementation/phase1/release/authoring/from_draft")
DEFAULT_SIGNING_DIR = Path("implementation/phase1/release/signing")
DEFAULT_OUT = DEFAULT_OUT_DIR / "native_authoring_pipeline_from_draft.json"


def build_native_authoring_pipeline_from_draft(
    *,
    draft_json_path: Path,
    out_dir: Path = DEFAULT_OUT_DIR,
    signing_dir: Path = DEFAULT_SIGNING_DIR,
    out_path: Path = DEFAULT_OUT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = str(generated_at or "").strip() or datetime.now(timezone.utc).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    signing_dir.mkdir(parents=True, exist_ok=True)

    workspace_summary = out_dir / "native_authoring_workspace_summary.json"
    solver_session = out_dir / "native_authoring_solver_session.json"
    solver_loadcomb = out_dir / "native_authoring_solver_session.loadcomb_preview.mgt"
    job_manifest = out_dir / "native_authoring_job_manifest.json"
    batch_report = out_dir / "native_authoring_batch_job_report.json"
    snapshot_root = out_dir / "snapshots"
    project_registry = out_dir / "native_authoring_project_registry.json"
    project_package = out_dir / "native_authoring_project_package.zip"
    private_key = signing_dir / "native_authoring_draft_project_registry_ed25519.pem"
    public_key = signing_dir / "native_authoring_draft_project_registry_ed25519.pub.pem"
    signature = signing_dir / "native_authoring_draft_project_registry.signature.b64"
    ops_bundle = out_dir / "native_authoring_ops_bundle.json"

    bundle_payload = build_native_authoring_workspace_ops_bundle(
        workspace_summary_path=workspace_summary,
        solver_session_out=solver_session,
        solver_loadcomb_out=solver_loadcomb,
        draft_json_path=draft_json_path,
        job_manifest_out=job_manifest,
        batch_report_out=batch_report,
        snapshot_root=snapshot_root,
        project_registry_out=project_registry,
        project_package_out=project_package,
        private_key_out=private_key,
        public_key_out=public_key,
        signature_out=signature,
        out=ops_bundle,
        generated_at=timestamp,
    )

    payload = {
        "schema_version": "1.0",
        "report_family": "native_authoring_pipeline_from_draft",
        "generated_at": timestamp,
        "draft_json_path": str(draft_json_path),
        "summary": {
            "job_count": int(bundle_payload.get("summary", {}).get("job_count", 0) or 0),
            "snapshot_count": int(bundle_payload.get("summary", {}).get("snapshot_count", 0) or 0),
            "solver_combo_count": int(bundle_payload.get("summary", {}).get("solver_combo_count", 0) or 0),
            "solver_mesh_request_count": int(bundle_payload.get("summary", {}).get("solver_mesh_request_count", 0) or 0),
        },
        "artifacts": {
            "workspace_summary_json": str(workspace_summary),
            "solver_session_json": str(solver_session),
            "solver_loadcomb_preview_mgt": str(solver_loadcomb),
            "job_manifest_json": str(job_manifest),
            "batch_job_report_json": str(batch_report),
            "project_registry_json": str(project_registry),
            "project_package_zip": str(project_package),
            "project_registry_signature": str(signature),
            "ops_bundle_json": str(ops_bundle),
        },
        "ops_bundle_summary": bundle_payload.get("summary", {}),
        "summary_line": (
            "Native authoring pipeline from draft: "
            f"{'PASS' if bundle_payload.get('contract_pass', False) else 'CHECK'} | "
            f"jobs={int(bundle_payload.get('summary', {}).get('job_count', 0) or 0)} | "
            f"combos={int(bundle_payload.get('summary', {}).get('solver_combo_count', 0) or 0)}"
        ),
        "contract_pass": bool(bundle_payload.get("contract_pass", False)),
        "reason_code": str(bundle_payload.get("reason_code", "") or ""),
        "reason": "native authoring pipeline materialized from frontend draft",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-json", required=True)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--signing-dir", default=str(DEFAULT_SIGNING_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    payload = build_native_authoring_pipeline_from_draft(
        draft_json_path=Path(args.draft_json),
        out_dir=Path(args.out_dir),
        signing_dir=Path(args.signing_dir),
        out_path=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
