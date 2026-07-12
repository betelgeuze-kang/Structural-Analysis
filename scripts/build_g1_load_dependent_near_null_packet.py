#!/usr/bin/env python3
"""Build a local, non-promoting G1 load-dependent near-null packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
PHASE1 = ROOT / "implementation" / "phase1"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

from build_g1_support_elastic_link_reconciliation_audit import (  # noqa: E402
    DEFAULT_MGT,
    DEFAULT_PREFLIGHT,
    DEFAULT_SUPPORT_ENTITY,
    DEFAULT_SUPPORT_SPRING,
    build_audit as build_reconciliation_audit,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from run_g1_null_space_mode_audit import (  # noqa: E402
    run_g1_null_space_mode_audit as run_null_space_audit,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SCHEMA_VERSION = "g1-load-dependent-near-null-packet.v1"
DEFAULT_FRAME_SERVICE_TANGENT_SOURCE = "real_per_element"
LOAD_SCALE_TOLERANCE = 1.0e-9


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_label(load_scale: float) -> str:
    text = f"{float(load_scale):.12g}".replace("-", "m").replace(".", "p")
    return text or "0"


def default_raw_near_null_path(load_scale: float) -> Path:
    return PRODUCTIZATION / f"g1_load_dependent_near_null_raw_{_load_label(load_scale)}.local.json"


def default_packet_path(load_scale: float) -> Path:
    return PRODUCTIZATION / f"g1_load_dependent_near_null_{_load_label(load_scale)}.local.json"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _extract_near_null_mode_count(raw_near_null: dict[str, Any]) -> int:
    singularity = _as_dict(raw_near_null.get("singularity_indicators"))
    return _as_int(singularity.get("near_null_mode_count"), 0)


def _smallest_abs_eigenvalue(raw_near_null: dict[str, Any]) -> float | None:
    values = [
        abs(float(value))
        for value in _as_list(_as_dict(raw_near_null.get("singularity_indicators")).get("smallest_eigenvalues"))
        if _as_float(value, None) is not None
    ]
    return min(values) if values else None


def _dominant_node_ids(rows: list[Any]) -> list[int]:
    node_ids: list[int] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("node_id") is None:
            continue
        try:
            node_ids.append(int(row["node_id"]))
        except Exception:
            continue
    return sorted(set(node_ids))


def build_packet(
    *,
    repo_root: Path = ROOT,
    load_scale: float,
    mgt_path: Path = DEFAULT_MGT,
    roundtrip_npz: Path | None = None,
    frame_service_tangent_source: str = DEFAULT_FRAME_SERVICE_TANGENT_SOURCE,
    max_modes: int = 8,
    raw_near_null_json: Path | None = None,
    support_entity_path: Path = DEFAULT_SUPPORT_ENTITY,
    support_spring_path: Path = DEFAULT_SUPPORT_SPRING,
    preflight_path: Path = DEFAULT_PREFLIGHT,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    raw_near_null_json = raw_near_null_json or default_raw_near_null_path(load_scale)
    raw_near_null_resolved = _resolve(repo_root, raw_near_null_json)

    raw_near_null = run_null_space_audit(
        mgt_model=_resolve(repo_root, mgt_path),
        roundtrip_npz=_resolve(repo_root, roundtrip_npz) if roundtrip_npz is not None else None,
        load_scale=float(load_scale),
        frame_service_tangent_source=frame_service_tangent_source,
        max_modes=int(max_modes),
        scan_only=False,
        output_json=raw_near_null_resolved,
    )
    reconciliation = build_reconciliation_audit(
        repo_root=repo_root,
        mgt_path=mgt_path,
        near_null_path=raw_near_null_json,
        support_entity_path=support_entity_path,
        support_spring_path=support_spring_path,
        preflight_path=preflight_path,
    )

    blockers: list[str] = []
    load_key = f"{float(load_scale):g}"
    raw_status = str(raw_near_null.get("status") or "missing")
    reconciliation_status = str(reconciliation.get("status") or "missing")
    observed_load = _as_float(raw_near_null.get("load_scale"), None)
    near_null_mode_count = _extract_near_null_mode_count(raw_near_null)
    mode_rows = _as_list(raw_near_null.get("mode_rows"))
    dominant_rows = _as_list(reconciliation.get("dominant_dof_rows"))

    if raw_status != "ready":
        blockers.append(f"raw_near_null_audit_not_ready:{load_key}")
    if reconciliation_status != "ready":
        blockers.append(f"support_elastic_link_reconciliation_not_ready:{load_key}")
    if observed_load is None:
        blockers.append(f"load_dependent_near_null_packet_load_scale_missing:{load_key}")
    elif abs(float(observed_load) - float(load_scale)) > LOAD_SCALE_TOLERANCE:
        blockers.append(f"load_dependent_near_null_packet_load_scale_mismatch:{load_key}")
    if near_null_mode_count <= 0:
        blockers.append(f"load_dependent_near_null_packet_mode_count_missing:{load_key}")
    if not mode_rows:
        blockers.append(f"load_dependent_near_null_packet_mode_rows_missing:{load_key}")
    if not dominant_rows:
        blockers.append(f"load_dependent_near_null_packet_dominant_rows_missing:{load_key}")

    for source_blocker in _as_list(raw_near_null.get("blockers")):
        if source_blocker:
            blockers.append(f"raw_near_null_audit_source_blocker:{source_blocker}")
    for source_blocker in _as_list(reconciliation.get("blockers")):
        if source_blocker:
            blockers.append(f"support_elastic_link_reconciliation_source_blocker:{source_blocker}")

    blockers = sorted(dict.fromkeys(str(item) for item in blockers if str(item)))
    ready = not blockers
    singularity = _as_dict(raw_near_null.get("singularity_indicators"))
    assembled_tangent = _as_dict(raw_near_null.get("assembled_tangent"))
    reconciliation_summary = _as_dict(reconciliation.get("summary"))

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_g1_load_dependent_near_null_packet.py"),
                Path("implementation/phase1/run_g1_null_space_mode_audit.py"),
                Path("scripts/build_g1_support_elastic_link_reconciliation_audit.py"),
                mgt_path,
                raw_near_null_json,
                support_entity_path,
                support_spring_path,
                preflight_path,
            ],
            reused_evidence=True,
            reuse_policy="local_non_promoting_load_dependent_null_space_audit_wrapped_for_comparison",
            repo_root=repo_root,
        ),
        "status": "ready" if ready else "blocked",
        "contract_pass": ready,
        "reason_code": "PASS" if ready else "ERR_LOAD_DEPENDENT_NEAR_NULL_PACKET_INCOMPLETE",
        "promotes_g1_closure": False,
        "load_scale": float(load_scale),
        "claim_boundary": (
            "This local packet wraps a load-dependent reference-tangent near-null audit "
            "and support/elastic-link reconciliation for comparison only. It does not "
            "close G1, prove full-load 1.0, or replace the consistent residual/Jacobian "
            "Newton and production ROCm/HIP gates."
        ),
        "summary_line": (
            "G1 load-dependent near-null packet: "
            f"{'READY' if ready else 'BLOCKED'} | load_scale={float(load_scale):g} | "
            f"near_null_modes={near_null_mode_count} | dominant_rows={len(dominant_rows)}"
        ),
        "summary": {
            "load_scale": float(load_scale),
            "raw_near_null_status": raw_status,
            "support_elastic_link_reconciliation_status": reconciliation_status,
            "near_null_mode_count": int(near_null_mode_count),
            "mode_row_count": int(len(mode_rows)),
            "dominant_dof_row_count": int(len(dominant_rows)),
            "dominant_node_count": int(len(_dominant_node_ids(dominant_rows))),
            "smallest_abs_eigenvalue": _smallest_abs_eigenvalue(raw_near_null),
            "direct_support_member_count": _as_int(
                reconciliation_summary.get("direct_support_member_count"), 0
            ),
            "direct_elastic_link_endpoint_count": _as_int(
                reconciliation_summary.get("direct_elastic_link_endpoint_count"), 0
            ),
            "elastic_link_reachable_to_support_count": _as_int(
                reconciliation_summary.get("elastic_link_reachable_to_support_count"), 0
            ),
            "blocker_count": int(len(blockers)),
        },
        "near_null_context": {
            "load_scale": observed_load,
            "frame_service_tangent_source": raw_near_null.get("frame_service_tangent_source"),
            "near_null_mode_count": near_null_mode_count,
            "smallest_eigenvalues": singularity.get("smallest_eigenvalues", []),
            "near_null_eigenvalue_tolerance_relative": singularity.get(
                "near_null_eigenvalue_tolerance_relative"
            ),
            "singular": singularity.get("singular"),
            "assembled_tangent": assembled_tangent,
        },
        "raw_near_null_audit": {
            "path": str(raw_near_null_resolved),
            "status": raw_status,
            "reason_code": raw_near_null.get("reason_code"),
            "mode_rows": mode_rows,
            "pinning_candidates": raw_near_null.get("pinning_candidates", []),
            "resource_usage": raw_near_null.get("resource_usage", {}),
        },
        "support_elastic_link_reconciliation": {
            "status": reconciliation_status,
            "reason_code": reconciliation.get("reason_code"),
            "summary": reconciliation_summary,
            "ranked_findings": reconciliation.get("ranked_findings", []),
            "support_context": reconciliation.get("support_context", {}),
        },
        "dominant_dof_rows": dominant_rows,
        "dominant_node_ids": _dominant_node_ids(dominant_rows),
        "blockers": blockers,
        "disallowed_promotions": [
            "no_G1_closure_claim",
            "no_full_load_1p0_claim",
            "no_solver_change",
            "no_pinning_applied",
            "no_modal_promotion_without_comparison_receipt",
            "no_consistent_newton_or_rocm_gate_closure",
        ],
    }


def write_packet(
    *,
    repo_root: Path = ROOT,
    load_scale: float,
    mgt_path: Path = DEFAULT_MGT,
    roundtrip_npz: Path | None = None,
    frame_service_tangent_source: str = DEFAULT_FRAME_SERVICE_TANGENT_SOURCE,
    max_modes: int = 8,
    raw_near_null_json: Path | None = None,
    out: Path | None = None,
    support_entity_path: Path = DEFAULT_SUPPORT_ENTITY,
    support_spring_path: Path = DEFAULT_SUPPORT_SPRING,
    preflight_path: Path = DEFAULT_PREFLIGHT,
) -> dict[str, Any]:
    payload = build_packet(
        repo_root=repo_root,
        load_scale=load_scale,
        mgt_path=mgt_path,
        roundtrip_npz=roundtrip_npz,
        frame_service_tangent_source=frame_service_tangent_source,
        max_modes=max_modes,
        raw_near_null_json=raw_near_null_json,
        support_entity_path=support_entity_path,
        support_spring_path=support_spring_path,
        preflight_path=preflight_path,
    )
    out = out or default_packet_path(load_scale)
    resolved_out = _resolve(repo_root.resolve(), out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--load-scale", type=float, required=True)
    parser.add_argument("--mgt-path", type=Path, default=DEFAULT_MGT)
    parser.add_argument("--roundtrip-npz", type=Path, default=None)
    parser.add_argument(
        "--frame-service-tangent-source",
        choices=["real_per_element", "placeholder_1mpa"],
        default=DEFAULT_FRAME_SERVICE_TANGENT_SOURCE,
    )
    parser.add_argument("--max-modes", type=int, default=8)
    parser.add_argument("--raw-near-null-json", type=Path, default=None)
    parser.add_argument("--support-entity-json", type=Path, default=DEFAULT_SUPPORT_ENTITY)
    parser.add_argument("--support-spring-json", type=Path, default=DEFAULT_SUPPORT_SPRING)
    parser.add_argument("--preflight-json", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--out", "--output-json", dest="out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = write_packet(
        repo_root=args.repo_root,
        load_scale=args.load_scale,
        mgt_path=args.mgt_path,
        roundtrip_npz=args.roundtrip_npz,
        frame_service_tangent_source=args.frame_service_tangent_source,
        max_modes=args.max_modes,
        raw_near_null_json=args.raw_near_null_json,
        out=args.out,
        support_entity_path=args.support_entity_json,
        support_spring_path=args.support_spring_json,
        preflight_path=args.preflight_json,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
