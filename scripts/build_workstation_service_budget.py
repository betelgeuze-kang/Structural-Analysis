#!/usr/bin/env python3
"""Build the workstation delivery service performance and size budget."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "workstation-service-budget.v1"
DEFAULT_BUDGET_OUT = Path("implementation/phase1/workstation_service_budget.json")
DEFAULT_HARDWARE_PROFILE = Path("implementation/phase1/workstation_hardware_profile.json")
DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE = Path("implementation/phase1/structure_viewer_browser_performance_probe.json")
DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE = Path("implementation/phase1/structure_viewer_visual_regression_baseline.json")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_row(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "available": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
        "sha256": _sha256_path(path) if path.exists() else "",
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _viewer_metrics(viewer_probe: dict[str, Any]) -> dict[str, Any]:
    probe = viewer_probe.get("probe", {}) if isinstance(viewer_probe.get("probe"), dict) else {}
    raf = probe.get("rafSample", {}) if isinstance(probe.get("rafSample"), dict) else {}
    budgets = viewer_probe.get("budgets", {}) if isinstance(viewer_probe.get("budgets"), dict) else {}
    return {
        "ready_ms": probe.get("readyMs"),
        "average_fps": raf.get("averageFps"),
        "max_ready_ms": budgets.get("max_ready_ms", 60000),
        "min_average_fps": budgets.get("min_average_fps", 5),
        "probe_contract_pass": bool(viewer_probe.get("contract_pass", False)),
        "probe_summary_line": str(viewer_probe.get("summary_line", "")),
    }


def classify_project_size(*, nodes: int, elements: int) -> str:
    if nodes <= 25000 and elements <= 50000:
        return "small"
    if nodes <= 75000 and elements <= 150000:
        return "medium"
    if nodes <= 150000 and elements <= 300000:
        return "large"
    return "oversize"


def _tier_rows() -> list[dict[str, Any]]:
    return [
        {
            "tier": "small",
            "label": "immediate_delivery",
            "max_nodes": 25000,
            "max_elements": 50000,
            "processing_mode": "same_session",
            "customer_commitment": "ready for immediate workstation delivery when input validation passes",
        },
        {
            "tier": "medium",
            "label": "standard_delivery",
            "max_nodes": 75000,
            "max_elements": 150000,
            "processing_mode": "standard",
            "customer_commitment": "standard workstation delivery",
        },
        {
            "tier": "large",
            "label": "batch_or_overnight",
            "max_nodes": 150000,
            "max_elements": 300000,
            "processing_mode": "batch_or_overnight",
            "customer_commitment": "batch or overnight workstation delivery",
        },
        {
            "tier": "oversize",
            "label": "split_or_quote_required",
            "max_nodes": None,
            "max_elements": None,
            "processing_mode": "split_or_quote_required",
            "customer_commitment": "requires model split, scope review, or pre-quote",
        },
    ]


def build_workstation_service_budget(
    *,
    hardware_profile: Path = DEFAULT_HARDWARE_PROFILE,
    viewer_browser_performance_probe: Path = DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE,
    viewer_visual_regression_baseline: Path = DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE,
    hardware_payload: dict[str, Any] | None = None,
    viewer_probe_payload: dict[str, Any] | None = None,
    visual_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hardware = hardware_payload if hardware_payload is not None else _load_json(hardware_profile)
    viewer_probe = viewer_probe_payload if viewer_probe_payload is not None else _load_json(viewer_browser_performance_probe)
    visual = visual_payload if visual_payload is not None else _load_json(viewer_visual_regression_baseline)
    metrics = _viewer_metrics(viewer_probe)

    memory = (
        hardware.get("hardware_profile", {}).get("memory", {})
        if isinstance(hardware.get("hardware_profile"), dict)
        else {}
    )
    total_gib = float(memory.get("total_gib", 0.0) or 0.0)
    blockers = [
        *(["hardware_profile_missing"] if not hardware else []),
        *(["hardware_profile_not_green"] if hardware and not hardware.get("contract_pass", False) else []),
        *(["viewer_browser_performance_probe_missing"] if not viewer_probe else []),
        *(["viewer_browser_performance_probe_not_green"] if viewer_probe and not metrics["probe_contract_pass"] else []),
        *(["workstation_memory_below_delivery_minimum"] if total_gib and total_gib < 16.0 else []),
    ]
    warnings = [
        *(["viewer_visual_regression_baseline_missing"] if not visual else []),
        *(
            ["viewer_visual_regression_baseline_not_green"]
            if visual and not visual.get("contract_pass", False)
            else []
        ),
    ]
    contract_pass = not blockers
    fps = float(metrics["average_fps"] or 0.0)
    ready_ms = int(metrics["ready_ms"] or 0)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_WORKSTATION_SERVICE_BUDGET_BLOCKED",
        "summary_line": (
            f"Workstation service budget: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"tiers=small/medium/large/oversize | ready={ready_ms}ms | fps={fps:.1f}"
        ),
        "service_model": {
            "mode": "single_operator_workstation_delivery",
            "multi_tenant_saas": False,
            "customer_device_fps_claim": False,
            "delivery_formats_v1": ["HTML", "PDF", "SVG", "JSON", "CSV"],
            "dxf_dwg_roundtrip": "v2_extension",
        },
        "performance_budget": {
            "viewer_ready_ms": metrics["ready_ms"],
            "viewer_average_fps": metrics["average_fps"],
            "viewer_max_ready_ms": metrics["max_ready_ms"],
            "viewer_min_average_fps": metrics["min_average_fps"],
            "package_generation_target_seconds": {
                "small": 60,
                "medium": 180,
                "large": 1800,
                "oversize": None,
            },
            "memory_budget_gib": {
                "available_total_gib": total_gib,
                "minimum_required_gib": 16,
                "recommended_gib": 32,
            },
        },
        "project_size_tiers": _tier_rows(),
        "tier_classifier_examples": [
            {"nodes": 10000, "elements": 20000, "tier": classify_project_size(nodes=10000, elements=20000)},
            {"nodes": 60000, "elements": 120000, "tier": classify_project_size(nodes=60000, elements=120000)},
            {"nodes": 120000, "elements": 250000, "tier": classify_project_size(nodes=120000, elements=250000)},
            {"nodes": 200000, "elements": 400000, "tier": classify_project_size(nodes=200000, elements=400000)},
        ],
        "claim_boundary": (
            "Performance and size budgets apply only to this local workstation profile. "
            "They are not SaaS throughput or customer-device FPS claims."
        ),
        "warnings": warnings,
        "blockers": blockers,
        "source_rows": [
            _source_row("workstation_hardware_profile", hardware_profile),
            _source_row("viewer_browser_performance_probe", viewer_browser_performance_probe),
            _source_row("viewer_visual_regression_baseline", viewer_visual_regression_baseline),
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_BUDGET_OUT)
    parser.add_argument("--hardware-profile", type=Path, default=DEFAULT_HARDWARE_PROFILE)
    parser.add_argument("--viewer-browser-performance-probe", type=Path, default=DEFAULT_VIEWER_BROWSER_PERFORMANCE_PROBE)
    parser.add_argument("--viewer-visual-regression-baseline", type=Path, default=DEFAULT_VIEWER_VISUAL_REGRESSION_BASELINE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_workstation_service_budget(
        hardware_profile=args.hardware_profile,
        viewer_browser_performance_probe=args.viewer_browser_performance_probe,
        viewer_visual_regression_baseline=args.viewer_visual_regression_baseline,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
