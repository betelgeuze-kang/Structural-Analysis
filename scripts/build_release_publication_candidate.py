#!/usr/bin/env python3
"""Build a flat, upload-safe release publication candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")
GENERATE_SIGNED_RELEASE_REGISTRY = Path("implementation/phase1/generate_signed_release_registry.py")
GENERATED_ASSET_SOURCES = {
    "project_package.zip": Path("project_package.zip"),
    "project_registry.json": Path("project_registry.json"),
    "project_registry.signature.b64": Path("signing/project_registry.signature.b64"),
    "project_registry_ed25519.pub.pem": Path("signing/project_registry_ed25519.pub.pem"),
    "release_registry.json": Path("release_registry.json"),
    "release_registry.signature.b64": Path("signing/release_registry.signature.b64"),
    "release_registry_ed25519.pub.pem": Path("signing/release_registry_ed25519.pub.pem"),
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _contains_private_key_marker(path: Path) -> bool:
    try:
        return b"PRIVATE KEY" in path.read_bytes()[:8192].upper()
    except OSError:
        return False


def _is_safe_asset_source(asset_name: str, source: Path) -> bool:
    lower_names = (asset_name.lower(), source.name.lower())
    if any(name.endswith(".pem") and not name.endswith(".pub.pem") for name in lower_names):
        return False
    return not _contains_private_key_marker(source)


def _manifest_generated_at(manifest: dict[str, Any]) -> str:
    value = str(manifest.get("generated_at", "") or "").strip()
    return value


def _manifest_artifacts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("artifacts")
    if not isinstance(rows, list) or not rows:
        raise ValueError("manifest artifacts must be a non-empty list")
    return [row for row in rows if isinstance(row, dict)]


def _source_for_asset(row: dict[str, Any], work_dir: Path) -> Path:
    asset_name = str(row.get("asset_name", "") or "").strip()
    generated_relative = GENERATED_ASSET_SOURCES.get(asset_name)
    if generated_relative is not None:
        return work_dir / generated_relative
    return Path(str(row.get("local_path", "") or ""))


def _external_registry_artifact_args(artifacts: list[dict[str, Any]]) -> list[str]:
    by_name = {
        str(row.get("asset_name", "") or "").strip(): Path(str(row.get("local_path", "") or ""))
        for row in artifacts
        if str(row.get("asset_name", "") or "").strip() and str(row.get("local_path", "") or "").strip()
    }
    optional_paths = {
        "--external-benchmark-submission-readiness": Path(
            "implementation/phase1/release/external_benchmark_submission_readiness.json"
        ),
        "--external-benchmark-submission-updates": Path(
            "implementation/phase1/release_evidence/productization/external_benchmark_submission_updates.json"
        ),
        "--residual-holdout-closure-updates": Path(
            "implementation/phase1/release_evidence/productization/residual_holdout_closure_updates.json"
        ),
        "--external-benchmark-execution-manifest": Path(
            "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.json"
        ),
        "--external-benchmark-execution-manifest-markdown": Path(
            "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_manifest.md"
        ),
        "--external-benchmark-execution-status": Path(
            "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.json"
        ),
        "--external-benchmark-execution-status-markdown": Path(
            "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_execution_status_manifest.md"
        ),
    }
    manifest_asset_args = {
        "--external-benchmark-kickoff-package": by_name.get("external_benchmark_kickoff_package.json"),
        "--external-benchmark-kickoff-markdown": by_name.get("external_benchmark_kickoff_package.md"),
        "--approve-all-submission-readiness-preview": by_name.get(
            "external_benchmark_submission_readiness_preview.approve_all.json"
        ),
        "--approve-all-submission-readiness-preview-markdown": by_name.get(
            "external_benchmark_submission_readiness_preview.approve_all.md"
        ),
        "--case-onepage-attestation-index": by_name.get("case_onepage_attestation_index.json"),
        "--case-onepage-attestation-index-markdown": by_name.get("case_onepage_attestation_index.md"),
        "--audit-review-decision-batch-template": by_name.get("audit_review_decision_batch_template.json"),
        "--audit-review-decision-batch-template-markdown": by_name.get("audit_review_decision_batch_template.md"),
        "--exact-topology-structural-preview-promotion-queue": by_name.get(
            "exact_topology_structural_preview_promotion_queue.json"
        ),
        "--exact-topology-structural-preview-promotion-queue-markdown": by_name.get(
            "exact_topology_structural_preview_promotion_queue.md"
        ),
    }
    args: list[str] = []
    for flag, path in {**optional_paths, **manifest_asset_args}.items():
        if path is not None and (flag in manifest_asset_args or path.exists()):
            args.extend([flag, str(path)])
    return args


def _run_registry_generation(
    *,
    work_dir: Path,
    generated_at: str,
    python_executable: str,
    manifest_artifacts: list[dict[str, Any]] | None = None,
) -> list[str]:
    signing_dir = work_dir / "signing"
    command = [
        python_executable,
        str(GENERATE_SIGNED_RELEASE_REGISTRY),
        "--private-key-out",
        str(signing_dir / "release_registry_ed25519.pem"),
        "--public-key-out",
        str(signing_dir / "release_registry_ed25519.pub.pem"),
        "--signature-out",
        str(signing_dir / "release_registry.signature.b64"),
        "--project-private-key-out",
        str(signing_dir / "project_registry_ed25519.pem"),
        "--project-public-key-out",
        str(signing_dir / "project_registry_ed25519.pub.pem"),
        "--project-signature-out",
        str(signing_dir / "project_registry.signature.b64"),
        "--project-package-out",
        str(work_dir / "project_package.zip"),
        "--project-registry-out",
        str(work_dir / "project_registry.json"),
        "--out",
        str(work_dir / "release_registry.json"),
    ]
    command.extend(_external_registry_artifact_args(manifest_artifacts or []))
    if generated_at:
        command.extend(["--generated-at", generated_at])
    # First pass may create keys and set key_generated_this_run=true in registry metadata.
    # A second pass with the same key files stabilizes registry/package bytes for upload.
    for _ in range(2):
        proc = subprocess.run(command, check=False, capture_output=True, text=True)
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "release registry generation failed").strip()
            raise RuntimeError(message)
    return command


def _copy_asset(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _flat_root_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
        return True
    except ValueError:
        return False


def build_release_publication_candidate(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    artifact_root: Path,
    work_dir: Path | None = None,
    manifest_out: Path | None = None,
    generated_at: str = "",
    write: bool = False,
    skip_registry_generation: bool = False,
    python_executable: str = sys.executable,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be an object")
    artifacts = _manifest_artifacts(manifest)
    release_tag = str(manifest.get("release_tag", "") or "").strip()
    timestamp = str(generated_at or "").strip() or _manifest_generated_at(manifest)
    resolved_work_dir = work_dir or artifact_root.with_name(f"{artifact_root.name}.work")
    resolved_manifest_out = manifest_out or artifact_root.with_name(f"{artifact_root.name}.manifest.json")

    plan_actions: list[dict[str, Any]] = []
    selected_names = [str(row.get("asset_name", "") or "").strip() for row in artifacts]
    if not write:
        for row in artifacts:
            asset_name = str(row.get("asset_name", "") or "").strip()
            plan_actions.append(
                {
                    "asset_name": asset_name,
                    "source": str(_source_for_asset(row, resolved_work_dir)),
                    "destination": str(artifact_root / asset_name),
                    "status": "planned",
                }
            )
        return {
            "ok": True,
            "write": False,
            "release_tag": release_tag,
            "generated_at": timestamp,
            "manifest": str(manifest_path),
            "manifest_out": str(resolved_manifest_out),
            "artifact_root": str(artifact_root),
            "work_dir": str(resolved_work_dir),
            "skip_registry_generation": skip_registry_generation,
            "actions": plan_actions,
            "errors": [],
            "totals": {"selected_assets": len(artifacts), "copied": 0, "errors": 0},
        }

    errors: list[str] = []
    generation_command: list[str] = []
    if _path_is_relative_to(resolved_manifest_out, artifact_root):
        errors.append(f"manifest_out must not be inside artifact_root: {resolved_manifest_out}")
        return {
            "ok": False,
            "write": True,
            "release_tag": release_tag,
            "generated_at": timestamp,
            "manifest": str(manifest_path),
            "manifest_out": str(resolved_manifest_out),
            "artifact_root": str(artifact_root),
            "work_dir": str(resolved_work_dir),
            "skip_registry_generation": skip_registry_generation,
            "generation_command": generation_command,
            "actions": [],
            "extra_files": [],
            "errors": errors,
            "totals": {"selected_assets": len(artifacts), "copied": 0, "errors": len(errors)},
        }
    if not skip_registry_generation:
        generation_command = _run_registry_generation(
            work_dir=resolved_work_dir,
            generated_at=timestamp,
            python_executable=python_executable,
            manifest_artifacts=artifacts,
        )

    candidate_manifest = dict(manifest)
    candidate_manifest["generated_at"] = timestamp or candidate_manifest.get("generated_at", "")
    candidate_manifest["publication_candidate"] = {
        "artifact_root": str(artifact_root),
        "work_dir": str(resolved_work_dir),
        "source_manifest": str(manifest_path),
        "registry_generated": not skip_registry_generation,
    }
    candidate_rows: list[dict[str, Any]] = []

    for row in artifacts:
        asset_name = str(row.get("asset_name", "") or "").strip()
        source = _source_for_asset(row, resolved_work_dir)
        destination = artifact_root / asset_name
        action: dict[str, Any] = {
            "asset_name": asset_name,
            "source": str(source),
            "destination": str(destination),
            "status": "pending",
        }
        if not asset_name:
            errors.append("manifest asset_name is required")
            action["status"] = "error"
        elif not source.is_file():
            errors.append(f"source artifact missing for {asset_name}: {source}")
            action["status"] = "error"
        elif not _is_safe_asset_source(asset_name, source):
            errors.append(f"unsafe private key-like asset source for {asset_name}: {source}")
            action["status"] = "error"
        else:
            _copy_asset(source, destination)
            actual_sha = _sha256(destination)
            actual_bytes = destination.stat().st_size
            updated_row = dict(row)
            updated_row["sha256"] = actual_sha
            updated_row["bytes"] = actual_bytes
            candidate_rows.append(updated_row)
            action.update(
                {
                    "status": "copied",
                    "sha256": actual_sha,
                    "bytes": actual_bytes,
                    "required": bool(row.get("required", False)),
                }
            )
        plan_actions.append(action)

    root_files = _flat_root_files(artifact_root)
    extra_files = sorted(set(root_files) - set(selected_names))
    if extra_files:
        errors.append(f"artifact root contains non-manifest files: {', '.join(extra_files)}")

    if len(candidate_rows) == len(artifacts):
        candidate_manifest["artifacts"] = candidate_rows
        resolved_manifest_out.parent.mkdir(parents=True, exist_ok=True)
        resolved_manifest_out.write_text(json.dumps(candidate_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    copied = sum(1 for action in plan_actions if action["status"] == "copied")
    return {
        "ok": not errors,
        "write": True,
        "release_tag": release_tag,
        "generated_at": timestamp,
        "manifest": str(manifest_path),
        "manifest_out": str(resolved_manifest_out),
        "artifact_root": str(artifact_root),
        "work_dir": str(resolved_work_dir),
        "skip_registry_generation": skip_registry_generation,
        "generation_command": generation_command,
        "actions": plan_actions,
        "extra_files": extra_files,
        "errors": errors,
        "totals": {"selected_assets": len(artifacts), "copied": copied, "errors": len(errors)},
    }


def _print_text(result: dict[str, Any]) -> None:
    status = "ok" if result["ok"] else "failed"
    mode = "write" if result["write"] else "dry-run"
    print(f"Release publication candidate {status} ({mode})")
    print(f"Artifact root: {result['artifact_root']}")
    print(f"Work dir: {result['work_dir']}")
    print(f"Manifest out: {result['manifest_out']}")
    for action in result["actions"]:
        print(f"- {action['asset_name']}: {action['status']} {action['source']} -> {action['destination']}")
    for error in result["errors"]:
        print(f"  error: {error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate signed release/project registries in a private work dir, copy the "
            "manifest-listed public artifacts into a flat upload root, and emit a "
            "candidate manifest with updated SHA/bytes."
        )
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--skip-registry-generation", action="store_true")
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = build_release_publication_candidate(
            manifest_path=args.manifest,
            artifact_root=args.artifact_root,
            work_dir=args.work_dir,
            manifest_out=args.manifest_out,
            generated_at=args.generated_at,
            write=args.write,
            skip_registry_generation=args.skip_registry_generation,
            python_executable=args.python_executable,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "errors": [str(exc)], "actions": [], "write": args.write}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
