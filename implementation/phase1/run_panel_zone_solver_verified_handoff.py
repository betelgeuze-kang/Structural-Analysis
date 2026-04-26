#!/usr/bin/env python3
"""Run the panel-zone solver-verified handoff chain.

This helper is intentionally conservative:

1. By default it only regenerates the panel-zone source/contracts/artifact/report chain.
2. Live release-facing refresh is opt-in.
3. External validation refresh is a second opt-in because that script prunes bundle history by default.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any


ROOT = Path("implementation/phase1")
RELEASE_DIR = ROOT / "release"

DEFAULT_DATASET = RELEASE_DIR / "design_optimization" / "design_optimization_dataset_report.json"
DEFAULT_PBD_PACKAGE = RELEASE_DIR / "pbd_review" / "pbd_review_package_report.json"

DEFAULT_BUNDLE_OUT = ROOT / "panel_zone_solver_verified_export_bundle.json"
DEFAULT_PANEL_ZONE_INBOX = ROOT / "inbox" / "panel_zone_solver_verified"
DEFAULT_TRUSTED_SOURCE_ORIGIN_CLASS = "trusted_external_solver_source"
TRUSTED_RELEASE_REFRESH_SOURCE_ORIGINS = frozenset({DEFAULT_TRUSTED_SOURCE_ORIGIN_CLASS})
DEFAULT_JOINT_SOURCE_OUT = ROOT / "panel_zone_joint_geometry_3d.json"
DEFAULT_ANCHORAGE_SOURCE_OUT = ROOT / "panel_zone_rebar_anchorage_3d.json"
DEFAULT_CLASH_SOURCE_OUT = ROOT / "panel_zone_clash_verification_3d.json"
DEFAULT_JOINT_CONTRACT_OUT = ROOT / "panel_zone_joint_geometry_3d_contract.json"
DEFAULT_ANCHORAGE_CONTRACT_OUT = ROOT / "panel_zone_rebar_anchorage_3d_contract.json"
DEFAULT_CLASH_CONTRACT_OUT = ROOT / "panel_zone_clash_verification_3d_contract.json"
DEFAULT_CLASH_ARTIFACT_OUT = ROOT / "panel_zone_clash_artifact.json"
DEFAULT_CLASH_REPORT_OUT = ROOT / "panel_zone_clash_report.json"
DEFAULT_OUT = ROOT / "panel_zone_solver_verified_handoff_report.json"

DEFAULT_RELEASE_GAP_JSON = RELEASE_DIR / "release_gap_report.json"
DEFAULT_RELEASE_GAP_MD = RELEASE_DIR / "release_gap_report.md"
DEFAULT_RELEASE_REGISTRY = RELEASE_DIR / "release_registry.json"
DEFAULT_RELEASE_PRIVATE_KEY = RELEASE_DIR / "signing" / "release_registry_ed25519.pem"
DEFAULT_RELEASE_PUBLIC_KEY = RELEASE_DIR / "signing" / "release_registry_ed25519.pub.pem"
DEFAULT_RELEASE_SIGNATURE = RELEASE_DIR / "signing" / "release_registry.signature.b64"
DEFAULT_COMMITTEE_OUT_DIR = RELEASE_DIR / "committee_review"
DEFAULT_EXTERNAL_LATEST = RELEASE_DIR / "external_validation_latest.json"
DEFAULT_EXTERNAL_LIGHT_LATEST = RELEASE_DIR / "external_validation_light_latest.json"

REASONS = {
    "PASS": "panel-zone solver-verified handoff chain passed",
    "ERR_INPUT_MODE": "choose exactly one input mode: either a prebuilt bundle or all three raw source JSONs",
    "ERR_INPUT_MISSING": "one or more required input files are missing",
    "ERR_STEP_FAIL": "one or more orchestration steps failed to execute",
    "ERR_PANEL_CHAIN_OPEN": "panel-zone handoff steps executed, but the final clash report is not green",
    "ERR_RELEASE_REFRESH_FAIL": "panel-zone handoff passed, but live release-facing refresh failed",
    "ERR_RELEASE_REFRESH_SOURCE_UNCLASSIFIED": "panel-zone handoff passed, but live release-facing refresh is blocked for unclassified solver input provenance",
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _json_green(path: Path) -> bool:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return False
    if "contract_pass" in payload:
        return bool(payload.get("contract_pass", False))
    if "all_pass" in payload:
        return bool(payload.get("all_pass", False))
    return False


def _run_step(step: str, cmd: list[str], *, dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "step": step,
            "command": shlex.join(cmd),
            "return_code": 0,
            "ok": True,
            "status": "dry_run",
            "stdout_tail": "",
            "stderr_tail": "",
        }
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    return {
        "step": step,
        "command": shlex.join(cmd),
        "return_code": int(proc.returncode),
        "ok": bool(proc.returncode == 0),
        "status": "ok" if proc.returncode == 0 else "failed",
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def _append_step(rows: list[dict], step: str, cmd: list[str], *, dry_run: bool = False) -> bool:
    row = _run_step(step, cmd, dry_run=dry_run)
    rows.append(row)
    return bool(row["ok"])


def _bundle_out_path(args: argparse.Namespace) -> Path:
    if str(args.solver_verified_bundle_out).strip():
        return Path(args.solver_verified_bundle_out)
    joint_parent = Path(args.panel_zone_joint_geometry_source_output).parent
    if str(joint_parent).strip():
        return joint_parent / "panel_zone_solver_verified_export_bundle.json"
    return DEFAULT_BUNDLE_OUT


def _required_missing(path_strings: list[str]) -> list[str]:
    missing: list[str] = []
    for raw in path_strings:
        value = str(raw).strip()
        if value and not Path(value).exists():
            missing.append(value)
    return missing


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _bundle_source_origin_class(path: Path) -> str:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        return ""
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    solver = payload.get("solver") if isinstance(payload.get("solver"), dict) else {}
    origin = str(
        summary.get("source_origin_class")
        or solver.get("source_origin_class")
        or payload.get("source_origin_class")
        or ""
    ).strip()
    if origin:
        return origin
    if summary or solver or isinstance(payload.get("panel_zone_3d_results"), dict):
        return "unclassified_external_source"
    return ""


def _drop_manifest_candidates(drop_dir: Path) -> tuple[Path, ...]:
    return (
        drop_dir / "panel_zone_handoff_manifest.json",
        drop_dir / "panel_zone_solver_verified_input_manifest.json",
        drop_dir / "manifest.json",
    )


def _load_drop_dir_manifest(drop_dir: Path) -> dict[str, Any]:
    for candidate in _drop_manifest_candidates(drop_dir):
        manifest = _load_json(candidate)
        if manifest:
            return manifest
    return {}


def _drop_dir_source_origin_class(drop_dir: Path) -> str:
    manifest = _load_drop_dir_manifest(drop_dir)
    if not isinstance(manifest, dict):
        return ""
    provenance = manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}
    return str(
        manifest.get("source_origin_class")
        or provenance.get("source_origin_class")
        or ""
    ).strip()


def _release_refresh_source_allowed(source_origin_class: str) -> bool:
    origin = str(source_origin_class or "").strip().lower()
    if not origin:
        return False
    return origin in TRUSTED_RELEASE_REFRESH_SOURCE_ORIGINS


def _discover_from_drop_dir(drop_dir: Path) -> dict[str, str]:
    manifest = _load_drop_dir_manifest(drop_dir)

    key_to_names = {
        "bundle": (
            "panel_zone_solver_verified_export_bundle.json",
            "solver_verified_export_bundle.json",
        ),
        "joint": (
            "joint_geometry.json",
            "joint_geometry_source.json",
        ),
        "anchorage": (
            "rebar_anchorage.json",
            "rebar_anchorage_source.json",
        ),
        "clash": (
            "clash_verification.json",
            "clash_verification_source.json",
        ),
        "member_mapping_sidecar": (
            "member_mapping_sidecar.json",
            "panel_zone_member_mapping_sidecar.json",
        ),
    }

    discovered: dict[str, str] = {}
    manifest_map = manifest.get("inputs", {}) if isinstance(manifest.get("inputs"), dict) else {}
    manifest_aliases = {
        "bundle": ("solver_verified_bundle", "panel_zone_solver_verified_export_bundle", "bundle"),
        "joint": ("joint_geometry_source", "joint_geometry", "panel_zone_joint_geometry_source"),
        "anchorage": ("rebar_anchorage_source", "rebar_anchorage", "panel_zone_rebar_anchorage_source"),
        "clash": ("clash_verification_source", "clash_verification", "panel_zone_clash_verification_source"),
        "member_mapping_sidecar": (
            "member_mapping_sidecar",
            "panel_zone_member_mapping_sidecar",
            "solver_verified_member_mapping_sidecar",
        ),
    }

    for key, aliases in manifest_aliases.items():
        for alias in aliases:
            raw = str(manifest_map.get(alias, "") or "").strip()
            if not raw:
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = drop_dir / candidate
            if candidate.exists():
                discovered[key] = str(candidate.resolve())
                break
        if key in discovered:
            continue
        for name in key_to_names[key]:
            candidate = drop_dir / name
            if candidate.exists():
                discovered[key] = str(candidate.resolve())
                break
    return discovered


def _panel_outputs(args: argparse.Namespace) -> dict[str, str]:
    return {
        "solver_verified_bundle": str(args.solver_verified_bundle_in or _bundle_out_path(args)),
        "panel_zone_joint_geometry_source": str(args.panel_zone_joint_geometry_source_output),
        "panel_zone_rebar_anchorage_source": str(args.panel_zone_rebar_anchorage_source_output),
        "panel_zone_clash_verification_source": str(args.panel_zone_clash_verification_source_output),
        "panel_zone_joint_geometry_contract": str(args.panel_zone_joint_geometry_contract),
        "panel_zone_rebar_anchorage_contract": str(args.panel_zone_rebar_anchorage_contract),
        "panel_zone_clash_verification_contract": str(args.panel_zone_clash_verification_contract),
        "panel_zone_clash_artifact": str(args.panel_zone_clash_artifact_out),
        "panel_zone_clash_report": str(args.panel_zone_clash_report_out),
    }


def _write_report(out: Path, payload: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver-verified-bundle-in", default="")
    parser.add_argument("--solver-verified-bundle-out", default=str(DEFAULT_BUNDLE_OUT))
    parser.add_argument("--panel-zone-solver-verified-export-bundle", default="")
    parser.add_argument("--panel-zone-solver-export-bundle", default="")
    parser.add_argument("--source-drop-dir", default="")
    parser.add_argument("--source-origin-class", default="")
    parser.add_argument("--joint-geometry-source", default="")
    parser.add_argument("--rebar-anchorage-source", default="")
    parser.add_argument("--clash-verification-source", default="")
    parser.add_argument("--member-mapping-sidecar", default="")
    parser.add_argument("--design-optimization-dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--design-optimization-npz", default="")
    parser.add_argument("--pbd-review-package", default=str(DEFAULT_PBD_PACKAGE))
    parser.add_argument("--panel-zone-joint-geometry-source-output", default=str(DEFAULT_JOINT_SOURCE_OUT))
    parser.add_argument("--panel-zone-rebar-anchorage-source-output", default=str(DEFAULT_ANCHORAGE_SOURCE_OUT))
    parser.add_argument("--panel-zone-clash-verification-source-output", default=str(DEFAULT_CLASH_SOURCE_OUT))
    parser.add_argument("--panel-zone-joint-geometry-contract", default=str(DEFAULT_JOINT_CONTRACT_OUT))
    parser.add_argument("--panel-zone-rebar-anchorage-contract", default=str(DEFAULT_ANCHORAGE_CONTRACT_OUT))
    parser.add_argument("--panel-zone-clash-verification-contract", default=str(DEFAULT_CLASH_CONTRACT_OUT))
    parser.add_argument("--panel-zone-clash-artifact-out", default=str(DEFAULT_CLASH_ARTIFACT_OUT))
    parser.add_argument("--panel-zone-clash-report-out", default=str(DEFAULT_CLASH_REPORT_OUT))
    parser.add_argument("--panel-zone-clash-artifact", default="")
    parser.add_argument("--panel-zone-clash-report", default="")
    parser.add_argument("--refresh-release-surfaces", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--refresh-external-validation", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--allow-unclassified-release-refresh", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--external-bundle-id", default="")
    parser.add_argument("--external-emit-lightweight", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--external-prune-old", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    # Backward-compatible aliases
    if str(args.panel_zone_clash_artifact).strip():
        args.panel_zone_clash_artifact_out = str(args.panel_zone_clash_artifact).strip()
    if str(args.panel_zone_clash_report).strip():
        args.panel_zone_clash_report_out = str(args.panel_zone_clash_report).strip()

    discovered_inputs: dict[str, str] = {}
    if str(args.source_drop_dir).strip():
        source_drop_dir = Path(str(args.source_drop_dir).strip())
        discovered_inputs = _discover_from_drop_dir(source_drop_dir)
        if not str(args.source_origin_class).strip():
            args.source_origin_class = _drop_dir_source_origin_class(source_drop_dir)
        if (not str(args.solver_verified_bundle_in).strip()) and discovered_inputs.get("bundle"):
            args.solver_verified_bundle_in = str(discovered_inputs["bundle"])
        if (not str(args.joint_geometry_source).strip()) and discovered_inputs.get("joint"):
            args.joint_geometry_source = str(discovered_inputs["joint"])
        if (not str(args.rebar_anchorage_source).strip()) and discovered_inputs.get("anchorage"):
            args.rebar_anchorage_source = str(discovered_inputs["anchorage"])
        if (not str(args.clash_verification_source).strip()) and discovered_inputs.get("clash"):
            args.clash_verification_source = str(discovered_inputs["clash"])
        if (not str(args.member_mapping_sidecar).strip()) and discovered_inputs.get("member_mapping_sidecar"):
            args.member_mapping_sidecar = str(discovered_inputs["member_mapping_sidecar"])

    alias_bundle = (
        str(args.panel_zone_solver_verified_export_bundle).strip()
        or str(args.panel_zone_solver_export_bundle).strip()
    )
    if alias_bundle:
        raw_seed_count = sum(
            bool(str(value).strip())
            for value in (
                args.joint_geometry_source,
                args.rebar_anchorage_source,
                args.clash_verification_source,
            )
        )
        if raw_seed_count > 0:
            if (not str(args.solver_verified_bundle_out).strip()) or str(args.solver_verified_bundle_out) == str(DEFAULT_BUNDLE_OUT):
                args.solver_verified_bundle_out = alias_bundle
        else:
            if not str(args.solver_verified_bundle_in).strip():
                args.solver_verified_bundle_in = alias_bundle
            if (not str(args.solver_verified_bundle_out).strip()) or str(args.solver_verified_bundle_out) == str(DEFAULT_BUNDLE_OUT):
                args.solver_verified_bundle_out = alias_bundle

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    has_bundle = bool(str(args.solver_verified_bundle_in).strip())
    raw_inputs = [
        str(args.joint_geometry_source).strip(),
        str(args.rebar_anchorage_source).strip(),
        str(args.clash_verification_source).strip(),
    ]
    raw_present_count = sum(bool(value) for value in raw_inputs)
    steps: list[dict] = []
    reason_code = "PASS"
    reason = REASONS["PASS"]
    panel_chain_pass = False
    release_surface_refresh_pass = False
    external_validation_refresh_pass = False

    if bool(args.refresh_external_validation) and not bool(args.refresh_release_surfaces):
        reason_code = "ERR_INPUT_MODE"
        reason = "--refresh-external-validation requires --refresh-release-surfaces"
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-panel-zone-solver-verified-handoff",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": reason,
            "inputs": {**vars(args), "discovered_inputs": discovered_inputs},
            "steps": steps,
            "artifacts": _panel_outputs(args),
        }
        _write_report(out, payload)
        print(f"Wrote panel-zone solver-verified handoff report: {out}")
        raise SystemExit(1)

    if has_bundle == (raw_present_count > 0) or (not has_bundle and raw_present_count not in {0, 3}):
        reason_code = "ERR_INPUT_MODE"
        reason = REASONS[reason_code]
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-panel-zone-solver-verified-handoff",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": reason,
            "inputs": {**vars(args), "discovered_inputs": discovered_inputs},
            "steps": steps,
            "artifacts": _panel_outputs(args),
        }
        _write_report(out, payload)
        print(f"Wrote panel-zone solver-verified handoff report: {out}")
        raise SystemExit(1)

    bundle_path = Path(args.solver_verified_bundle_in) if has_bundle else _bundle_out_path(args)
    input_mode = "prebuilt_bundle" if has_bundle else "raw_sources"
    required_paths = [str(args.design_optimization_dataset), str(args.pbd_review_package)]
    if has_bundle:
        required_paths.append(str(args.solver_verified_bundle_in))
    else:
        required_paths.extend(raw_inputs)
    missing_inputs = _required_missing(required_paths)
    if missing_inputs:
        reason_code = "ERR_INPUT_MISSING"
        reason = f"{REASONS[reason_code]}: {', '.join(missing_inputs)}"
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-panel-zone-solver-verified-handoff",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": reason,
            "inputs": {**vars(args), "discovered_inputs": discovered_inputs},
            "steps": steps,
            "artifacts": _panel_outputs(args),
        }
        _write_report(out, payload)
        print(f"Wrote panel-zone solver-verified handoff report: {out}")
        raise SystemExit(1)

    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    if not has_bundle:
        bundle_source_origin_class = str(args.source_origin_class).strip() or "unclassified_external_source"
        cmd = [
            sys.executable,
            "implementation/phase1/generate_panel_zone_solver_verified_export_bundle.py",
            "--joint-geometry-source",
            str(args.joint_geometry_source),
            "--rebar-anchorage-source",
            str(args.rebar_anchorage_source),
            "--clash-verification-source",
            str(args.clash_verification_source),
            "--source-origin-class",
            bundle_source_origin_class,
        ]
        if str(args.member_mapping_sidecar).strip():
            cmd.extend([
                "--member-mapping-sidecar",
                str(args.member_mapping_sidecar),
            ])
        cmd.extend([
            "--out",
            str(bundle_path),
        ])
        if not _append_step(steps, "panel_zone_solver_verified_bundle", cmd, dry_run=bool(args.dry_run)):
            reason_code = "ERR_STEP_FAIL"
            reason = REASONS[reason_code]

    source_specs = [
        (
            "joint_geometry",
            "implementation/phase1/generate_panel_zone_joint_geometry_3d_source.py",
            Path(args.panel_zone_joint_geometry_source_output),
            Path(args.panel_zone_joint_geometry_contract),
        ),
        (
            "rebar_anchorage",
            "implementation/phase1/generate_panel_zone_rebar_anchorage_3d_source.py",
            Path(args.panel_zone_rebar_anchorage_source_output),
            Path(args.panel_zone_rebar_anchorage_contract),
        ),
        (
            "clash_verification",
            "implementation/phase1/generate_panel_zone_clash_verification_3d_source.py",
            Path(args.panel_zone_clash_verification_source_output),
            Path(args.panel_zone_clash_verification_contract),
        ),
    ]

    if reason_code == "PASS":
        for source_kind, script_path, source_out, contract_out in source_specs:
            source_out.parent.mkdir(parents=True, exist_ok=True)
            source_cmd = [
                sys.executable,
                script_path,
                "--design-optimization-dataset",
                str(args.design_optimization_dataset),
            ]
            if str(args.design_optimization_npz).strip():
                source_cmd.extend(["--design-optimization-npz", str(args.design_optimization_npz)])
            source_cmd.extend(
                [
                    "--source-input",
                    str(bundle_path),
                    "--out",
                    str(source_out),
                ]
            )
            if not _append_step(steps, f"panel_zone_{source_kind}_source", source_cmd, dry_run=bool(args.dry_run)):
                reason_code = "ERR_STEP_FAIL"
                reason = REASONS[reason_code]
                break

            contract_out.parent.mkdir(parents=True, exist_ok=True)
            contract_cmd = [
                sys.executable,
                "implementation/phase1/generate_panel_zone_3d_source_contract.py",
                "--source-kind",
                source_kind,
                "--source-artifact",
                str(source_out),
                "--out",
                str(contract_out),
            ]
            if not _append_step(steps, f"panel_zone_{source_kind}_contract", contract_cmd, dry_run=bool(args.dry_run)):
                reason_code = "ERR_STEP_FAIL"
                reason = REASONS[reason_code]
                break

    clash_artifact_path = Path(args.panel_zone_clash_artifact_out)
    clash_report_path = Path(args.panel_zone_clash_report_out)

    if reason_code == "PASS":
        clash_artifact_path.parent.mkdir(parents=True, exist_ok=True)
        clash_artifact_cmd = [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_artifact.py",
            "--design-optimization-dataset",
            str(args.design_optimization_dataset),
        ]
        if str(args.design_optimization_npz).strip():
            clash_artifact_cmd.extend(["--design-optimization-npz", str(args.design_optimization_npz)])
        clash_artifact_cmd.extend(
            [
                "--panel-zone-joint-geometry-artifact",
                str(args.panel_zone_joint_geometry_contract),
                "--panel-zone-rebar-anchorage-artifact",
                str(args.panel_zone_rebar_anchorage_contract),
                "--panel-zone-clash-verification-artifact",
                str(args.panel_zone_clash_verification_contract),
                "--out",
                str(clash_artifact_path),
            ]
        )
        if not _append_step(steps, "panel_zone_clash_artifact", clash_artifact_cmd, dry_run=bool(args.dry_run)):
            reason_code = "ERR_STEP_FAIL"
            reason = REASONS[reason_code]

    if reason_code == "PASS":
        clash_report_path.parent.mkdir(parents=True, exist_ok=True)
        clash_report_cmd = [
            sys.executable,
            "implementation/phase1/generate_panel_zone_clash_report.py",
            "--design-optimization-dataset",
            str(args.design_optimization_dataset),
            "--pbd-review-package",
            str(args.pbd_review_package),
            "--panel-zone-clash-artifact",
            str(clash_artifact_path),
            "--out",
            str(clash_report_path),
        ]
        if not _append_step(steps, "panel_zone_clash_report", clash_report_cmd, dry_run=bool(args.dry_run)):
            reason_code = "ERR_STEP_FAIL"
            reason = REASONS[reason_code]

    if bool(args.dry_run):
        bundle_green = True
        source_green = True
        contract_green = True
        clash_artifact_green = True
        clash_report_green = True
    else:
        bundle_green = True if has_bundle else _json_green(bundle_path)
        source_green = all(_json_green(Path(path)) for path in (
            args.panel_zone_joint_geometry_source_output,
            args.panel_zone_rebar_anchorage_source_output,
            args.panel_zone_clash_verification_source_output,
        ))
        contract_green = all(_json_green(Path(path)) for path in (
            args.panel_zone_joint_geometry_contract,
            args.panel_zone_rebar_anchorage_contract,
            args.panel_zone_clash_verification_contract,
        ))
        clash_artifact_green = _json_green(clash_artifact_path)
        clash_report_green = _json_green(clash_report_path)
    if bool(args.dry_run):
        if has_bundle:
            source_origin_class = _bundle_source_origin_class(bundle_path)
        else:
            source_origin_class = str(args.source_origin_class).strip() or "unclassified_external_source"
    else:
        source_origin_class = _bundle_source_origin_class(bundle_path)
    release_refresh_source_allowed = bool(
        _release_refresh_source_allowed(source_origin_class) or bool(args.allow_unclassified_release_refresh)
    )
    panel_chain_pass = bool(
        reason_code == "PASS"
        and bundle_green
        and source_green
        and contract_green
        and clash_artifact_green
        and clash_report_green
    )
    if reason_code == "PASS" and not panel_chain_pass:
        reason_code = "ERR_PANEL_CHAIN_OPEN"
        reason = REASONS[reason_code]

    if (
        reason_code == "PASS"
        and bool(args.refresh_release_surfaces)
        and not bool(args.dry_run)
        and not release_refresh_source_allowed
    ):
        reason_code = "ERR_RELEASE_REFRESH_SOURCE_UNCLASSIFIED"
        reason = (
            f"{REASONS[reason_code]}: source_origin_class="
            f"{source_origin_class or 'missing'}"
        )

    if reason_code == "PASS" and bool(args.refresh_release_surfaces):
        release_gap_cmd = [
            sys.executable,
            "implementation/phase1/generate_release_gap_report.py",
            "--panel-zone-clash-report",
            str(clash_report_path),
            "--out-json",
            str(DEFAULT_RELEASE_GAP_JSON),
            "--out-md",
            str(DEFAULT_RELEASE_GAP_MD),
        ]
        registry_pass1_cmd = [
            sys.executable,
            "implementation/phase1/generate_signed_release_registry.py",
            "--gap-report",
            str(DEFAULT_RELEASE_GAP_JSON),
            "--committee-package",
            str(DEFAULT_COMMITTEE_OUT_DIR / "committee_review_package_report.json"),
            "--committee-summary",
            str(DEFAULT_COMMITTEE_OUT_DIR / "committee_summary.json"),
            "--private-key-out",
            str(DEFAULT_RELEASE_PRIVATE_KEY),
            "--public-key-out",
            str(DEFAULT_RELEASE_PUBLIC_KEY),
            "--signature-out",
            str(DEFAULT_RELEASE_SIGNATURE),
            "--out",
            str(DEFAULT_RELEASE_REGISTRY),
        ]
        committee_cmd = [
            sys.executable,
            "implementation/phase1/generate_committee_review_package.py",
            "--gap-report",
            str(DEFAULT_RELEASE_GAP_JSON),
            "--release-registry",
            str(DEFAULT_RELEASE_REGISTRY),
            "--out-dir",
            str(DEFAULT_COMMITTEE_OUT_DIR),
        ]
        registry_pass2_cmd = registry_pass1_cmd[:]

        release_steps = [
            ("release_gap_report", release_gap_cmd),
            ("release_registry_pass1", registry_pass1_cmd),
            ("committee_review_package", committee_cmd),
            ("release_registry_pass2", registry_pass2_cmd),
        ]
        release_surface_refresh_pass = True
        for step_name, cmd in release_steps:
            if not _append_step(steps, step_name, cmd, dry_run=bool(args.dry_run)):
                release_surface_refresh_pass = False
                break
        if release_surface_refresh_pass and bool(args.refresh_external_validation):
            external_cmd = [
                sys.executable,
                "implementation/phase1/prepare_external_validation_submission.py",
                "--release-dir",
                str(RELEASE_DIR),
                "--latest-pointer",
                str(DEFAULT_EXTERNAL_LATEST),
                "--light-latest-pointer",
                str(DEFAULT_EXTERNAL_LIGHT_LATEST),
            ]
            if str(args.external_bundle_id).strip():
                external_cmd.extend(["--bundle-id", str(args.external_bundle_id).strip()])
            external_cmd.extend(
                [
                    "--emit-lightweight" if bool(args.external_emit_lightweight) else "--no-emit-lightweight",
                    "--prune-old" if bool(args.external_prune_old) else "--no-prune-old",
                ]
            )
            external_validation_refresh_pass = _append_step(
                steps,
                "external_validation_submission",
                external_cmd,
                dry_run=bool(args.dry_run),
            )
            release_surface_refresh_pass = bool(release_surface_refresh_pass and external_validation_refresh_pass)

        if not release_surface_refresh_pass:
            reason_code = "ERR_RELEASE_REFRESH_FAIL"
            reason = REASONS[reason_code]
    else:
        release_surface_refresh_pass = not bool(args.refresh_release_surfaces)
        external_validation_refresh_pass = not bool(args.refresh_external_validation)

    clash_report_payload = {} if bool(args.dry_run) else _load_json(clash_report_path)
    clash_report_summary = clash_report_payload.get("summary", {}) if isinstance(clash_report_payload.get("summary"), dict) else {}

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-solver-verified-handoff",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            **vars(args),
            "input_mode": input_mode,
            "solver_verified_bundle_effective": str(bundle_path),
            "discovered_inputs": discovered_inputs,
        },
        "checks": {
            "bundle_green": bool(bundle_green),
            "source_green": bool(source_green),
            "contract_green": bool(contract_green),
            "clash_artifact_green": bool(clash_artifact_green),
            "clash_report_green": bool(clash_report_green),
            "panel_chain_pass": bool(panel_chain_pass),
            "release_surface_refresh_pass": bool(release_surface_refresh_pass),
            "external_validation_refresh_pass": bool(external_validation_refresh_pass),
            "release_refresh_source_allowed": bool(release_refresh_source_allowed),
        },
        "summary": {
            "input_mode": input_mode,
            "source_input_mode": input_mode,
            "panel_chain_pass": bool(panel_chain_pass),
            "source_origin_class": source_origin_class,
            "refresh_release_surfaces": bool(args.refresh_release_surfaces),
            "refresh_external_validation": bool(args.refresh_external_validation),
            "allow_unclassified_release_refresh": bool(args.allow_unclassified_release_refresh),
            "release_surface_refresh_guard_status": (
                "allowed"
                if bool(release_refresh_source_allowed)
                else "blocked_unclassified_source"
            ),
            "release_surface_refresh_model": (
                "gap -> registry -> committee -> gap -> registry -> external"
                if bool(args.refresh_release_surfaces)
                else "panel_only"
            ),
            "panel_zone_constructability_mode": str(clash_report_summary.get("constructability_mode", "") or ""),
            "panel_zone_source_contract_mode": str(clash_report_summary.get("panel_zone_source_contract_mode", "") or ""),
            "validated_source_row_count_total": _safe_int(
                clash_report_summary.get("panel_zone_validated_source_row_count_total", 0),
                0,
            ),
            "validated_source_overlap_member_count_min": _safe_int(
                clash_report_summary.get("panel_zone_validated_source_overlap_member_count_min", 0),
                0,
            ),
        },
        "artifacts": {
            **_panel_outputs(args),
            "release_gap_report_json": str(DEFAULT_RELEASE_GAP_JSON),
            "release_gap_report_md": str(DEFAULT_RELEASE_GAP_MD),
            "release_registry": str(DEFAULT_RELEASE_REGISTRY),
            "committee_out_dir": str(DEFAULT_COMMITTEE_OUT_DIR),
            "external_release_dir": str(RELEASE_DIR),
            "external_validation_latest": str(DEFAULT_EXTERNAL_LATEST),
            "external_validation_light_latest": str(DEFAULT_EXTERNAL_LIGHT_LATEST),
        },
        "steps": steps,
    }
    _write_report(out, payload)
    print(f"Wrote panel-zone solver-verified handoff report: {out}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
