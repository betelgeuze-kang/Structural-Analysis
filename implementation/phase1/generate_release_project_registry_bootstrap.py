#!/usr/bin/env python3
"""Bootstrap the release project registry from checked-in signed release artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.generate_signed_release_registry import (
        _artifact_entry,
        _load_json,
        _project_registry_approval_payload,
        _project_registry_audit_payload,
    )
    from implementation.phase1.project_registry_service import build_project_registry
except ImportError:  # pragma: no cover
    from generate_signed_release_registry import (  # type: ignore
        _artifact_entry,
        _load_json,
        _project_registry_approval_payload,
        _project_registry_audit_payload,
    )
    from project_registry_service import build_project_registry  # type: ignore


DEFAULT_RELEASE_DIR = Path("implementation/phase1/release")
DEFAULT_PROJECT_ID = "phase1-release"
DEFAULT_PROJECT_NAME = "Phase1 Structural AI Release Package"


def _resolve_path(raw: str, default: Path) -> Path:
    return Path(str(raw).strip()) if str(raw).strip() else default


def _require_existing_path(raw: str, *, field_name: str) -> Path:
    path = Path(str(raw).strip())
    if not str(raw).strip():
        raise FileNotFoundError(f"missing {field_name}")
    if not path.exists():
        raise FileNotFoundError(str(path))
    return path


def _load_release_registry_artifact_entries(release_registry: dict[str, Any]) -> list[dict[str, Any]]:
    registry_body = release_registry.get("registry_body") if isinstance(release_registry.get("registry_body"), dict) else {}
    rows = registry_body.get("artifacts") if isinstance(registry_body.get("artifacts"), list) else []
    artifact_entries: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = _require_existing_path(str(row.get("path", "") or ""), field_name="registry_body.artifacts[].path")
        label = str(row.get("label", "") or "").strip() or path.name
        artifact_entries.append(_artifact_entry(label, path, None))
    return artifact_entries


def bootstrap_release_project_registry(
    *,
    release_registry_path: Path,
    project_id: str,
    project_name: str,
    project_private_key_out: Path,
    project_public_key_out: Path,
    project_signature_out: Path,
    project_package_out: Path,
    out: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    release_registry = _load_json(release_registry_path)
    if not bool(release_registry.get("contract_pass", False)):
        raise ValueError("release registry was not green")
    checks = release_registry.get("checks") if isinstance(release_registry.get("checks"), dict) else {}
    if not bool(checks.get("signature_verified_pass", False)):
        raise ValueError("release registry signature was not verified")

    artifact_entries = _load_release_registry_artifact_entries(release_registry)
    if not artifact_entries:
        raise ValueError("release registry artifacts were missing")

    signature = release_registry.get("signature") if isinstance(release_registry.get("signature"), dict) else {}
    inputs = release_registry.get("inputs") if isinstance(release_registry.get("inputs"), dict) else {}
    release_public_key = _require_existing_path(
        str(signature.get("public_key_path", "") or inputs.get("public_key_out", "") or ""),
        field_name="release registry public key",
    )
    release_signature = _require_existing_path(
        str(signature.get("signature_out", "") or inputs.get("signature_out", "") or ""),
        field_name="release registry signature",
    )
    artifact_entries.extend(
        [
            _artifact_entry("release_registry_public_key", release_public_key, None),
            _artifact_entry("release_registry_signature", release_signature, None),
        ]
    )

    timestamp = str(generated_at or release_registry.get("generated_at", "") or "").strip()
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    return build_project_registry(
        project_id=project_id,
        project_name=project_name,
        artifact_paths=[Path(str(row["path"])) for row in artifact_entries],
        audit_payload=_project_registry_audit_payload(
            artifact_entries=artifact_entries,
            generated_at=timestamp,
        ),
        approval_payload=_project_registry_approval_payload(generated_at=timestamp),
        private_key_out=project_private_key_out,
        public_key_out=project_public_key_out,
        signature_out=project_signature_out,
        package_out=project_package_out,
        out=out,
        generated_at=timestamp,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", default=str(DEFAULT_RELEASE_DIR))
    parser.add_argument("--release-registry", default="")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument("--project-private-key-out", default="")
    parser.add_argument("--project-public-key-out", default="")
    parser.add_argument("--project-signature-out", default="")
    parser.add_argument("--project-package-out", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--generated-at", default="")
    args = parser.parse_args()

    release_dir = Path(args.release_dir)
    release_registry_path = _resolve_path(args.release_registry, release_dir / "release_registry.json")
    project_private_key_out = _resolve_path(
        args.project_private_key_out,
        release_dir / "signing" / "project_registry_ed25519.pem",
    )
    project_public_key_out = _resolve_path(
        args.project_public_key_out,
        release_dir / "signing" / "project_registry_ed25519.pub.pem",
    )
    project_signature_out = _resolve_path(args.project_signature_out, release_dir / "project_registry.signature.b64")
    project_package_out = _resolve_path(args.project_package_out, release_dir / "project_package.zip")
    out = _resolve_path(args.out, release_dir / "project_registry.json")

    payload = bootstrap_release_project_registry(
        release_registry_path=release_registry_path,
        project_id=str(args.project_id),
        project_name=str(args.project_name),
        project_private_key_out=project_private_key_out,
        project_public_key_out=project_public_key_out,
        project_signature_out=project_signature_out,
        project_package_out=project_package_out,
        out=out,
        generated_at=str(args.generated_at).strip() or None,
    )
    print(payload["summary_line"])
    if not payload["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
