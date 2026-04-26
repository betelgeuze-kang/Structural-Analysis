#!/usr/bin/env python3
"""Generate KDS-style compliance package from Phase1 reports."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

try:
    from implementation.phase1.code_check_engine import evaluate_code_compliance
except ImportError:  # pragma: no cover - script execution fallback
    from code_check_engine import evaluate_code_compliance


REASONS = {
    "PASS": "kds compliance package generated",
    "ERR_INPUT": "input report missing or invalid",
    "ERR_KDS_COMPLIANCE_FAIL": "kds compliance checks failed",
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _finite(v: object, default: float = math.nan) -> float:
    try:
        x = float(v)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def _status_row(item: str, criterion: str, value: str, passed: bool, evidence: str) -> dict:
    return {
        "item": item,
        "criterion": criterion,
        "value": value,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence,
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item", "criterion", "value", "status", "evidence"])
        w.writeheader()
        w.writerows(rows)


def _write_markdown(
    *,
    path: Path,
    project_name: str,
    code_name: str,
    rows: list[dict],
    frontend_payload: dict,
    pbd_path: Path,
    commercial_path: Path,
    member_force_path: Path | None,
    design_change_csv: Path | None,
) -> None:
    lines: list[str] = []
    lines.append("# KDS Compliance Report")
    lines.append("")
    lines.append(f"- Project: `{project_name}`")
    lines.append(f"- Design code basis: `{code_name}`")
    lines.append(f"- Generated at (UTC): `{datetime.now(timezone.utc).isoformat()}`")
    lines.append("")
    lines.append("## Input Reports")
    lines.append(f"- PBD review package: `{pbd_path}`")
    lines.append(f"- Commercial CSV gate: `{commercial_path}`")
    if member_force_path is not None:
        lines.append(f"- Member force gate: `{member_force_path}`")
    if design_change_csv is not None:
        lines.append(f"- Design change evidence: `{design_change_csv}`")
    lines.append("")
    lines.append("## Compliance Table")
    lines.append("| Item | Criterion | Value | Status | Evidence |")
    lines.append("|---|---|---:|:---:|---|")
    for r in rows:
        lines.append(
            f"| {r['item']} | {r['criterion']} | {r['value']} | {r['status']} | {r['evidence']} |"
        )
    rc_rows = frontend_payload.get("governing_rc_checks_top100", []) if isinstance(frontend_payload, dict) else []
    steel_rows = frontend_payload.get("governing_steel_checks_top100", []) if isinstance(frontend_payload, dict) else []
    ng_combo = frontend_payload.get("ng_members_by_combination", []) if isinstance(frontend_payload, dict) else []
    family_env = frontend_payload.get("member_family_dcr_envelope", []) if isinstance(frontend_payload, dict) else []
    combo_prov = frontend_payload.get("combination_provenance_rows", []) if isinstance(frontend_payload, dict) else []
    if rc_rows:
        lines.append("")
        lines.append("## RC Governing Checks")
        lines.append("| Member | Component | Clause | DCR |")
        lines.append("|---|---|---|---:|")
        for row in rc_rows[:20]:
            lines.append(
                f"| {row.get('member_id','')} | {row.get('component','')} | {row.get('clause','')} | {float(row.get('dcr',0.0)):.4f} |"
            )
    if steel_rows:
        lines.append("")
        lines.append("## Steel Governing Checks")
        lines.append("| Member | Component | Clause | DCR |")
        lines.append("|---|---|---|---:|")
        for row in steel_rows[:20]:
            lines.append(
                f"| {row.get('member_id','')} | {row.get('component','')} | {row.get('clause','')} | {float(row.get('dcr',0.0)):.4f} |"
            )
    if ng_combo:
        lines.append("")
        lines.append("## NG Members By Combination")
        lines.append("| Combination | NG Members | Max DCR |")
        lines.append("|---|---:|---:|")
        for row in ng_combo[:20]:
            lines.append(
                f"| {row.get('combination','')} | {int(row.get('ng_member_count',0))} | {float(row.get('max_dcr',0.0)):.4f} |"
            )
    if family_env:
        lines.append("")
        lines.append("## Member Family DCR Envelope")
        lines.append("| Member Type | Max DCR | Governing Clause |")
        lines.append("|---|---:|---|")
        for row in family_env:
            lines.append(
                f"| {row.get('member_type','')} | {float(row.get('max_dcr',0.0)):.4f} | {row.get('governing_clause','')} |"
            )
    if combo_prov:
        lines.append("")
        lines.append("## Combination Provenance")
        lines.append("| KDS Combination | Runtime Combination | Match Score |")
        lines.append("|---|---|---:|")
        for row in combo_prov[:20]:
            lines.append(
                f"| {row.get('kds_name','')} | {row.get('matched_runtime_name','')} | {float(row.get('match_score',0.0)):.4f} |"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pdf(path: Path, title: str, rows: list[dict], frontend_payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.5, 11.0))
        fig.clf()
        y = 0.96
        fig.text(0.07, y, title, fontsize=16, weight="bold", va="top")
        y -= 0.04
        fig.text(0.07, y, f"Generated (UTC): {datetime.now(timezone.utc).isoformat()}", fontsize=10, va="top")
        y -= 0.04
        for r in rows:
            line = f"[{r['status']}] {r['item']} | {r['criterion']} | {r['value']} | {r['evidence']}"
            fig.text(0.07, y, line, fontsize=9, va="top")
            y -= 0.027
            if y < 0.08:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig = plt.figure(figsize=(8.5, 11.0))
                fig.clf()
                y = 0.96
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        sections = [
            ("RC Governing Checks", frontend_payload.get("governing_rc_checks_top100", [])[:25]),
            ("Steel Governing Checks", frontend_payload.get("governing_steel_checks_top100", [])[:25]),
            ("NG Members By Combination", frontend_payload.get("ng_members_by_combination", [])[:25]),
            ("Member Family DCR Envelope", frontend_payload.get("member_family_dcr_envelope", [])[:25]),
            ("Combination Provenance", frontend_payload.get("combination_provenance_rows", [])[:25]),
        ]
        for title_text, items in sections:
            if not items:
                continue
            fig = plt.figure(figsize=(8.5, 11.0))
            fig.clf()
            y = 0.96
            fig.text(0.07, y, title_text, fontsize=15, weight="bold", va="top")
            y -= 0.05
            for item in items:
                line = json.dumps(item, ensure_ascii=False)
                fig.text(0.07, y, line[:150], fontsize=8.5, va="top")
                y -= 0.03
                if y < 0.08:
                    pdf.savefig(fig, bbox_inches="tight")
                    plt.close(fig)
                    fig = plt.figure(figsize=(8.5, 11.0))
                    fig.clf()
                    y = 0.96
                    fig.text(0.07, y, title_text, fontsize=15, weight="bold", va="top")
                    y -= 0.05
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


def _build_frontend_payload(*, rows: list[dict], code_check_report: dict | None) -> dict:
    status_counts = {"PASS": 0, "FAIL": 0}
    for r in rows:
        st = str(r.get("status", "FAIL"))
        if st not in status_counts:
            status_counts[st] = 0
        status_counts[st] += 1

    member_rows: list[dict] = []
    combo_rows: list[dict] = []
    member_check_rows: list[dict] = []
    rc_detail_rows: list[dict] = []
    steel_detail_rows: list[dict] = []
    combo_prov_rows: list[dict] = []
    member_type_counts: dict[str, int] = {}
    clause_set: set[str] = set()
    code_summary = code_check_report.get("summary") if isinstance((code_check_report or {}).get("summary"), dict) else {}
    if isinstance(code_check_report, dict):
        raw_rows = code_check_report.get("rows")
        if isinstance(raw_rows, list):
            for r in raw_rows:
                if not isinstance(r, dict):
                    continue
                member_rows.append(
                    {
                        "case_id": str(r.get("case_id", "")),
                        "member_id": str(r.get("member_id", r.get("case_id", ""))),
                        "member_type": str(r.get("member_type", "generic_frame")),
                        "governing_component": str(r.get("governing_component", "")),
                        "governing_combination": str(r.get("governing_combination", "")),
                        "governing_scale": float(_finite(r.get("governing_scale"), 0.0)),
                        "max_dcr": float(_finite(r.get("max_dcr"), 0.0)),
                    }
                )
            member_rows.sort(key=lambda x: float(x["max_dcr"]), reverse=True)
        raw_combo_rows = code_check_report.get("combination_rows")
        if isinstance(raw_combo_rows, list):
            for r in raw_combo_rows:
                if not isinstance(r, dict):
                    continue
                member_type = str(r.get("member_type", "generic_frame"))
                member_type_counts[member_type] = int(member_type_counts.get(member_type, 0) + 1)
                clause_set.add(str(r.get("clause", "")))
                combo_rows.append(
                    {
                        "member_id": str(r.get("member_id", "")),
                        "case_id": str(r.get("case_id", "")),
                        "member_type": member_type,
                        "combination": str(r.get("combination", "")),
                        "component": str(r.get("component", "")),
                        "clause": str(r.get("clause", "")),
                        "rule_family": str(r.get("rule_family", "")),
                        "dcr": float(_finite(r.get("dcr"), 0.0)),
                    }
                )
            combo_rows.sort(key=lambda x: float(x["dcr"]), reverse=True)
        raw_check_rows = code_check_report.get("member_check_rows")
        if isinstance(raw_check_rows, list):
            for r in raw_check_rows:
                if not isinstance(r, dict):
                    continue
                clause_set.add(str(r.get("clause", "")))
                member_check_rows.append(
                    {
                        "member_id": str(r.get("member_id", "")),
                        "case_id": str(r.get("case_id", "")),
                        "member_type": str(r.get("member_type", "generic_frame")),
                        "hazard_type": str(r.get("hazard_type", "")),
                        "topology_type": str(r.get("topology_type", "")),
                        "rule_family": str(r.get("rule_family", "")),
                        "combination": str(r.get("combination", "")),
                        "component": str(r.get("component", "")),
                        "clause": str(r.get("clause", "")),
                        "dcr": float(_finite(r.get("dcr"), 0.0)),
                    }
                )
                if str(r.get("rule_family", "")) == "rc_detail":
                    rc_detail_rows.append(
                        {
                            "member_id": str(r.get("member_id", "")),
                            "case_id": str(r.get("case_id", "")),
                            "member_type": str(r.get("member_type", "generic_frame")),
                            "combination": str(r.get("combination", "")),
                            "component": str(r.get("component", "")),
                            "clause": str(r.get("clause", "")),
                            "dcr": float(_finite(r.get("dcr"), 0.0)),
                        }
                    )
                if str(r.get("rule_family", "")) == "steel_detail":
                    steel_detail_rows.append(
                        {
                            "member_id": str(r.get("member_id", "")),
                            "case_id": str(r.get("case_id", "")),
                            "member_type": str(r.get("member_type", "generic_frame")),
                            "combination": str(r.get("combination", "")),
                            "component": str(r.get("component", "")),
                            "clause": str(r.get("clause", "")),
                            "dcr": float(_finite(r.get("dcr"), 0.0)),
                        }
                    )
        raw_combo_prov = code_check_report.get("combination_provenance_rows")
        if isinstance(raw_combo_prov, list):
            for row in raw_combo_prov:
                if not isinstance(row, dict):
                    continue
                combo_prov_rows.append(
                    {
                        "kds_name": str(row.get("kds_name", "")),
                        "matched_runtime_name": str(row.get("matched_runtime_name", "")),
                        "match_score": float(_finite(row.get("match_score"), 0.0)),
                    }
                )
        member_check_rows.sort(key=lambda x: float(x["dcr"]), reverse=True)
        rc_detail_rows.sort(key=lambda x: float(x["dcr"]), reverse=True)
        steel_detail_rows.sort(key=lambda x: float(x["dcr"]), reverse=True)

    ng_count = sum(1 for r in member_rows if float(r.get("max_dcr", 0.0)) > 1.0)
    ng_members_by_combination: list[dict] = []
    by_combo: dict[str, dict] = {}
    for row in member_check_rows:
        combo = str(row.get("combination", ""))
        rec = by_combo.setdefault(combo, {"combination": combo, "ng_member_count": 0, "max_dcr": 0.0})
        dcr = float(row.get("dcr", 0.0))
        if dcr > 1.0:
            rec["ng_member_count"] = int(rec["ng_member_count"]) + 1
        rec["max_dcr"] = max(float(rec["max_dcr"]), dcr)
    ng_members_by_combination = sorted(by_combo.values(), key=lambda item: (int(item["ng_member_count"]), float(item["max_dcr"])), reverse=True)

    member_family_dcr_envelope: list[dict] = []
    by_family: dict[str, dict] = {}
    for row in member_check_rows:
        member_type = str(row.get("member_type", "generic_frame"))
        rec = by_family.setdefault(member_type, {"member_type": member_type, "max_dcr": 0.0, "governing_clause": ""})
        dcr = float(row.get("dcr", 0.0))
        if dcr >= float(rec["max_dcr"]):
            rec["max_dcr"] = dcr
            rec["governing_clause"] = str(row.get("clause", ""))
    member_family_dcr_envelope = sorted(by_family.values(), key=lambda item: float(item["max_dcr"]), reverse=True)

    return {
        "schema_version": "1.0",
        "view": "kds_code_check_dashboard",
        "summary": {
            "member_count": int(code_summary.get("member_count", len(member_rows))),
            "member_type_count": int(code_summary.get("member_type_count", len(member_type_counts))),
            "combination_count": int(code_summary.get("combination_count", 0)),
            "combination_row_count": int(code_summary.get("combination_row_count", len(combo_rows))),
            "member_check_row_count": int(code_summary.get("member_check_row_count", len(member_check_rows))),
            "clause_count": int(code_summary.get("clause_count", len(clause_set))),
            "rc_rule_row_count": int(code_summary.get("rc_rule_row_count", len(rc_detail_rows))),
            "steel_rule_row_count": int(code_summary.get("steel_rule_row_count", len(steel_detail_rows))),
        },
        "summary_cards": [
            {"id": "total_items", "label": "Items", "value": int(len(rows)), "status": "INFO"},
            {"id": "pass_items", "label": "PASS", "value": int(status_counts.get("PASS", 0)), "status": "PASS"},
            {"id": "fail_items", "label": "FAIL", "value": int(status_counts.get("FAIL", 0)), "status": "FAIL" if int(status_counts.get("FAIL", 0)) > 0 else "PASS"},
            {"id": "member_ng", "label": "Member NG", "value": int(ng_count), "status": "FAIL" if int(ng_count) > 0 else "PASS"},
            {"id": "combo_rows", "label": "Combo Rows", "value": int(len(combo_rows)), "status": "INFO"},
            {"id": "member_types", "label": "Member Types", "value": int(len(member_type_counts)), "status": "INFO"},
            {"id": "member_checks", "label": "Member Checks", "value": int(len(member_check_rows)), "status": "INFO"},
            {"id": "rc_checks", "label": "RC Detail", "value": int(len(rc_detail_rows)), "status": "INFO"},
            {"id": "steel_checks", "label": "Steel Detail", "value": int(len(steel_detail_rows)), "status": "INFO"},
            {"id": "clauses", "label": "Clauses", "value": int(len(clause_set)), "status": "INFO"},
        ],
        "compliance_rows": [
            {
                "item": str(r.get("item", "")),
                "criterion": str(r.get("criterion", "")),
                "value": str(r.get("value", "")),
                "status": str(r.get("status", "")),
                "evidence": str(r.get("evidence", "")),
            }
            for r in rows
        ] + [
            {
                "item": f"{row.get('case_id', '')}:{row.get('component', '')}",
                "criterion": f"{row.get('combination', '')} / {row.get('clause', '')}",
                "value": f"{float(row.get('dcr', 0.0)):.4f}",
                "status": "PASS" if float(row.get("dcr", 0.0)) <= 1.0 else "FAIL",
                "evidence": str(row.get("member_type", "")),
            }
            for row in member_check_rows[:500]
        ],
        "governing_members_top50": member_rows[:50],
        "governing_combo_rows_top150": combo_rows[:150],
        "governing_member_checks_top500": member_check_rows[:500],
        "governing_rc_checks_top100": rc_detail_rows[:100],
        "governing_steel_checks_top100": steel_detail_rows[:100],
        "ng_members_by_combination": ng_members_by_combination[:100],
        "member_family_dcr_envelope": member_family_dcr_envelope,
        "combination_provenance_rows": combo_prov_rows[:100],
    }


def _parse_scales(raw: str) -> list[float]:
    out: list[float] = []
    for tok in str(raw).split(","):
        s = tok.strip()
        if not s:
            continue
        out.append(float(s))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project-name", default="Phase1 Structural AI Solver")
    p.add_argument("--code-name", default="KDS 41 / KDS seismic submission format")
    p.add_argument("--pbd-review-package", default="implementation/phase1/release/pbd_review/pbd_review_package_report.json")
    p.add_argument("--pbd-compliance-slice-report", default="implementation/phase1/release/pbd_review/pbd_review_compliance_slice_report.json")
    p.add_argument("--commercial-csv-gate", default="implementation/phase1/commercial_csv_gate_report.json")
    p.add_argument("--member-force-gate", default="implementation/phase1/member_force_soft_accept_report.json")
    p.add_argument("--require-member-force-gate", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--run-code-check", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--code-check-report", default="implementation/phase1/release/kds_compliance/code_check_report.json")
    p.add_argument("--code-check-hf-csv", default="implementation/phase1/commercial_hf_export_sample.csv")
    p.add_argument("--axial-capacity-kN", type=float, default=2200.0)
    p.add_argument("--shear-capacity-kN", type=float, default=380.0)
    p.add_argument("--moment-capacity-kNm", type=float, default=2600.0)
    p.add_argument("--code-check-combination-family", default="KDS-2022")
    p.add_argument("--code-check-limit-state", default="ULS")
    p.add_argument("--code-check-combination-scales", default="")
    p.add_argument("--code-check-load-comb-model-json", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument(
        "--design-optimization-cost-reduction-report",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_report.json",
    )
    p.add_argument(
        "--design-optimization-cost-reduction-changes-csv",
        default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.csv",
    )
    p.add_argument("--max-code-check-dcr", type=float, default=1.25)
    p.add_argument("--max-drift-envelope-pct", type=float, default=2.0)
    p.add_argument("--max-member-force-p95-pct", type=float, default=5.0)
    p.add_argument("--max-member-force-soft-ratio", type=float, default=0.25)
    p.add_argument("--max-energy-balance-rel-error", type=float, default=1e-2)
    p.add_argument("--out-dir", default="implementation/phase1/release/kds_compliance")
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reason_code = "PASS"
    rows: list[dict] = []
    member_force_required = bool(args.require_member_force_gate)
    code_check_report: dict | None = None
    design_opt_report: dict | None = None

    try:
        pbd = _load_json(Path(args.pbd_review_package))
        pbd_slice_path = Path(args.pbd_compliance_slice_report)
        pbd_slice = _load_json(pbd_slice_path) if pbd_slice_path.exists() else {}
        commercial = _load_json(Path(args.commercial_csv_gate))
        member_force: dict | None = None
        member_force_path = Path(args.member_force_gate)
        if member_force_required or member_force_path.exists():
            member_force = _load_json(member_force_path)
        else:
            member_force_path = None
        if Path(args.design_optimization_cost_reduction_report).exists():
            design_opt_report = _load_json(Path(args.design_optimization_cost_reduction_report))
    except Exception as exc:
        reason_code = "ERR_INPUT"
        pbd = {}
        commercial = {}
        member_force = None
        member_force_path = None
        rows.append(
            _status_row(
                "Input Integrity",
                "all required input reports exist and valid json",
                "N/A",
                False,
                str(exc),
            )
        )

    if reason_code == "PASS":
        pbd_metrics = pbd.get("metrics") if isinstance(pbd.get("metrics"), dict) else {}
        pbd_slice_metrics = pbd_slice.get("metrics") if isinstance(pbd_slice.get("metrics"), dict) else {}
        pbd_source_metrics = pbd_slice_metrics if pbd_slice_metrics else pbd_metrics
        comm_metrics = commercial.get("metrics") if isinstance(commercial.get("metrics"), dict) else {}
        comm_checks = commercial.get("checks") if isinstance(commercial.get("checks"), dict) else {}
        mf_summary = member_force.get("summary") if isinstance((member_force or {}).get("summary"), dict) else {}
        mf_checks = member_force.get("checks") if isinstance((member_force or {}).get("checks"), dict) else {}

        drift_env = _finite(pbd_source_metrics.get("drift_envelope_max_pct"), math.nan)
        converged = bool(pbd_source_metrics.get("all_cases_converged", False))
        conv_ratio = _finite(pbd_source_metrics.get("converged_step_ratio_min"), 0.0)
        energy_err = abs(_finite(pbd_source_metrics.get("energy_balance_relative_error_ref"), math.inf))
        drift_err = _finite(comm_metrics.get("drift_error_pct"), math.inf)
        base_shear_err = _finite(comm_metrics.get("base_shear_error_pct"), math.inf)
        buckling_err = _finite(comm_metrics.get("buckling_factor_error_pct"), math.inf)
        mac = _finite(comm_metrics.get("mode_shape_mac"), -math.inf)
        mf_p95 = _finite(mf_summary.get("error_pct_p95"), math.inf)
        mf_soft_ratio = _finite(mf_summary.get("soft_accept_case_ratio"), math.inf)

        rows.append(
            _status_row(
                "Drift Envelope",
                f"max drift <= {float(args.max_drift_envelope_pct):.3f}%",
                f"{drift_env:.4f}%",
                bool(math.isfinite(drift_env) and drift_env <= float(args.max_drift_envelope_pct)),
                "PBD drift envelope (compliance slice preferred)",
            )
        )
        rows.append(
            _status_row(
                "Time-Step Convergence",
                "all cases converged and min converged-step ratio == 1.0",
                f"all={converged}, min_ratio={conv_ratio:.4f}",
                bool(converged and conv_ratio >= 1.0),
                "NDTHA convergence summary",
            )
        )
        rows.append(
            _status_row(
                "Energy Balance",
                f"relative error <= {float(args.max_energy_balance_rel_error):.2e}",
                f"{energy_err:.6e}",
                bool(math.isfinite(energy_err) and energy_err <= float(args.max_energy_balance_rel_error)),
                "thermodynamic integrity check",
            )
        )
        rows.append(
            _status_row(
                "HF Drift Error",
                "commercial gate drift error <= 5%",
                f"{drift_err:.4f}%",
                bool(math.isfinite(drift_err) and drift_err <= 5.0 and bool(comm_checks.get("drift_within_5pct", False))),
                "commercial csv direct compare",
            )
        )
        rows.append(
            _status_row(
                "HF Base Shear Error",
                "commercial gate base shear error <= 5%",
                f"{base_shear_err:.4f}%",
                bool(
                    math.isfinite(base_shear_err)
                    and base_shear_err <= 5.0
                    and bool(comm_checks.get("base_shear_within_5pct", False))
                ),
                "commercial csv direct compare",
            )
        )
        rows.append(
            _status_row(
                "HF Buckling Error",
                "commercial gate buckling factor error <= 5%",
                f"{buckling_err:.4f}%",
                bool(
                    math.isfinite(buckling_err)
                    and buckling_err <= 5.0
                    and bool(comm_checks.get("buckling_within_5pct", False))
                ),
                "commercial csv direct compare",
            )
        )
        rows.append(
            _status_row(
                "Mode Shape MAC",
                "commercial gate mode shape MAC >= 0.95",
                f"{mac:.5f}",
                bool(math.isfinite(mac) and mac >= 0.95 and bool(comm_checks.get("mac_above_095", False))),
                "commercial csv direct compare",
            )
        )

        if member_force is not None:
            rows.append(
                _status_row(
                    "Member Axial Force (p95)",
                    f"p95 error <= {float(args.max_member_force_p95_pct):.3f}%",
                    f"{mf_p95:.4f}%",
                    bool(
                        math.isfinite(mf_p95)
                        and mf_p95 <= float(args.max_member_force_p95_pct)
                        and bool(mf_checks.get("member_force_metric_present", False))
                    ),
                    "member-force soft-accept report",
                )
            )
            rows.append(
                _status_row(
                    "Member Force Soft-Accept Ratio",
                    f"soft-accept ratio <= {float(args.max_member_force_soft_ratio):.3f}",
                    f"{mf_soft_ratio:.5f}",
                    bool(
                        math.isfinite(mf_soft_ratio)
                        and mf_soft_ratio <= float(args.max_member_force_soft_ratio)
                        and bool(mf_checks.get("soft_accept_gate_pass", False))
                    ),
                    "member-force soft-accept report",
                )
            )
        elif member_force_required:
            rows.append(
                _status_row(
                    "Member Force Gate",
                    "member force gate report is required",
                    "missing",
                    False,
                    "require-member-force-gate=true",
                )
            )
        if isinstance(design_opt_report, dict):
            dos = design_opt_report.get("summary") if isinstance(design_opt_report.get("summary"), dict) else {}
            rows.append(
                _status_row(
                    "Design Change Evidence",
                    "feasible input and cost reduction report present",
                    (
                        f"accepted={int(dos.get('accepted_count', 0))}, "
                        f"changed={int(dos.get('changed_group_count', 0))}, "
                        f"cost_delta={_finite(dos.get('cost_reduction_proxy'), 0.0):.3f}"
                    ),
                    bool(
                        bool(design_opt_report.get("contract_pass", False))
                        and bool(dos.get("feasible_input", False))
                        and not bool(dos.get("blocked", True))
                    ),
                    "design optimization cost reduction report",
                )
            )

        if bool(args.run_code_check):
            code_check_out = Path(args.code_check_report)
            code_check_out.parent.mkdir(parents=True, exist_ok=True)
            try:
                code_check_report = evaluate_code_compliance(
                    hf_csv=Path(args.code_check_hf_csv),
                    capacity={
                        "axial_capacity_kN": float(args.axial_capacity_kN),
                        "shear_capacity_kN": float(args.shear_capacity_kN),
                        "moment_capacity_kNm": float(args.moment_capacity_kNm),
                    },
                    combination_scales=_parse_scales(str(args.code_check_combination_scales)),
                    max_dcr=float(args.max_code_check_dcr),
                    combination_family=str(args.code_check_combination_family),
                    combination_limit_state=str(args.code_check_limit_state),
                    load_combination_model=(
                        _load_json(Path(args.code_check_load_comb_model_json))
                        if str(args.code_check_load_comb_model_json).strip()
                        and Path(args.code_check_load_comb_model_json).exists()
                        else None
                    ),
                )
            except Exception as exc:
                code_check_report = {
                    "contract_pass": False,
                    "reason_code": "ERR_INPUT",
                    "reason": str(exc),
                }
            code_check_out.write_text(json.dumps(code_check_report, indent=2), encoding="utf-8")

            code_summary = code_check_report.get("summary") if isinstance(code_check_report.get("summary"), dict) else {}
            code_checks = code_check_report.get("checks") if isinstance(code_check_report.get("checks"), dict) else {}
            max_dcr_val = _finite(code_summary.get("max_dcr"), math.inf)
            rows.append(
                _status_row(
                    "Code Check D/C",
                    f"max D/C <= {float(args.max_code_check_dcr):.3f}",
                    f"{max_dcr_val:.4f}",
                    bool(
                        bool(code_check_report.get("contract_pass", False))
                        and bool(code_checks.get("max_dcr_pass", False))
                        and math.isfinite(max_dcr_val)
                        and max_dcr_val <= float(args.max_code_check_dcr)
                    ),
                    f"code_check_report: {code_check_out}",
                )
            )

    contract_pass = bool(reason_code == "PASS" and all(r["status"] == "PASS" for r in rows))
    if reason_code == "PASS" and not contract_pass:
        reason_code = "ERR_KDS_COMPLIANCE_FAIL"

    csv_out = out_dir / "kds_compliance_table.csv"
    md_out = out_dir / "kds_compliance_report.md"
    pdf_out = out_dir / "kds_compliance_report.pdf"
    frontend_out = out_dir / "kds_frontend_payload.json"
    summary_json = out_dir / "kds_compliance_summary.json"
    frontend_payload = _build_frontend_payload(rows=rows, code_check_report=code_check_report if isinstance(code_check_report, dict) else None)
    _write_csv(csv_out, rows)
    _write_markdown(
        path=md_out,
        project_name=str(args.project_name),
        code_name=str(args.code_name),
        rows=rows,
        frontend_payload=frontend_payload,
        pbd_path=Path(args.pbd_review_package),
        commercial_path=Path(args.commercial_csv_gate),
        member_force_path=Path(args.member_force_gate) if (member_force_required or Path(args.member_force_gate).exists()) else None,
        design_change_csv=Path(args.design_optimization_cost_reduction_changes_csv) if Path(args.design_optimization_cost_reduction_changes_csv).exists() else None,
    )
    _write_pdf(pdf_out, title="KDS Compliance Summary", rows=rows, frontend_payload=frontend_payload)
    frontend_out.write_text(json.dumps(frontend_payload, indent=2), encoding="utf-8")
    frontend_summary = frontend_payload.get("summary") if isinstance(frontend_payload.get("summary"), dict) else {}

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-kds-compliance-package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "project_name": str(args.project_name),
                "code_name": str(args.code_name),
                "pbd_review_package": str(args.pbd_review_package),
                "pbd_compliance_slice_report": str(args.pbd_compliance_slice_report),
                "commercial_csv_gate": str(args.commercial_csv_gate),
                "member_force_gate": str(args.member_force_gate),
                "require_member_force_gate": bool(args.require_member_force_gate),
                "run_code_check": bool(args.run_code_check),
                "code_check_report": str(args.code_check_report),
                "code_check_hf_csv": str(args.code_check_hf_csv),
                "axial_capacity_kN": float(args.axial_capacity_kN),
                "shear_capacity_kN": float(args.shear_capacity_kN),
                "moment_capacity_kNm": float(args.moment_capacity_kNm),
                "code_check_combination_family": str(args.code_check_combination_family),
                "code_check_limit_state": str(args.code_check_limit_state),
                "code_check_combination_scales": str(args.code_check_combination_scales),
                "design_optimization_cost_reduction_report": str(args.design_optimization_cost_reduction_report),
                "design_optimization_cost_reduction_changes_csv": str(args.design_optimization_cost_reduction_changes_csv),
                "max_code_check_dcr": float(args.max_code_check_dcr),
                "max_drift_envelope_pct": float(args.max_drift_envelope_pct),
                "max_member_force_p95_pct": float(args.max_member_force_p95_pct),
                "max_member_force_soft_ratio": float(args.max_member_force_soft_ratio),
                "max_energy_balance_rel_error": float(args.max_energy_balance_rel_error),
            },
        "summary": {
            "status_item_count": int(len(rows)),
            "pass_item_count": int(sum(1 for r in rows if str(r.get("status")) == "PASS")),
            "fail_item_count": int(sum(1 for r in rows if str(r.get("status")) == "FAIL")),
            "summary_card_count": int(len(frontend_payload.get("summary_cards", []))),
            "compliance_row_count": int(len(frontend_payload.get("compliance_rows", []))),
            "member_check_row_count": int(frontend_summary.get("member_check_row_count", 0)),
            "combination_row_count": int(frontend_summary.get("combination_row_count", 0)),
            "clause_count": int(frontend_summary.get("clause_count", 0)),
            "member_type_count": int(frontend_summary.get("member_type_count", 0)),
            "rc_rule_row_count": int((code_check_report or {}).get("summary", {}).get("rc_rule_row_count", 0)) if isinstance(code_check_report, dict) else 0,
            "steel_rule_row_count": int((code_check_report or {}).get("summary", {}).get("steel_rule_row_count", 0)) if isinstance(code_check_report, dict) else 0,
        },
        "rows": rows,
        "artifacts": {
            "kds_compliance_csv": str(csv_out),
            "kds_compliance_markdown": str(md_out),
            "kds_compliance_pdf": str(pdf_out),
            "kds_frontend_payload_json": str(frontend_out),
            "code_check_report": str(args.code_check_report) if bool(args.run_code_check) else "",
            "design_change_csv": str(args.design_optimization_cost_reduction_changes_csv) if Path(args.design_optimization_cost_reduction_changes_csv).exists() else "",
            "design_change_report": str(args.design_optimization_cost_reduction_report) if Path(args.design_optimization_cost_reduction_report).exists() else "",
        },
        "frontend_payload": frontend_payload,
        "code_check_report": code_check_report if isinstance(code_check_report, dict) else {},
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    summary_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote KDS compliance package: {summary_json}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
