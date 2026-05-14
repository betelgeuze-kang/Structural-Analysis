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
DEFAULT_REPORT_FALLBACKS = {
    "p0_2_midas_exact_roundtrip": (
        Path("implementation/phase1/release_evidence/midas/midas_exact_roundtrip_closure_gate_report.json"),
    ),
    "p0_3_kds_load_combination": (
        Path("implementation/phase1/release_evidence/midas/load_combination_engine_gate_report.json"),
    ),
    "p0_4_midas_kds_geometry_identity": (
        Path("implementation/phase1/release_evidence/midas/midas_kds_geometry_bridge_validation_report.json"),
    ),
    "p0_5_material_constitutive": (
        Path("implementation/phase1/release_evidence/surface/material_constitutive_gate_report.json"),
    ),
    "p0_5_steel_composite_constitutive": (
        Path("implementation/phase1/release_evidence/surface/steel_composite_constitutive_gate_report.json"),
    ),
    "p0_6_solver_breadth": (
        Path("implementation/phase1/release_evidence/surface/solver_breadth_report.json"),
    ),
    "p0_6_element_material_breadth": (
        Path("implementation/phase1/release_evidence/surface/element_material_breadth_gate_report.json"),
    ),
    "p0_6_structural_contact": (
        Path("implementation/phase1/release_evidence/surface/structural_contact_gate_report.json"),
    ),
    "p0_6_general_fe_contact": (
        Path("implementation/phase1/release_evidence/surface/general_fe_contact_benchmark_gate_report.json"),
    ),
    "p0_6_solver_truthfulness": (
        Path("implementation/phase1/release_evidence/surface/solver_truthfulness_gate_report.json"),
    ),
}
DEFAULT_MANIFEST = Path("implementation/phase1/release_artifacts_manifest.json")
DEFAULT_PUBLICATION_EVIDENCE_INDEX = Path(
    "implementation/phase1/release/publication_evidence/current/release-publication-evidence-index.json"
)
PUBLICATION_EVIDENCE_INDEX_SCHEMA = "release-publication-evidence-index.v1"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _publication_index_paths(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = _load_json(path)
    if payload.get("schema_version") != PUBLICATION_EVIDENCE_INDEX_SCHEMA:
        raise ValueError(f"publication evidence index has unsupported schema: {path}")
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"publication evidence index paths must be an object: {path}")

    def resolve(value: object) -> Path | None:
        if not value:
            return None
        candidate = Path(str(value))
        if candidate.exists():
            return candidate
        sibling = path.parent / candidate.name
        return sibling if sibling.exists() else candidate

    return {
        "manifest": resolve(paths.get("manifest")),
        "promoted_manifest_json": resolve(paths.get("promoted_manifest_json")),
        "release_assets_json": resolve(paths.get("release_assets_json")),
        "artifact_root": resolve(paths.get("artifact_root")),
        "upload_plan_json": resolve(paths.get("upload_plan_json")),
        "metadata_preflight_json": resolve(paths.get("metadata_preflight_json")),
        "post_publish_roundtrip_json": resolve(paths.get("post_publish_roundtrip_json")),
        "p0_status_json": resolve(paths.get("p0_status_json")),
        "tag_ref_present": bool(payload.get("tag_ref_present", False)),
    }


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


def _first_existing_path(path: Path, fallback_paths: tuple[Path, ...]) -> Path:
    if path.exists():
        return path
    for fallback_path in fallback_paths:
        if fallback_path.exists():
            return fallback_path
    return path


def _gate_status(label: str, path: Path, fallback_paths: tuple[Path, ...] = ()) -> dict[str, Any]:
    evidence_path = _first_existing_path(path, fallback_paths)
    payload = _load_json(evidence_path)
    exists = evidence_path.exists()
    ok = bool(exists and _report_pass(payload))
    return {
        "label": label,
        "path": str(evidence_path),
        "primary_path": str(path),
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
    promoted_manifest_json: Path | None,
    release_assets_json: Path | None,
    artifact_root: Path | None,
    upload_plan_json: Path | None,
    metadata_preflight_json: Path | None,
    post_publish_roundtrip_json: Path | None,
    tag_ref_present: bool,
    require_all: bool,
    require_exact: bool,
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
        promoted_manifest_json=promoted_manifest_json,
        artifact_root=artifact_root,
        assets_json=release_assets_json,
        upload_plan_json=upload_plan_json,
        metadata_preflight_json=metadata_preflight_json,
        post_publish_roundtrip_json=post_publish_roundtrip_json,
        require_all=require_all,
        require_exact=require_exact,
        tag_ref_present=tag_ref_present,
    )
    return {
        "label": "P0-1 release publication",
        "status": "closed" if bool(status.get("p0_closed", False)) else "open",
        "ok": bool(status.get("p0_closed", False)),
        "manifest": str(manifest),
        "promoted_manifest_json": str(promoted_manifest_json) if promoted_manifest_json else "",
        "release_assets_json": str(release_assets_json),
        "artifact_root": str(artifact_root) if artifact_root else "",
        "post_publish_roundtrip_json": str(post_publish_roundtrip_json) if post_publish_roundtrip_json else "",
        "details": status,
    }


