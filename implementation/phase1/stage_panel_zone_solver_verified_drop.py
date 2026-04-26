#!/usr/bin/env python3
"""Stage panel-zone solver-verified inputs into the default inbox."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from run_panel_zone_solver_verified_handoff import (
    DEFAULT_PANEL_ZONE_INBOX,
    _bundle_source_origin_class,
    _discover_from_drop_dir,
    _drop_dir_source_origin_class,
)


REASONS = {
    "PASS": "panel-zone solver-verified inputs staged",
    "ERR_INPUT_MODE": "provide either a bundle, a source drop directory, or all three raw source files",
    "ERR_INPUT_MISSING": "one or more staging inputs are missing",
}


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-drop-dir", default="")
    parser.add_argument("--source-origin-class", default="")
    parser.add_argument("--solver-verified-bundle", default="")
    parser.add_argument("--joint-geometry-source", default="")
    parser.add_argument("--rebar-anchorage-source", default="")
    parser.add_argument("--clash-verification-source", default="")
    parser.add_argument("--member-mapping-sidecar", default="")
    parser.add_argument("--inbox-dir", default=str(DEFAULT_PANEL_ZONE_INBOX))
    parser.add_argument("--clean", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--out", default="implementation/phase1/inbox/panel_zone_solver_verified/stage_report.json")
    args = parser.parse_args()

    explicit_bundle = str(args.solver_verified_bundle).strip()
    explicit_joint = str(args.joint_geometry_source).strip()
    explicit_anchorage = str(args.rebar_anchorage_source).strip()
    explicit_clash = str(args.clash_verification_source).strip()
    explicit_member_mapping_sidecar = str(args.member_mapping_sidecar).strip()
    explicit_drop_dir = str(args.source_drop_dir).strip()
    explicit_source_origin_class = str(args.source_origin_class).strip()

    discovered: dict[str, str] = {}
    if explicit_drop_dir:
        discovered = _discover_from_drop_dir(Path(explicit_drop_dir))

    bundle = explicit_bundle or str(discovered.get("bundle", "") or "")
    joint = explicit_joint or str(discovered.get("joint", "") or "")
    anchorage = explicit_anchorage or str(discovered.get("anchorage", "") or "")
    clash = explicit_clash or str(discovered.get("clash", "") or "")
    member_mapping_sidecar = explicit_member_mapping_sidecar or str(discovered.get("member_mapping_sidecar", "") or "")
    source_origin_class = explicit_source_origin_class
    if not source_origin_class and explicit_drop_dir:
        source_origin_class = _drop_dir_source_origin_class(Path(explicit_drop_dir))
    if not source_origin_class and bundle:
        source_origin_class = _bundle_source_origin_class(Path(bundle))

    has_bundle = bool(bundle)
    raw_count = sum(bool(v) for v in (joint, anchorage, clash))
    if has_bundle and raw_count:
        reason_code = "ERR_INPUT_MODE"
        reason = REASONS[reason_code]
    elif not has_bundle and raw_count not in {0, 3}:
        reason_code = "ERR_INPUT_MODE"
        reason = REASONS[reason_code]
    elif not has_bundle and raw_count == 0:
        reason_code = "ERR_INPUT_MODE"
        reason = REASONS[reason_code]
    else:
        reason_code = "PASS"
        reason = REASONS[reason_code]

    missing_inputs: list[str] = []
    for raw in ([bundle] if has_bundle else [joint, anchorage, clash]):
        if raw and not Path(raw).exists():
            missing_inputs.append(raw)
    if member_mapping_sidecar and not Path(member_mapping_sidecar).exists():
        missing_inputs.append(member_mapping_sidecar)
    if reason_code == "PASS" and missing_inputs:
        reason_code = "ERR_INPUT_MISSING"
        reason = f"{REASONS[reason_code]}: {', '.join(missing_inputs)}"

    inbox = Path(args.inbox_dir)
    manifest_path = inbox / "panel_zone_handoff_manifest.json"
    bundle_path = inbox / "panel_zone_solver_verified_export_bundle.json"
    joint_path = inbox / "joint_geometry.json"
    anchorage_path = inbox / "rebar_anchorage.json"
    clash_path = inbox / "clash_verification.json"
    member_mapping_sidecar_path = inbox / "member_mapping_sidecar.json"

    staged_files: dict[str, str] = {}
    if reason_code == "PASS":
        inbox.mkdir(parents=True, exist_ok=True)
        if bool(args.clean):
            for candidate in (manifest_path, bundle_path, joint_path, anchorage_path, clash_path, member_mapping_sidecar_path):
                if candidate.exists():
                    candidate.unlink()
        if has_bundle:
            _copy(Path(bundle), bundle_path)
            if member_mapping_sidecar:
                _copy(Path(member_mapping_sidecar), member_mapping_sidecar_path)
            manifest = {
                "source_origin_class": source_origin_class or "unclassified_external_source",
                "inputs": {
                    "solver_verified_bundle": bundle_path.name,
                },
            }
            if member_mapping_sidecar:
                manifest["inputs"]["member_mapping_sidecar"] = member_mapping_sidecar_path.name
            _write_json(manifest_path, manifest)
            staged_files["bundle"] = str(bundle_path)
            if member_mapping_sidecar:
                staged_files["member_mapping_sidecar"] = str(member_mapping_sidecar_path)
            staged_files["manifest"] = str(manifest_path)
        else:
            _copy(Path(joint), joint_path)
            _copy(Path(anchorage), anchorage_path)
            _copy(Path(clash), clash_path)
            if member_mapping_sidecar:
                _copy(Path(member_mapping_sidecar), member_mapping_sidecar_path)
            manifest = {
                "source_origin_class": source_origin_class or "unclassified_external_source",
                "inputs": {
                    "joint_geometry_source": joint_path.name,
                    "rebar_anchorage_source": anchorage_path.name,
                    "clash_verification_source": clash_path.name,
                }
            }
            if member_mapping_sidecar:
                manifest["inputs"]["member_mapping_sidecar"] = member_mapping_sidecar_path.name
            _write_json(manifest_path, manifest)
            staged_files["joint"] = str(joint_path)
            staged_files["anchorage"] = str(anchorage_path)
            staged_files["clash"] = str(clash_path)
            if member_mapping_sidecar:
                staged_files["member_mapping_sidecar"] = str(member_mapping_sidecar_path)
            staged_files["manifest"] = str(manifest_path)

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-stage-panel-zone-solver-verified-drop",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "source_drop_dir": explicit_drop_dir,
            "solver_verified_bundle": explicit_bundle,
            "joint_geometry_source": explicit_joint,
            "rebar_anchorage_source": explicit_anchorage,
            "clash_verification_source": explicit_clash,
            "member_mapping_sidecar": explicit_member_mapping_sidecar,
            "source_origin_class": source_origin_class,
            "discovered_inputs": discovered,
            "inbox_dir": str(inbox),
            "clean": bool(args.clean),
        },
        "summary": {
            "source_origin_class": source_origin_class,
        },
        "artifacts": staged_files,
    }
    _write_json(Path(args.out), payload)
    print(f"Wrote panel-zone staging report: {args.out}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
