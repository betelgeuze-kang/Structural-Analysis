#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from parse_midas_mgt_to_json_npz import derive_kds_geometry_bridge_for_model_payload
    from build_kds_geometry_bridge_registry import merge_registry_payloads
except ImportError:  # pragma: no cover - package import fallback
    from implementation.phase1.parse_midas_mgt_to_json_npz import derive_kds_geometry_bridge_for_model_payload
    from implementation.phase1.build_kds_geometry_bridge_registry import merge_registry_payloads


CANONICAL_MIDAS_ARTIFACTS = (
    Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
)
DEFAULT_KDS_REPORT = Path("implementation/phase1/release/kds_compliance/code_check_report.json")
DEFAULT_HEURISTIC_REGISTRY = Path("implementation/phase1/open_data/midas/kds_geometry_bridge_registry.heuristic.json")
DEFAULT_EXACT_REGISTRY = Path("implementation/phase1/open_data/midas/kds_geometry_bridge_registry.exact.json")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _embedded_summary(bridge_payload: dict[str, Any]) -> dict[str, Any]:
    summary = bridge_payload.get("summary") if isinstance(bridge_payload.get("summary"), dict) else {}
    return {
        "review_rows": int(summary.get("review_row_count", 0) or 0),
        "review_ids": int(summary.get("review_id_count", 0) or 0),
        "mapped_review_ids": int(summary.get("mapped_review_id_count", 0) or 0),
        "exact_mapped_review_ids": int(summary.get("exact_mapped_review_id_count", 0) or 0),
        "heuristic_mapped_review_ids": int(summary.get("heuristic_mapped_review_id_count", 0) or 0),
        "unmapped_review_ids": int(summary.get("unmapped_review_id_count", 0) or 0),
        "registry_source_label": str(bridge_payload.get("registry_source_label", "") or "none"),
        "registry_contract_version": str(bridge_payload.get("registry_contract_version", "") or "0.1.0"),
        "external_registry_row_count": int(summary.get("external_registry_row_count", 0) or 0),
        "external_registry_usable_row_count": int(summary.get("external_registry_usable_row_count", 0) or 0),
        "external_registry_exact_row_count": int(summary.get("external_registry_exact_row_count", 0) or 0),
        "external_registry_heuristic_row_count": int(summary.get("external_registry_heuristic_row_count", 0) or 0),
        "external_registry_source_counts": summary.get("external_registry_source_counts") if isinstance(summary.get("external_registry_source_counts"), dict) else {},
        "strategy_counts": summary.get("strategy_counts") if isinstance(summary.get("strategy_counts"), dict) else {},
        "confidence_counts": summary.get("confidence_counts") if isinstance(summary.get("confidence_counts"), dict) else {},
    }


def _default_registry_paths() -> list[Path]:
    return [path for path in (DEFAULT_HEURISTIC_REGISTRY, DEFAULT_EXACT_REGISTRY) if path.exists()]


def _merge_registry_paths(paths: list[Path]) -> dict[str, Any] | None:
    unique_paths: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_paths.append(path)
    payloads = [_load_json(path) for path in unique_paths if path.exists()]
    if not payloads:
        return None
    return merge_registry_payloads(*payloads)


def _effective_registry_payload(registry_path: Path | None) -> dict[str, Any] | None:
    registry_paths = _default_registry_paths()
    if isinstance(registry_path, Path):
        registry_paths.append(registry_path)
    return _merge_registry_paths(registry_paths)


def backfill_artifact(
    path: Path,
    *,
    report_path: Path,
    registry_path: Path | None = None,
    write: bool = False,
) -> dict[str, Any]:
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    if not isinstance(model, dict):
        raise ValueError(f"{path} is missing a model object")
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    report = _load_json(report_path)
    registry_payload = _effective_registry_payload(registry_path if isinstance(registry_path, Path) else None)
    bridge_payload = derive_kds_geometry_bridge_for_model_payload(
        payload,
        code_check_report=report,
        bridge_registry=registry_payload,
    )
    if not bridge_payload:
        return {
            "path": str(path),
            "supported": False,
            "review_rows": 0,
            "review_ids": 0,
            "mapped_review_ids": 0,
            "unmapped_review_ids": 0,
            "registry_source_label": str((registry_payload or {}).get("source", "") or "none"),
            "registry_contract_version": str((registry_payload or {}).get("contract_version", "") or "0.1.0"),
            "external_registry_row_count": int(len((registry_payload or {}).get("mappings") or (registry_payload or {}).get("bridge_rows") or [])),
            "external_registry_usable_row_count": 0,
            "external_registry_exact_row_count": int(((registry_payload or {}).get("summary") or {}).get("exact_mapping_count", 0) or 0),
            "external_registry_heuristic_row_count": int(((registry_payload or {}).get("summary") or {}).get("heuristic_mapping_count", 0) or 0),
            "external_registry_source_counts": ((registry_payload or {}).get("summary") or {}).get("source_counts", {}),
            "strategy_counts": {},
            "confidence_counts": {},
            "changed": False,
            "had_embedded_kds_geometry_bridge": bool(metadata.get("kds_geometry_bridge")),
            "written": False,
        }
    existing = metadata.get("kds_geometry_bridge") if isinstance(metadata.get("kds_geometry_bridge"), dict) else {}
    changed = existing != bridge_payload
    if write and changed:
        metadata = dict(metadata)
        metadata["kds_geometry_bridge"] = bridge_payload
        model = dict(model)
        model["metadata"] = metadata
        payload = dict(payload)
        payload["model"] = model
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = _embedded_summary(bridge_payload)
    summary.update(
        {
            "path": str(path),
            "supported": True,
            "changed": changed,
            "had_embedded_kds_geometry_bridge": bool(existing),
            "written": bool(write and changed),
        }
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Embed kds_geometry_bridge metadata into canonical MIDAS JSON artifacts.")
    parser.add_argument("paths", nargs="*", type=Path, default=list(CANONICAL_MIDAS_ARTIFACTS))
    parser.add_argument("--report", type=Path, default=DEFAULT_KDS_REPORT, help="KDS code-check report JSON path.")
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Optional additional KDS geometry-bridge registry JSON. When provided, it is merged with the default heuristic registry and the default reviewer-verified exact registry so exact rows can override heuristic surrogate rows by review key.",
    )
    parser.add_argument("--write", action="store_true", help="Write updated payloads back to disk.")
    args = parser.parse_args(argv)

    for path in args.paths:
        summary = backfill_artifact(path, report_path=args.report, registry_path=args.registry, write=args.write)
        if not bool(summary.get("supported", False)):
            print(
                f"{path}: unsupported kds geometry bridge | "
                f"registry={summary['registry_source_label']} "
                f"rows={summary['external_registry_usable_row_count']}/{summary['external_registry_row_count']} "
                f"written=False"
            )
            continue
        print(
            f"{path}: review_ids={summary['mapped_review_ids']}/{summary['review_ids']} mapped "
            f"(exact={summary.get('exact_mapped_review_ids', 0)}, heuristic={summary.get('heuristic_mapped_review_ids', 0)}) "
            f"rows={summary['review_rows']} strategy={summary['strategy_counts']} "
            f"confidence={summary.get('confidence_counts', {})} "
            f"registry={summary['registry_source_label']} "
            f"registry_exact={summary.get('external_registry_exact_row_count', 0)} "
            f"registry_heuristic={summary.get('external_registry_heuristic_row_count', 0)} "
            f"registry_rows={summary['external_registry_usable_row_count']}/{summary['external_registry_row_count']} "
            f"changed={summary['changed']} written={summary['written']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