def build_status(
    *,
    manifest: Path | None = None,
    promoted_manifest_json: Path | None = None,
    release_assets_json: Path | None = None,
    artifact_root: Path | None = None,
    upload_plan_json: Path | None = None,
    metadata_preflight_json: Path | None = None,
    post_publish_roundtrip_json: Path | None = None,
    tag_ref_present: bool = False,
    require_all: bool = True,
    require_exact: bool = True,
    reports: dict[str, Path] | None = None,
    publication_evidence_index: Path | None = None,
) -> dict[str, Any]:
    manifest = manifest or DEFAULT_MANIFEST
    release_inputs_provided = any(
        value is not None
        for value in (
            promoted_manifest_json,
            release_assets_json,
            artifact_root,
            upload_plan_json,
            metadata_preflight_json,
            post_publish_roundtrip_json,
        )
    )
    default_publication_evidence_index_missing = False
    if (
        publication_evidence_index is None
        and manifest == DEFAULT_MANIFEST
        and not release_inputs_provided
    ):
        if DEFAULT_PUBLICATION_EVIDENCE_INDEX.exists():
            publication_evidence_index = DEFAULT_PUBLICATION_EVIDENCE_INDEX
        else:
            default_publication_evidence_index_missing = True
    index_paths = _publication_index_paths(publication_evidence_index)
    manifest = index_paths.get("manifest") or manifest
    promoted_manifest_json = index_paths.get("promoted_manifest_json") or promoted_manifest_json
    release_assets_json = index_paths.get("release_assets_json") or release_assets_json
    artifact_root = index_paths.get("artifact_root") or artifact_root
    upload_plan_json = index_paths.get("upload_plan_json") or upload_plan_json
    metadata_preflight_json = index_paths.get("metadata_preflight_json") or metadata_preflight_json
    post_publish_roundtrip_json = index_paths.get("post_publish_roundtrip_json") or post_publish_roundtrip_json
    tag_ref_present = bool(index_paths.get("tag_ref_present", tag_ref_present))
    report_paths = reports or DEFAULT_REPORTS
    report_fallbacks = {} if reports is not None else DEFAULT_REPORT_FALLBACKS
    release = _release_publication_status(
        manifest=manifest,
        promoted_manifest_json=promoted_manifest_json,
        release_assets_json=release_assets_json,
        artifact_root=artifact_root,
        upload_plan_json=upload_plan_json,
        metadata_preflight_json=metadata_preflight_json,
        post_publish_roundtrip_json=post_publish_roundtrip_json,
        tag_ref_present=tag_ref_present,
        require_all=require_all,
        require_exact=require_exact,
    )
    if default_publication_evidence_index_missing and not bool(release.get("ok", False)):
        release["reason"] = "default publication evidence missing"
        release["default_publication_evidence_index"] = str(DEFAULT_PUBLICATION_EVIDENCE_INDEX)
    midas_exact = _gate_status(
        "P0-2 MIDAS exact roundtrip",
        report_paths["p0_2_midas_exact_roundtrip"],
        report_fallbacks.get("p0_2_midas_exact_roundtrip", ()),
    )
    load_combination = _gate_status(
        "P0-3 KDS load combination",
        report_paths["p0_3_kds_load_combination"],
        report_fallbacks.get("p0_3_kds_load_combination", ()),
    )
    geometry = _gate_status(
        "P0-4 MIDAS-KDS geometry identity",
        report_paths["p0_4_midas_kds_geometry_identity"],
        report_fallbacks.get("p0_4_midas_kds_geometry_identity", ()),
    )
    constitutive = _group_status(
        "P0-5 constitutive libraries",
        [
            _gate_status(
                "Material constitutive",
                report_paths["p0_5_material_constitutive"],
                report_fallbacks.get("p0_5_material_constitutive", ()),
            ),
            _gate_status(
                "Steel/composite constitutive",
                report_paths["p0_5_steel_composite_constitutive"],
                report_fallbacks.get("p0_5_steel_composite_constitutive", ()),
            ),
        ],
    )
    solver = _group_status(
        "P0-6 element / solver engine",
        [
            _gate_status(
                "Solver breadth",
                report_paths["p0_6_solver_breadth"],
                report_fallbacks.get("p0_6_solver_breadth", ()),
            ),
            _gate_status(
                "Element/material breadth",
                report_paths["p0_6_element_material_breadth"],
                report_fallbacks.get("p0_6_element_material_breadth", ()),
            ),
            _gate_status(
                "Structural contact",
                report_paths["p0_6_structural_contact"],
                report_fallbacks.get("p0_6_structural_contact", ()),
            ),
            _gate_status(
                "General FE contact",
                report_paths["p0_6_general_fe_contact"],
                report_fallbacks.get("p0_6_general_fe_contact", ()),
            ),
            _gate_status(
                "Solver truthfulness",
                report_paths["p0_6_solver_truthfulness"],
                report_fallbacks.get("p0_6_solver_truthfulness", ()),
            ),
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
        "publication_evidence_index": str(publication_evidence_index) if publication_evidence_index else "",
        "default_publication_evidence_index_missing": default_publication_evidence_index_missing,
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
    parser.add_argument("--promoted-manifest-json", type=Path)
    parser.add_argument("--release-assets-json", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--upload-plan-json", type=Path)
    parser.add_argument("--metadata-preflight-json", type=Path)
    parser.add_argument("--post-publish-roundtrip-json", type=Path)
    parser.add_argument(
        "--publication-evidence-index",
        type=Path,
        help="Compact release-publication-evidence artifact index that supplies P0 closure inputs.",
    )
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
            promoted_manifest_json=args.promoted_manifest_json,
            release_assets_json=args.release_assets_json,
            artifact_root=args.artifact_root,
            upload_plan_json=args.upload_plan_json,
            metadata_preflight_json=args.metadata_preflight_json,
            post_publish_roundtrip_json=args.post_publish_roundtrip_json,
            tag_ref_present=bool(args.tag_ref_present),
            publication_evidence_index=args.publication_evidence_index,
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
