#!/usr/bin/env python3
"""Build Evidence Console scope/readiness status without expanding GUI claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "evidence-console-scope-status.v1"
DEFAULT_SCOPE_SOURCE = Path("docs/structure-viewer-product-workspace.md")
DEFAULT_CLAIM_BOUNDARY_DOCS = (
    Path("README.md"),
    Path("docs/commercialization-gap-current-state.md"),
)
DEFAULT_P0_STATUS = Path("implementation/phase1/release_evidence/productization/p0_closure_status.json")
DEFAULT_P1_READINESS = Path("implementation/phase1/release_evidence/productization/p1_readiness_status.json")
DEFAULT_P1_BENCHMARK_BREADTH = Path(
    "implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json"
)
DEFAULT_REAL_PROJECT_STATUS = Path("implementation/phase1/real_project_corpus_measured_status.json")
DEFAULT_CUSTOMER_SHADOW_STATUS = Path("implementation/phase1/customer_shadow_evidence_status.json")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/evidence_console_scope_status.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")


REQUIRED_EVIDENCE_CONSOLE_FEATURES = {
    "case_list": ["case list", "case-list", "case rows", "케이스 목록"],
    "source_provenance_inspector": [
        "source/provenance inspector",
        "source provenance inspector",
        "provenance inspector",
        "source provenance",
    ],
    "reference_vs_engine_comparison": [
        "reference vs engine comparison",
        "reference-vs-engine comparison",
        "reference comparison",
    ],
    "residual_audit": ["residual audit", "잔차 감사", "residual auditing"],
    "worst_member_story": ["worst member/story", "worst member", "worst story", "governing member/story"],
    "reviewer_decision": ["PASS/REVIEW/FAIL", "PASS REVIEW FAIL", "reviewer decision"],
    "reproduce_bundle_export": ["reproduce bundle export", "reproduction bundle export", "reproduce bundle"],
}

DEFERRED_GUI_SURFACES = {
    "full_project_dashboard": ["full project dashboard", "project dashboard"],
    "model_editor": ["model editor", "model-editing", "model editing"],
    "accounts_permissions": ["accounts/permissions", "account/permission", "permission management"],
    "collaboration": ["collaboration", "multi-user collaboration"],
    "licensing": ["licensing", "license management"],
}

PROHIBITED_FIRST_SCOPE_CLAIMS = {
    "full_gui_ready_true": ["full_gui_ready=true", '"full_gui_ready": true', "`full_gui_ready`: `true`"],
    "model_editor_ready_true": ["model_editor_ready=true", '"model_editor_ready": true'],
    "collaboration_ready_true": ["collaboration_ready=true", '"collaboration_ready": true'],
    "licensing_ready_true": ["licensing_ready=true", '"licensing_ready": true'],
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _contains_any(text: str, phrases: list[str]) -> bool:
    lowered = text.lower()
    return any(phrase.lower() in lowered for phrase in phrases)


def _row_terms(source_text: str, terms: dict[str, list[str]], *, pass_when_present: bool) -> list[dict[str, Any]]:
    rows = []
    for key, phrases in terms.items():
        present = _contains_any(source_text, phrases)
        rows.append(
            {
                "check": key,
                "pass": bool(present if pass_when_present else not present),
                "present": bool(present),
                "accepted_phrases": phrases,
            }
        )
    return rows


def _truthy_contract(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("p0_closed") is True
        or str(payload.get("status", "")).strip().lower() in {"closed", "ready", "pass"}
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _int_from_summary(payload: dict[str, Any], key: str, default: int = 0) -> int:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    try:
        return int(summary.get(key, default))
    except Exception:
        return int(default)


def _prerequisite_row(label: str, ok: bool, path: Path, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "check": label,
        "pass": bool(ok),
        "path": str(path),
        "summary": summary or {},
    }


def build_status(
    *,
    scope_source: Path = DEFAULT_SCOPE_SOURCE,
    claim_boundary_docs: tuple[Path, ...] = DEFAULT_CLAIM_BOUNDARY_DOCS,
    p0_status: Path = DEFAULT_P0_STATUS,
    p1_readiness: Path = DEFAULT_P1_READINESS,
    p1_benchmark_breadth: Path = DEFAULT_P1_BENCHMARK_BREADTH,
    real_project_status: Path = DEFAULT_REAL_PROJECT_STATUS,
    customer_shadow_status: Path = DEFAULT_CUSTOMER_SHADOW_STATUS,
) -> dict[str, Any]:
    scope_text = _read_text(scope_source)
    claim_boundary_text = "\n".join([scope_text, *(_read_text(path) for path in claim_boundary_docs)])
    feature_rows = _row_terms(scope_text, REQUIRED_EVIDENCE_CONSOLE_FEATURES, pass_when_present=True)
    deferred_rows = _row_terms(scope_text, DEFERRED_GUI_SURFACES, pass_when_present=True)
    prohibited_rows = _row_terms(claim_boundary_text, PROHIBITED_FIRST_SCOPE_CLAIMS, pass_when_present=False)

    p0_payload = _load_json(p0_status)
    p1_payload = _load_json(p1_readiness)
    p1_breadth_payload = _load_json(p1_benchmark_breadth)
    real_project_payload = _load_json(real_project_status)
    customer_shadow_payload = _load_json(customer_shadow_status)

    p0_ready = bool(p0_payload.get("p0_closed", False) or str(p0_payload.get("status", "")) == "closed")
    p1_ready = bool(p1_payload.get("p1_execution_unblocked", False) or str(p1_payload.get("status", "")) == "ready")
    p1_breadth_ready = bool(str(p1_breadth_payload.get("status", "")) == "ready" or _truthy_contract(p1_breadth_payload))
    real_project_ready = bool(real_project_payload.get("contract_pass", False))
    customer_shadow_ready = bool(customer_shadow_payload.get("contract_pass", False))
    customer_shadow_count = _int_from_summary(customer_shadow_payload, "completed_shadow_case_count")
    customer_shadow_min = _int_from_summary(customer_shadow_payload, "min_completed_shadow_cases", default=3)

    prerequisite_rows = [
        _prerequisite_row("p0_closed", p0_ready, p0_status),
        _prerequisite_row("p1_readiness_unblocked", p1_ready, p1_readiness),
        _prerequisite_row("p1_benchmark_breadth_ready", p1_breadth_ready, p1_benchmark_breadth),
        _prerequisite_row("real_project_measured_status_pass", real_project_ready, real_project_status),
        _prerequisite_row(
            "customer_shadow_completed_project_cases_ready",
            customer_shadow_ready,
            customer_shadow_status,
            summary={
                "completed_shadow_case_count": customer_shadow_count,
                "min_completed_shadow_cases": customer_shadow_min,
            },
        ),
    ]

    missing_features = [row["check"] for row in feature_rows if not row["pass"]]
    missing_deferred = [row["check"] for row in deferred_rows if not row["pass"]]
    prohibited_claims = [row["check"] for row in prohibited_rows if not row["pass"]]
    failed_prerequisites = [row["check"] for row in prerequisite_rows if not row["pass"]]

    scope_contract_pass = bool(not missing_features and not missing_deferred and not prohibited_claims)
    launch_ready = bool(scope_contract_pass and not failed_prerequisites)
    blockers = [
        *(f"evidence_console_feature_missing:{item}" for item in missing_features),
        *(f"deferred_gui_surface_missing:{item}" for item in missing_deferred),
        *(f"prohibited_first_scope_claim_present:{item}" for item in prohibited_claims),
        *(f"launch_prerequisite_blocked:{item}" for item in failed_prerequisites),
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                scope_source,
                *claim_boundary_docs,
                p0_status,
                p1_readiness,
                p1_benchmark_breadth,
                real_project_status,
                customer_shadow_status,
            ],
            reused_evidence=True,
            reuse_policy="status_rebuilt_from_existing_scope_docs_and_readiness_receipts",
        ),
        "status": "ready" if launch_ready else "blocked",
        "contract_pass": launch_ready,
        "scope_contract_pass": scope_contract_pass,
        "launch_ready": launch_ready,
        "reason_code": "PASS" if launch_ready else "ERR_EVIDENCE_CONSOLE_SCOPE_OR_PREREQUISITES_BLOCKED",
        "summary_line": (
            f"Evidence Console scope: {'READY' if launch_ready else 'BLOCKED'} | "
            f"features={len(feature_rows) - len(missing_features)}/{len(feature_rows)} | "
            f"deferred_gui={len(deferred_rows) - len(missing_deferred)}/{len(deferred_rows)} | "
            f"prerequisites={len(prerequisite_rows) - len(failed_prerequisites)}/{len(prerequisite_rows)}"
        ),
        "summary": {
            "scope_source": str(scope_source),
            "claim_boundary_docs": [str(path) for path in claim_boundary_docs],
            "evidence_console_feature_count": len(feature_rows),
            "evidence_console_feature_pass_count": len(feature_rows) - len(missing_features),
            "deferred_gui_surface_count": len(deferred_rows),
            "deferred_gui_surface_pass_count": len(deferred_rows) - len(missing_deferred),
            "launch_prerequisite_count": len(prerequisite_rows),
            "launch_prerequisite_pass_count": len(prerequisite_rows) - len(failed_prerequisites),
            "customer_shadow_completed_case_count": customer_shadow_count,
            "customer_shadow_min_completed_cases": customer_shadow_min,
            "next_action": (
                "attach validated customer completed-project shadow evidence"
                if "customer_shadow_completed_project_cases_ready" in failed_prerequisites
                else "keep Evidence Console limited to reviewer evidence workflows"
            ),
        },
        "checks": {
            "scope_source_present": scope_source.exists(),
            "evidence_console_features_present": not missing_features,
            "deferred_gui_surfaces_present": not missing_deferred,
            "no_prohibited_first_scope_claims": not prohibited_claims,
            "launch_prerequisites_pass": not failed_prerequisites,
            "customer_shadow_prerequisite_pass": customer_shadow_ready,
        },
        "feature_rows": feature_rows,
        "deferred_gui_surface_rows": deferred_rows,
        "prohibited_first_scope_claim_rows": prohibited_rows,
        "prerequisite_rows": prerequisite_rows,
        "blockers": blockers,
        "claim_boundary": (
            "This status defines the first GUI surface as an Evidence Console only. It must not be treated "
            "as approval for a full project dashboard, model editor, account/permission system, collaboration, "
            "or licensing workflow. Launch readiness remains blocked until validated customer completed-project "
            "shadow evidence is attached; synthetic customer cases must not close this gate."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Evidence Console Scope Status",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `scope_contract_pass`: `{payload['scope_contract_pass']}`",
        f"- `launch_ready`: `{payload['launch_ready']}`",
        "",
        "| Evidence Console Feature | Pass |",
        "|---|---|",
    ]
    for row in payload["feature_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    lines.extend(["", "| Deferred GUI Surface | Visible |", "|---|---|"])
    for row in payload["deferred_gui_surface_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    lines.extend(["", "| Launch Prerequisite | Pass |", "|---|---|"])
    for row in payload["prerequisite_rows"]:
        lines.append(f"| `{row['check']}` | `{row['pass']}` |")
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{item}`" for item in payload["blockers"])
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-source", type=Path, default=DEFAULT_SCOPE_SOURCE)
    parser.add_argument(
        "--claim-boundary-doc",
        action="append",
        type=Path,
        dest="claim_boundary_docs",
        default=None,
    )
    parser.add_argument("--p0-status", type=Path, default=DEFAULT_P0_STATUS)
    parser.add_argument("--p1-readiness", type=Path, default=DEFAULT_P1_READINESS)
    parser.add_argument("--p1-benchmark-breadth", type=Path, default=DEFAULT_P1_BENCHMARK_BREADTH)
    parser.add_argument("--real-project-status", type=Path, default=DEFAULT_REAL_PROJECT_STATUS)
    parser.add_argument("--customer-shadow-status", type=Path, default=DEFAULT_CUSTOMER_SHADOW_STATUS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_status(
        scope_source=args.scope_source,
        claim_boundary_docs=tuple(args.claim_boundary_docs)
        if args.claim_boundary_docs is not None
        else DEFAULT_CLAIM_BOUNDARY_DOCS,
        p0_status=args.p0_status,
        p1_readiness=args.p1_readiness,
        p1_benchmark_breadth=args.p1_benchmark_breadth,
        real_project_status=args.real_project_status,
        customer_shadow_status=args.customer_shadow_status,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else payload["summary_line"])
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
