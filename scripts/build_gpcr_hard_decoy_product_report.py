#!/usr/bin/env python3
"""Build the read-only GPCR hard-decoy product report contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_OPERATOR_INTAKE_PACKET = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.json"
DEFAULT_OPERATOR_INTAKE_PACKET_MD = PRODUCTIZATION / "gpcr_hard_decoy_operator_intake_packet.md"
DEFAULT_SUITE_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"
DEFAULT_EVIDENCE_SURFACE = SURFACE_DIR / "gpcr_hard_decoy_evidence_surface.json"
DEFAULT_OUT = PRODUCTIZATION / "gpcr_hard_decoy_product_report.json"

SCHEMA_VERSION = "gpcr-hard-decoy-product-report.v1"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _input_paths() -> list[Path]:
    return [
        Path("scripts/build_gpcr_hard_decoy_product_report.py"),
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
        DEFAULT_OPERATOR_TEMPLATE,
        DEFAULT_OPERATOR_INTAKE_PACKET,
        DEFAULT_OPERATOR_INTAKE_PACKET_MD,
        DEFAULT_SUITE_REPORT,
        DEFAULT_EVIDENCE_SURFACE,
    ]


def _required_fields_from_template(template: dict[str, Any]) -> list[str]:
    targets = _as_list(template.get("targets"))
    if targets and isinstance(targets[0], dict):
        return [
            key
            for key in (
                "target_id",
                "ranking_pr_auc_ci_low",
                "top20_hit_rate",
                "decoys_above_positive_count",
                "positive_out_anchored_by_top_decoys",
            )
            if key in targets[0]
        ]
    return [
        "target_id",
        "ranking_pr_auc_ci_low",
        "top20_hit_rate",
        "decoys_above_positive_count",
        "positive_out_anchored_by_top_decoys",
    ]


def build_gpcr_hard_decoy_product_report(*, repo_root: Path = ROOT) -> dict[str, Any]:
    template = _load_json(repo_root, DEFAULT_OPERATOR_TEMPLATE)
    operator_intake = _load_json(repo_root, DEFAULT_OPERATOR_INTAKE_PACKET)
    suite = _load_json(repo_root, DEFAULT_SUITE_REPORT)
    surface = _load_json(repo_root, DEFAULT_EVIDENCE_SURFACE)
    broad_safe = bool(suite.get("broad_gpcr_family_claim_safe"))
    target_rows = _as_list(suite.get("target_rows"))
    target_count = int(suite.get("target_count") or len(target_rows) or 0)
    target_pass_count = int(suite.get("target_pass_count") or 0)
    science_blockers = [str(row) for row in _as_list(suite.get("blockers"))]

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(),
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_product_report_read_model_from_suite_report",
            repo_root=repo_root,
        ),
        "status": "ready_science_claim_blocked" if not broad_safe else "ready",
        "reason_code": "PASS_READ_MODEL",
        "contract_pass": True,
        "read_model_ready": True,
        "mutation_allowed": False,
        "route": "/product/gpcr-hard-decoy-suite-report",
        "product_report_id": "gpcr_hard_decoy_suite_report",
        "broad_gpcr_family_claim_safe": broad_safe,
        "science_claim_status": "ready" if broad_safe else "blocked",
        "target_count": target_count,
        "target_pass_count": target_pass_count,
        "first_blocked_target": str(
            suite.get("first_blocked_target") or surface.get("first_blocked_target") or ""
        ),
        "root_cause_tags": [
            str(row)
            for row in _as_list(suite.get("root_cause_tags") or surface.get("root_cause_tags"))
        ],
        "exit_criteria": _as_dict(suite.get("exit_criteria") or surface.get("exit_criteria")),
        "required_targets": [
            str(row) for row in _as_list(template.get("required_targets") or surface.get("target_families"))
        ],
        "required_operator_fields": _required_fields_from_template(template),
        "science_blockers": science_blockers,
        "linked_artifacts": {
            "operator_intake_packet": str(DEFAULT_OPERATOR_INTAKE_PACKET),
            "operator_intake_packet_markdown": str(DEFAULT_OPERATOR_INTAKE_PACKET_MD),
            "operator_template": str(DEFAULT_OPERATOR_TEMPLATE),
            "suite_report": str(DEFAULT_SUITE_REPORT),
            "evidence_surface": str(DEFAULT_EVIDENCE_SURFACE),
        },
        "endpoints": [
            {
                "endpoint_id": "get_gpcr_hard_decoy_suite_report",
                "method": "GET",
                "route": "/product/gpcr-hard-decoy-suite-report",
                "artifact": str(DEFAULT_SUITE_REPORT),
            },
            {
                "endpoint_id": "get_gpcr_hard_decoy_evidence_surface",
                "method": "GET",
                "route": "/product/gpcr-hard-decoy-suite-report/evidence-surface",
                "artifact": str(DEFAULT_EVIDENCE_SURFACE),
            },
            {
                "endpoint_id": "get_gpcr_hard_decoy_operator_template",
                "method": "GET",
                "route": "/product/gpcr-hard-decoy-suite-report/operator-template",
                "artifact": str(DEFAULT_OPERATOR_TEMPLATE),
            },
            {
                "endpoint_id": "get_gpcr_hard_decoy_operator_intake_packet",
                "method": "GET",
                "route": "/product/gpcr-hard-decoy-suite-report/operator-intake-packet",
                "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET),
            },
            {
                "endpoint_id": "list_gpcr_hard_decoy_required_fields",
                "method": "GET",
                "route": "/product/gpcr-hard-decoy-suite-report/required-fields",
                "artifact": str(DEFAULT_OPERATOR_TEMPLATE),
                "json_pointer": "/targets/0",
            },
        ],
        "forbidden_operations": [
            "generate_docking_results",
            "mutate_operator_metrics",
            "promote_broad_gpcr_claim",
            "infer_missing_target_values",
        ],
        "next_actions": (
            ["review_gpcr_hard_decoy_suite_report"]
            if broad_safe
            else [
                "fill_gpcr_hard_decoy_operator_intake_packet",
                "fill_drd2_htr2a_oprm1_operator_template_values",
                "run_gpcr_hard_decoy_materializer",
                "refresh_gpcr_hard_decoy_product_report",
                "regenerate_product_capabilities_surface",
            ]
        ),
        "summary": {
            "read_model_ready": True,
            "science_claim_status": "ready" if broad_safe else "blocked",
            "target_count": target_count,
            "target_pass_count": target_pass_count,
            "science_blocker_count": len(science_blockers),
            "operator_intake_packet_status": str(operator_intake.get("status") or ""),
            "operator_intake_required_slot_count": int(
                operator_intake.get("required_slot_count") or 0
            ),
            "first_blocked_target": str(
                suite.get("first_blocked_target") or surface.get("first_blocked_target") or ""
            ),
        },
        "summary_line": (
            "GPCR hard-decoy product report: READY | science_claim=ready"
            if broad_safe
            else (
                "GPCR hard-decoy product report: READY | science_claim=blocked | "
                f"first_blocked_target={suite.get('first_blocked_target') or 'none'}"
            )
        ),
        "claim_boundary": (
            "This product report is a read-only map for the GPCR hard-decoy suite report. "
            "It exposes required operator fields, linked artifacts, and current science "
            "claim status, but it does not generate target metrics, mutate evidence, or "
            "promote broad GPCR claims."
        ),
    }


def write_gpcr_hard_decoy_product_report(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    payload = build_gpcr_hard_decoy_product_report(repo_root=repo_root)
    resolved = out if out.is_absolute() else repo_root / out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_gpcr_hard_decoy_product_report(repo_root=args.repo_root, out=args.out)
    print(_json_text(payload), end="") if args.json else print(payload["summary_line"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
