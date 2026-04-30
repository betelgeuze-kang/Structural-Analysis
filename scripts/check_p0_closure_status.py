#!/usr/bin/env python3
"""Summarize P0 closure status from release and core gate evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_release_p0_closure import build_status as build_release_status  # noqa: E402


DEFAULT_REPORTS = {
    "p0_2_midas_exact_roundtrip": Path("implementation/phase1/midas_exact_roundtrip_closure_gate_report.json"),
    "p0_3_kds_load_combination": Path("implementation/phase1/load_combination_engine_gate_report.json"),
    "p0_4_midas_kds_geometry_identity": Path("implementation/phase1/midas_kds_geometry_bridge_validation_report.json"),
    "p0_5_material_constitutive": Path("implementation/phase1/material_constitutive_gate_report.json"),
    "p0_5_steel_composite_constitutive": Path("implementation/phase1/steel_composite_constitutive_gate_report.json"),
    "p0_6_solver_breadth": Path("implementation/phase1/solver_breadth_report.json"),
    "p0_6_element_material_breadth": Path("implementation/phase1/element_material_breadth_gate_report.json"),
    "p0_6_structural_contact": Path("implementation/phase1/structural_contact_gate_report.json"),
    "p0_6_general_fe_contact": Path("implementation/phase1/general_fe_contact_benchmark_gate_report.json"),
    "p0_6_solver_truthfulness": Path("implementation/phase1/solver_truthfulness_gate_report.json"),
}
DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _report_pass(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("contract_pass"), bool):
        return bool(payload["contract_pass"])
    if isinstance(payload.get("all_pass"), bool):
        return bool(payload["all_pass"])
    if isinstance(payload.get("pass"), bool):
        return bool(payload["pass"])
    return False


def _summary_line(payload: dict[str, Any]) -> str:
    direct = str(payload.get("summary_line", "") or "").strip()
    if direct:
        return direct
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return str(summary.get("summary_line", "") or "").strip()


def _gate_status(label: str, path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    exists = path.exists()
    ok = bool(exists and _report_pass(payload))
    return {
        "label": label,
        "path": str(path),
        "status": "closed" if ok else "open",
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload),
    }


def _group_status(label: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    ok = bool(children) and all(bool(child.get("ok", False)) for child in children)
    return {
        "label": label,
        "status": "closed" if ok else "open",
        "ok": ok,
        "children": children,
    }


def _release_publication_status(
    *,
    manifest: Path,
    release_assets_json: Path | None,
    artifact_root: Path | None,
    tag_ref_present: bool,
    require_all: bool,
) -> dict[str, Any]:
    if release_assets_json is None:
        return {
            "label": "P0-1 release publication",
            "status": "open",
            "ok": False,
            "reason": "release asset listing was not provided",
            "manifest": str(manifest),
        }
    status = build_release_status(
        manifest_path=manifest,
        artifact_root=artifact_root,
        assets_json=release_assets_json,
        require_all=require_all,
        tag_ref_present=tag_ref_present,
    )
    return {
        "label": "P0-1 release publication",
        "status": "closed" if bool(status.get("p0_closed", False)) else "open",
        "ok": bool(status.get("p0_closed", False)),
        "manifest": str(manifest),
        "release_assets_json": str(release_assets_json),
        "artifact_root": str(artifact_root) if artifact_root else "",
        "details": status,
    }


def build_status(
    *,
    manifest: Path = DEFAULT_MANIFEST,
    release_assets_json: Path | None = None,
    artifact_root: Path | None = None,
    tag_ref_present: bool = False,
    require_all: bool = True,
    reports: dict[str, Path] | None = None,
) -> dict[str, Any]:
    report_paths = reports or DEFAULT_REPORTS
    release = _release_publication_status(
        manifest=manifest,
        release_assets_json=release_assets_json,
        artifact_root=artifact_root,
        tag_ref_present=tag_ref_present,
        require_all=require_all,
    )
    midas_exact = _gate_status("P0-2 MIDAS exact roundtrip", report_paths["p0_2_midas_exact_roundtrip"])
    load_combination = _gate_status("P0-3 KDS load combination", report_paths["p0_3_kds_load_combination"])
    geometry = _gate_status("P0-4 MIDAS-KDS geometry identity", report_paths["p0_4_midas_kds_geometry_identity"])
    constitutive = _group_status(
        "P0-5 constitutive libraries",
        [
            _gate_status("Material constitutive", report_paths["p0_5_material_constitutive"]),
            _gate_status("Steel/composite constitutive", report_paths["p0_5_steel_composite_constitutive"]),
        ],
    )
    solver = _group_status(
        "P0-6 element / solver engine",
        [
            _gate_status("Solver breadth", report_paths["p0_6_solver_breadth"]),
            _gate_status("Element/material breadth", report_paths["p0_6_element_material_breadth"]),
            _gate_status("Structural contact", report_paths["p0_6_structural_contact"]),
            _gate_status("General FE contact", report_paths["p0_6_general_fe_contact"]),
            _gate_status("Solver truthfulness", report_paths["p0_6_solver_truthfulness"]),
        ],
    )
    gates = [release, midas_exact, load_combination, geometry, constitutive, solver]
    core_gates = [midas_exact, load_combination, geometry, constitutive, solver]
    return {
        "schema_version": "p0-closure-status.v1",
        "status": "closed" if all(bool(gate.get("ok", False)) for gate in gates) else "open",
        "p0_closed": all(bool(gate.get("ok", False)) for gate in gates),
        "core_evidence_closed": all(bool(gate.get("ok", False)) for gate in core_gates),
        "release_publication_closed": bool(release.get("ok", False)),
        "gates": gates,
        "next_action": (
            "run Publish Release Assets workflow or provide release asset listing"
            if not bool(release.get("ok", False))
            else "promote release manifest and proceed to P1/P2 breadth work"
        ),
    }


def _markdown(status: dict[str, Any]) -> str:
    lines = [
        "# P0 Closure Status",
        "",
        f"- Overall P0: `{status['status']}`",
        f"- Release publication closed: `{bool(status['release_publication_closed'])}`",
        f"- Core evidence closed: `{bool(status['core_evidence_closed'])}`",
        f"- Next action: `{status['next_action']}`",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for gate in status["gates"]:
        children = gate.get("children")
        if isinstance(children, list):
            evidence = "; ".join(
                str(child.get("summary_line", "") or child.get("path", ""))
                for child in children
                if isinstance(child, dict)
            )
        else:
            evidence = str(gate.get("summary_line", "") or gate.get("reason", "") or gate.get("manifest", ""))
        lines.append(f"| {gate['label']} | `{gate['status']}` | {evidence} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize P0 closure state from local evidence.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--release-assets-json", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--tag-ref-present", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--fail-open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        status = build_status(
            manifest=args.manifest,
            release_assets_json=args.release_assets_json,
            artifact_root=args.artifact_root,
            tag_ref_present=bool(args.tag_ref_present),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P0 closure status check failed: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(status), encoding="utf-8")
    print(payload if args.json else _markdown(status))
    return 1 if args.fail_open and not bool(status.get("p0_closed", False)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
