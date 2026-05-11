from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_VIEWER_MANIFEST = Path(
    "implementation/phase1/commercialization_status/real_drawing_private_3d_viewer_manifest.json"
)
DEFAULT_OUT = Path("implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json")
DEFAULT_OUT_MD = Path("implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.md")
EXPECTED_SCHEMA_VERSION = "real-drawing-private-3d-webviewer.v1"
EXPECTED_PRESET = "real_drawing_private_3d"
EXPECTED_VIEWER_HREF = "src/structure-viewer/index.html?preset=real_drawing_private_3d"

SENSITIVE_KEYS = (
    "file_id",
    "file_name",
    "private_path",
    "source_private_manifest",
    "source_url",
)
REVIEW_FLAGS = (
    "not_solver_exact",
    "proxy_layout_not_true_geometry",
    "proxy_node_glyph_fallback",
    "sampled_dense_model",
    "sparse_preview",
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object at {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n", encoding="utf-8")


def _sensitive_key_findings(value: Any, *, path: str = "$") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in SENSITIVE_KEYS:
                findings.append(
                    {
                        "path": child_path,
                        "key": key,
                        "reason_code": "ERR_SENSITIVE_SOURCE_FIELD_PRESENT",
                    }
                )
            findings.extend(_sensitive_key_findings(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_sensitive_key_findings(child, path=f"{path}[{index}]"))
    return findings


def _hard_blocker(blocker_id: str, reason_code: str, message: str, *, asset_ref: str = "") -> dict[str, str]:
    return {
        "blocker_id": blocker_id,
        "reason_code": reason_code,
        "asset_ref": asset_ref,
        "message": message,
    }


def _asset_counts(asset: dict[str, Any]) -> dict[str, int]:
    metrics = asset.get("metrics") if isinstance(asset.get("metrics"), dict) else {}
    segment_count = _safe_int(asset.get("segment_count"), 0)
    return {
        "edge_count": _safe_int(metrics.get("edge_count"), 0),
        "element_count": _safe_int(metrics.get("element_count"), 0),
        "node_count": _safe_int(metrics.get("node_count"), 0),
        "renderable_segment_count": _safe_int(metrics.get("renderable_segment_count"), segment_count),
        "segment_count": segment_count,
    }


def _has_full_detail_lod_evidence(asset: dict[str, Any]) -> bool:
    lod_evidence = asset.get("lod_evidence") if isinstance(asset.get("lod_evidence"), dict) else {}
    metrics = asset.get("metrics") if isinstance(asset.get("metrics"), dict) else {}
    full_detail_segment_count = _safe_int(lod_evidence.get("full_detail_segment_count"), 0)
    renderable_segment_count = _safe_int(metrics.get("renderable_segment_count"), _safe_int(asset.get("segment_count"), 0))
    return (
        bool(lod_evidence.get("contract_pass", False))
        and str(lod_evidence.get("reason_code") or "") == "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED"
        and full_detail_segment_count >= renderable_segment_count
    )


def _asset_quality_tier(asset: dict[str, Any], *, has_hard_blocker: bool) -> str:
    flags = {str(flag) for flag in (asset.get("quality_flags") or [])}
    solver_exact = bool(asset.get("solver_exact", False))
    full_detail_lod_ready = _has_full_detail_lod_evidence(asset)
    if has_hard_blocker:
        return "hard_blocker"
    if "sparse_preview" in flags and not solver_exact:
        return "sparse_preview_review"
    if solver_exact and "sampled_dense_model" in flags and not full_detail_lod_ready:
        return "solver_exact_sampled_review"
    if "proxy_layout_not_true_geometry" in flags or "not_solver_exact" in flags:
        return "proxy_preview_review"
    if solver_exact:
        return "solver_exact_ready"
    return "proxy_preview_review"


def _review_action(row: dict[str, Any]) -> str:
    flags = set(row["quality_flags"])
    if "sparse_preview" in flags and not bool(row.get("solver_exact", False)):
        return "expand sparse preview into a complete solver-exact model"
    if "sampled_dense_model" in flags and not bool(row.get("full_detail_lod_ready", False)):
        return "inspect sampled dense model before using it as a full-detail design claim"
    if "proxy_node_glyph_fallback" in flags:
        return "replace node glyph fallback with edge-backed topology"
    if "proxy_layout_not_true_geometry" in flags or "not_solver_exact" in flags:
        return "replace proxy or preview topology with solver-exact structural geometry"
    return "engineer review"


def _asset_quality_rows(assets: list[dict[str, Any]], asset_blockers: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, asset in enumerate(assets, start=1):
        asset_ref = str(asset.get("asset_ref") or f"asset-{index}")
        counts = _asset_counts(asset)
        flags = [str(flag) for flag in (asset.get("quality_flags") or [])]
        row = {
            "asset_ref": asset_ref,
            "file_type": str(asset.get("file_type") or ""),
            "geometry_available": bool(asset.get("geometry_available", False)),
            "geometry_mode": str(asset.get("geometry_mode") or ""),
            "quality_flags": flags,
            "quality_tier": _asset_quality_tier(asset, has_hard_blocker=bool(asset_blockers.get(asset_ref))),
            "route": str(asset.get("route") or ""),
            "solver_exact": bool(asset.get("solver_exact", False)),
            "status": str(asset.get("status") or ""),
            "full_detail_lod_ready": _has_full_detail_lod_evidence(asset),
        }
        row.update(counts)
        rows.append(row)
    return rows


def _review_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in rows:
        solver_exact = bool(row.get("solver_exact", False))
        full_detail_lod_ready = bool(row.get("full_detail_lod_ready", False))
        review_flags = [
            flag
            for flag in row["quality_flags"]
            if flag in REVIEW_FLAGS
            and not (solver_exact and flag == "sparse_preview")
            and not (solver_exact and full_detail_lod_ready and flag == "sampled_dense_model")
        ]
        if not review_flags:
            continue
        queue.append(
            {
                "review_id": f"RQ-{len(queue) + 1:03d}",
                "asset_ref": row["asset_ref"],
                "quality_tier": row["quality_tier"],
                "quality_flags": review_flags,
                "recommended_action": _review_action(row),
            }
        )
    return queue


def _append_blocker(
    blockers: list[dict[str, str]],
    reason_code: str,
    message: str,
    *,
    asset_ref: str = "",
) -> None:
    blockers.append(_hard_blocker(f"HB-{len(blockers) + 1:03d}", reason_code, message, asset_ref=asset_ref))


def build_quality_gate(viewer_manifest_path: Path = DEFAULT_VIEWER_MANIFEST) -> dict[str, Any]:
    if not viewer_manifest_path.exists():
        return {
            "schema_version": "real-drawing-viewer-quality-gate.v1",
            "source_viewer_manifest": str(viewer_manifest_path),
            "contract_pass": False,
            "reason_code": "ERR_REAL_DRAWING_VIEWER_MANIFEST_MISSING",
            "commercial_viewer_ready": False,
            "full_solver_exact_ready": False,
            "recommended_claim": "No commercial claim. Real drawing viewer manifest is missing.",
            "summary": {
                "asset_count": 0,
                "renderable_asset_count": 0,
                "solver_exact_asset_count": 0,
                "proxy_or_preview_asset_count": 0,
                "hard_blocker_count": 1,
                "review_queue_asset_count": 0,
                "review_item_count": 0,
            },
            "hard_blockers": [
                _hard_blocker(
                    "HB-001",
                    "ERR_REAL_DRAWING_VIEWER_MANIFEST_MISSING",
                    "Real drawing viewer manifest does not exist.",
                )
            ],
            "review_queue": [],
            "asset_quality_rows": [],
            "quality_flag_counts": {},
        }

    manifest = _load_json(viewer_manifest_path)
    raw_assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    assets = [asset for asset in raw_assets if isinstance(asset, dict)]
    blockers: list[dict[str, str]] = []
    asset_blockers: dict[str, list[dict[str, str]]] = {}

    schema_version = str(manifest.get("schema_version") or "")
    preset = str(manifest.get("structure_viewer_preset") or "")
    viewer_href = str(manifest.get("structure_viewer_href") or "")
    declared_asset_count = _safe_int(manifest.get("asset_count"), -1)
    declared_renderable_count = _safe_int(manifest.get("renderable_asset_count"), -1)
    declared_solver_exact_count = _safe_int(manifest.get("solver_exact_asset_count"), -1)
    declared_proxy_count = _safe_int(manifest.get("proxy_or_preview_asset_count"), -1)

    if schema_version != EXPECTED_SCHEMA_VERSION:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_SCHEMA_UNEXPECTED",
            f"Viewer manifest schema must be {EXPECTED_SCHEMA_VERSION}.",
        )
    if preset != EXPECTED_PRESET:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_PRESET_MISMATCH",
            f"Viewer preset must be {EXPECTED_PRESET}.",
        )
    if viewer_href != EXPECTED_VIEWER_HREF:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_HREF_MISMATCH",
            f"Viewer href must be {EXPECTED_VIEWER_HREF}.",
        )
    if not assets:
        _append_blocker(blockers, "ERR_REAL_DRAWING_VIEWER_ASSET_LIST_EMPTY", "No real drawing assets are registered.")
    if declared_asset_count != len(assets):
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_ASSET_COUNT_MISMATCH",
            "Declared asset_count does not match the asset list length.",
        )

    asset_refs: set[str] = set()
    duplicate_refs: set[str] = set()
    renderable_count = 0
    solver_exact_count = 0
    flag_counter: Counter[str] = Counter()
    for index, asset in enumerate(assets, start=1):
        asset_ref = str(asset.get("asset_ref") or "").strip()
        display_ref = asset_ref or f"asset-{index}"
        local_blockers: list[dict[str, str]] = []
        counts = _asset_counts(asset)
        quality_flags = [str(flag) for flag in (asset.get("quality_flags") or [])]
        flag_counter.update(quality_flags)
        if not asset_ref:
            _append_blocker(blockers, "ERR_REAL_DRAWING_VIEWER_ASSET_REF_MISSING", "Asset is missing asset_ref.")
            local_blockers.append(blockers[-1])
        elif asset_ref in asset_refs:
            duplicate_refs.add(asset_ref)
            _append_blocker(
                blockers,
                "ERR_REAL_DRAWING_VIEWER_ASSET_REF_DUPLICATE",
                "Asset ref must be unique.",
                asset_ref=asset_ref,
            )
            local_blockers.append(blockers[-1])
        else:
            asset_refs.add(asset_ref)

        geometry_available = bool(asset.get("geometry_available", False))
        if geometry_available and counts["segment_count"] > 0:
            renderable_count += 1
        else:
            _append_blocker(
                blockers,
                "ERR_REAL_DRAWING_VIEWER_ASSET_NOT_RENDERABLE",
                "Asset is not renderable in the 3D viewer.",
                asset_ref=display_ref,
            )
            local_blockers.append(blockers[-1])
        if counts["segment_count"] <= 0:
            _append_blocker(
                blockers,
                "ERR_REAL_DRAWING_VIEWER_ZERO_SEGMENTS",
                "Asset has no renderable segments.",
                asset_ref=display_ref,
            )
            local_blockers.append(blockers[-1])
        if bool(asset.get("solver_exact", False)):
            solver_exact_count += 1
        if local_blockers:
            asset_blockers[display_ref] = local_blockers

    proxy_count = len(assets) - solver_exact_count
    if declared_renderable_count != renderable_count:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_RENDERABLE_COUNT_MISMATCH",
            "Declared renderable_asset_count does not match computed renderable assets.",
        )
    if declared_solver_exact_count != solver_exact_count:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_SOLVER_EXACT_COUNT_MISMATCH",
            "Declared solver_exact_asset_count does not match computed solver-exact assets.",
        )
    if declared_proxy_count != proxy_count:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_PROXY_COUNT_MISMATCH",
            "Declared proxy_or_preview_asset_count does not match computed proxy/preview assets.",
        )
    if assets and solver_exact_count <= 0:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_NO_SOLVER_EXACT_ASSETS",
            "At least one solver-exact real drawing asset is required for the commercial review gate.",
        )

    sensitive_findings = _sensitive_key_findings(manifest)
    for finding in sensitive_findings:
        _append_blocker(
            blockers,
            "ERR_REAL_DRAWING_VIEWER_SENSITIVE_FIELD_PRESENT",
            f"Sensitive source field is present at {finding['path']}.",
        )

    rows = _asset_quality_rows(assets, asset_blockers)
    review_queue = _review_queue(rows)
    contract_pass = not blockers
    commercial_viewer_ready = (
        contract_pass
        and bool(assets)
        and renderable_count == len(assets)
        and preset == EXPECTED_PRESET
        and viewer_href == EXPECTED_VIEWER_HREF
    )
    full_solver_exact_ready = commercial_viewer_ready and solver_exact_count == len(assets) and not review_queue
    if blockers:
        reason_code = "ERR_REAL_DRAWING_VIEWER_HARD_BLOCKERS"
    elif review_queue:
        reason_code = "PASS_WITH_REVIEW_QUEUE"
    else:
        reason_code = "PASS"

    route_counts = manifest.get("route_counts") if isinstance(manifest.get("route_counts"), dict) else {}
    status_counts = manifest.get("status_counts") if isinstance(manifest.get("status_counts"), dict) else {}
    recommended_claim = (
        "Integrated real-drawing viewer is ready for engineer-in-loop review; proxy/preview assets are labeled "
        "and are not full solver-exact replacements."
        if commercial_viewer_ready and not full_solver_exact_ready
        else "Integrated real-drawing viewer is ready for full solver-exact review claims."
        if full_solver_exact_ready
        else "Do not use the real-drawing viewer for commercial review until hard blockers are closed."
    )
    return {
        "schema_version": "real-drawing-viewer-quality-gate.v1",
        "source_viewer_manifest": str(viewer_manifest_path),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "commercial_viewer_ready": commercial_viewer_ready,
        "full_solver_exact_ready": full_solver_exact_ready,
        "recommended_claim": recommended_claim,
        "structure_viewer_href": viewer_href,
        "structure_viewer_preset": preset,
        "summary": {
            "asset_count": len(assets),
            "duplicate_asset_ref_count": len(duplicate_refs),
            "hard_blocker_count": len(blockers),
            "proxy_or_preview_asset_count": proxy_count,
            "renderable_asset_count": renderable_count,
            "review_item_count": sum(len(item["quality_flags"]) for item in review_queue),
            "review_queue_asset_count": len(review_queue),
            "solver_exact_asset_count": solver_exact_count,
        },
        "hard_blockers": blockers,
        "review_queue": review_queue,
        "asset_quality_rows": rows,
        "quality_flag_counts": dict(sorted(flag_counter.items())),
        "route_counts": dict(sorted((str(key), value) for key, value in route_counts.items())),
        "status_counts": dict(sorted((str(key), value) for key, value in status_counts.items())),
        "sensitive_key_findings": sensitive_findings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    flag_counts = report.get("quality_flag_counts") if isinstance(report.get("quality_flag_counts"), dict) else {}
    review_queue = report.get("review_queue") if isinstance(report.get("review_queue"), list) else []
    blockers = report.get("hard_blockers") if isinstance(report.get("hard_blockers"), list) else []
    flag_text = ", ".join(f"{key}={value}" for key, value in flag_counts.items()) or "none"
    lines = [
        "# Real Drawing Viewer Quality Gate",
        "",
        f"- Contract: {report.get('reason_code')}",
        f"- Commercial viewer ready: {bool(report.get('commercial_viewer_ready'))}",
        f"- Full solver-exact ready: {bool(report.get('full_solver_exact_ready'))}",
        f"- Viewer: `{report.get('structure_viewer_href', '')}`",
        f"- Recommended claim: {report.get('recommended_claim', '')}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Asset count | {summary.get('asset_count', 0)} |",
        f"| Renderable assets | {summary.get('renderable_asset_count', 0)} |",
        f"| Solver-exact assets | {summary.get('solver_exact_asset_count', 0)} |",
        f"| Proxy or preview assets | {summary.get('proxy_or_preview_asset_count', 0)} |",
        f"| Review queue assets | {summary.get('review_queue_asset_count', 0)} |",
        f"| Review items | {summary.get('review_item_count', 0)} |",
        f"| Hard blockers | {summary.get('hard_blocker_count', 0)} |",
        "",
        f"- Quality flags: {flag_text}",
        "",
    ]
    if blockers:
        lines.extend(["## Hard Blockers", "", "| ID | Asset | Reason | Message |", "| --- | --- | --- | --- |"])
        for blocker in blockers:
            lines.append(
                "| {id} | {asset} | {reason} | {message} |".format(
                    id=blocker.get("blocker_id", ""),
                    asset=blocker.get("asset_ref", ""),
                    reason=blocker.get("reason_code", ""),
                    message=str(blocker.get("message", "")).replace("|", "/"),
                )
            )
        lines.append("")
    if review_queue:
        lines.extend(["## Review Queue", "", "| Asset | Tier | Flags | Action |", "| --- | --- | --- | --- |"])
        for item in review_queue:
            lines.append(
                "| {asset} | {tier} | {flags} | {action} |".format(
                    asset=item.get("asset_ref", ""),
                    tier=item.get("quality_tier", ""),
                    flags=", ".join(str(flag) for flag in item.get("quality_flags", [])),
                    action=str(item.get("recommended_action", "")).replace("|", "/"),
                )
            )
        lines.append("")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer-manifest", type=Path, default=DEFAULT_VIEWER_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true", help="Print the quality gate JSON to stdout.")
    parser.add_argument(
        "--fail-on-hard-blocker",
        action="store_true",
        help="Return exit code 2 when the quality gate has hard blockers.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_quality_gate(args.viewer_manifest)
    _write_json(args.out, report)
    _write_text(args.out_md, render_markdown(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    if args.fail_on_hard_blocker and not report["contract_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
