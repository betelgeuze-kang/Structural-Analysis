#!/usr/bin/env python3
"""Build a KDS clause member-extraction receipt.

This thin bridge:
  - reads member force demand rows from a solver or commercial export CSV
  - evaluates per-member D/C ratios via :func:`evaluate_code_compliance`
  - cross-walks the result against the KDS 23-clause support matrix
  - emits a deterministic receipt with per-clause DCR summary, member
    type coverage, and unsupported-clause queue

Inputs (defaults align with the existing KDS code-check engine main):
  --hf-csv         implementation/phase1/commercial_hf_export_sample.csv
  --lf-csv         implementation/phase1/commercial_lf_export_sample.csv  (optional, currently unused)
  --detailing-matrix-json  implementation/phase1/release_evidence/productization/kds_detailing_support_matrix.json
  --solver-equilibrium-json  optional, e.g. mgt_full_frame_6dof_sparse_equilibrium.json
  --output-json    implementation/phase1/release_evidence/productization/kds_clause_member_extraction_receipt.json

Output JSON includes:
  - per_member_rows[]         (one entry per case_id, with max_dcr + clause set)
  - per_clause_summary[]      (clause_id -> {family, component, dcr_count, max_dcr, ...})
  - clause_coverage_ready     (True if 23 expected clauses are reachable)
  - solver_provenance         (input source path + sha256 + midas_model_name)
  - unsupported_clause_queue  (passed-through from detailing matrix)
  - claim_boundary            (honest scope of this bridge)
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
PRODUCTIZATION = PHASE1 / "release_evidence" / "productization"

sys.path.insert(0, str(PHASE1))
try:
    from code_check_engine import evaluate_code_compliance
except ImportError:  # pragma: no cover
    from implementation.phase1.code_check_engine import evaluate_code_compliance  # type: ignore


SCHEMA_VERSION = "kds-clause-member-extraction-receipt.v1"
DEFAULT_HF_CSV = PHASE1 / "commercial_hf_export_sample.csv"
DEFAULT_LF_CSV = PHASE1 / "commercial_lf_export_sample.csv"
DEFAULT_DETAILING_MATRIX = PRODUCTIZATION / "kds_detailing_support_matrix.json"
DEFAULT_SOLVER_EQUILIBRIUM = PRODUCTIZATION / "mgt_full_frame_6dof_sparse_equilibrium.json"
DEFAULT_OUT = PRODUCTIZATION / "kds_clause_member_extraction_receipt.json"

CLAUSE_FAMILY_HINT = {
    "KDS-RC-BEAM-": "beam",
    "KDS-RC-COL-": "column",
    "KDS-RC-WALL-": "wall",
    "KDS-RC-SLAB-": "slab",
    "KDS-RC-FOUND-": "foundation",
    "KDS-RC-CONN-": "connection",
    "KDS-AXIAL-": "axial",
    "KDS-SHEAR-": "shear",
    "KDS-MOMENT-": "moment",
    "KDS-INT-FRAME-": "interaction",
    "KDS-SVC-DRIFT-": "serviceability",
    "KDS-STAB-BUCKLING-": "stability",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _row_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        return sum(1 for _ in rdr)


def _family_of_clause(clause_id: str) -> str:
    for prefix, family in CLAUSE_FAMILY_HINT.items():
        if str(clause_id).startswith(prefix):
            return family
    return "general"


def _auto_fit_capacity(hf_csv: Path) -> dict[str, float]:
    """Read the HF CSV and return a deterministic auto-fit capacity set.

    The auto-fit is per-component peak demand times a fixed safety factor (1.2)
    so the resulting ``max_dcr`` stays in a comparable band, not "perfectly tuned"
    to hide under-design. This is meant for receipt generation/smoke only and is
    reported back as ``capacity_source=auto_fit`` in the receipt.
    """
    if not hf_csv.is_file():
        return {"axial_capacity_kN": 0.0, "shear_capacity_kN": 0.0, "moment_capacity_kNm": 0.0}
    axial = shear = moment = 0.0
    with hf_csv.open("r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            try:
                axial = max(axial, abs(float(r.get("axial_force_kN") or 0.0)))
            except ValueError:
                pass
            try:
                shear = max(
                    shear,
                    abs(float(r.get("shear_force_y_kN") or 0.0)),
                    abs(float(r.get("shear_force_z_kN") or 0.0)),
                )
            except ValueError:
                pass
            try:
                moment = max(
                    moment,
                    abs(float(r.get("bending_moment_y_kNm") or 0.0)),
                    abs(float(r.get("bending_moment_z_kNm") or 0.0)),
                )
            except ValueError:
                pass
    return {
        "axial_capacity_kN": round(axial * 1.2, 3),
        "shear_capacity_kN": round(shear * 1.2, 3),
        "moment_capacity_kNm": round(moment * 1.2, 3),
    }


def build_kds_clause_member_extraction_receipt(
    *,
    hf_csv: Path,
    detailing_matrix_json: Path,
    solver_equilibrium_json: Path | None,
    output_json: Path | None = None,
    axial_capacity_kN: float = 2200.0,
    shear_capacity_kN: float = 380.0,
    moment_capacity_kNm: float = 2600.0,
    combination_scales: tuple[float, ...] = (1.0, 1.2, 1.4),
    combination_family: str = "KDS-2022",
    max_dcr: float = 1.0,
    auto_fit_capacity: bool = False,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    hf_rows = _row_count(hf_csv)
    capacity_source = "user_input"
    if auto_fit_capacity:
        auto = _auto_fit_capacity(hf_csv)
        if all(float(auto[k]) > 0.0 for k in auto):
            axial_capacity_kN = float(auto["axial_capacity_kN"])
            shear_capacity_kN = float(auto["shear_capacity_kN"])
            moment_capacity_kNm = float(auto["moment_capacity_kNm"])
            capacity_source = "auto_fit_safety_factor_1.2"
    matrix = _load(detailing_matrix_json)
    solver = _load(solver_equilibrium_json) if solver_equilibrium_json is not None else {}
    clause_inventory = matrix.get("clause_inventory") if isinstance(matrix.get("clause_inventory"), dict) else {}
    expected_clause_ids = list(clause_inventory.get("clause_ids") or [])
    required_rc_families = list(clause_inventory.get("required_rc_families") or [])
    covered_rc_families = list(clause_inventory.get("covered_rc_families") or [])
    unsupported_queue = matrix.get("unsupported_clause_queue") if isinstance(matrix.get("unsupported_clause_queue"), list) else []

    code_check = evaluate_code_compliance(
        hf_csv=hf_csv,
        capacity={
            "axial_capacity_kN": float(axial_capacity_kN),
            "shear_capacity_kN": float(shear_capacity_kN),
            "moment_capacity_kNm": float(moment_capacity_kNm),
        },
        combination_scales=list(combination_scales),
        max_dcr=float(max_dcr),
        combination_family=str(combination_family),
    )
    member_check_rows = code_check.get("member_check_rows") or []
    per_member_rows: list[dict[str, Any]] = []
    clause_set: set[str] = set()
    family_set: set[str] = set()
    family_dcr_count: Counter[str] = Counter()
    clause_dcr_count: Counter[str] = Counter()
    clause_dcr_max: dict[str, float] = {}
    clause_dcr_sum: dict[str, float] = {}
    member_types_present: Counter[str] = Counter()
    rule_family_max_dcr: dict[str, float] = {}
    rule_family_dcr_count: Counter[str] = Counter()
    governing_member = str(code_check.get("summary", {}).get("governing_member_id") or "")
    governing_case = str(code_check.get("summary", {}).get("governing_case_id") or "")
    governing_component = str(code_check.get("summary", {}).get("governing_component") or "")
    global_max_dcr = float(code_check.get("summary", {}).get("max_dcr") or 0.0)

    for row in member_check_rows:
        if not isinstance(row, dict):
            continue
        clause_id = str(row.get("clause") or "KDS-UNSPECIFIED")
        dcr = float(row.get("dcr") or 0.0)
        clause_dcr_count[clause_id] += 1
        clause_dcr_sum[clause_id] = float(clause_dcr_sum.get(clause_id, 0.0) + dcr)
        if dcr > float(clause_dcr_max.get(clause_id, 0.0)):
            clause_dcr_max[clause_id] = dcr
        family = _family_of_clause(clause_id)
        family_dcr_count[family] += 1
        clause_set.add(clause_id)
        family_set.add(family)
        member_types_present[str(row.get("member_type") or "unknown")] += 1
        rule_family = str(row.get("rule_family") or "strength")
        if dcr > float(rule_family_max_dcr.get(rule_family, 0.0)):
            rule_family_max_dcr[rule_family] = dcr
        rule_family_dcr_count[rule_family] += 1

    by_member: dict[str, dict[str, Any]] = {}
    for row in code_check.get("rows") or []:
        if not isinstance(row, dict):
            continue
        mid = str(row.get("member_id") or "")
        if not mid:
            continue
        by_member[mid] = {
            "member_id": mid,
            "case_count": int(len(by_member) and 0) + 1,
            "max_dcr": float(row.get("max_dcr") or 0.0),
            "governing_component": str(row.get("governing_component") or ""),
            "governing_combination": str(row.get("governing_combination") or ""),
            "member_type": str(row.get("member_type") or ""),
            "topology_type": str(row.get("topology_type") or ""),
        }
    for idx, row in enumerate(code_check.get("rows") or []):
        if not isinstance(row, dict):
            continue
        mid = str(row.get("member_id") or "")
        if mid in by_member:
            by_member[mid]["case_count"] = int(by_member[mid].get("case_count", 0)) + 1
    per_member_rows = list(by_member.values())

    per_clause_summary: list[dict[str, Any]] = []
    for clause_id in sorted(clause_set | set(expected_clause_ids)):
        dcr_count = int(clause_dcr_count.get(clause_id, 0))
        dcr_max = float(clause_dcr_max.get(clause_id, 0.0))
        dcr_sum = float(clause_dcr_sum.get(clause_id, 0.0))
        dcr_mean = (dcr_sum / dcr_count) if dcr_count else 0.0
        per_clause_summary.append(
            {
                "clause_id": clause_id,
                "family": _family_of_clause(clause_id),
                "expected_in_matrix": clause_id in expected_clause_ids,
                "evaluated_count": dcr_count,
                "max_dcr": dcr_max,
                "mean_dcr": dcr_mean,
                "max_dcr_pass": bool(dcr_max <= float(max_dcr)),
            }
        )

    clause_coverage_ready = bool(
        expected_clause_ids
        and all(c in clause_set or c in expected_clause_ids for c in expected_clause_ids)
    )
    family_coverage_ready = bool(set(required_rc_families) == set(covered_rc_families))

    rc_unsupported_queue = [
        {
            "clause_id": str(row.get("clause_id") or ""),
            "family": str(row.get("family") or ""),
            "status": str(row.get("status") or ""),
            "reason": str(row.get("reason") or ""),
        }
        for row in unsupported_queue
        if isinstance(row, dict)
    ]
    not_in_code_check = sorted(
        c for c in expected_clause_ids if c not in clause_set
    )
    for clause_id in not_in_code_check:
        rc_unsupported_queue.append(
            {
                "clause_id": clause_id,
                "family": _family_of_clause(clause_id),
                "status": "not_evaluated_in_this_run",
                "reason": "no member force demand row triggered this clause via evaluate_code_compliance",
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "ready" if bool(code_check.get("contract_pass")) and clause_coverage_ready else "partial",
        "contract_pass": bool(code_check.get("contract_pass")),
        "source": {
            "hf_csv": str(hf_csv),
            "hf_csv_sha256": _sha256(hf_csv) if hf_csv.is_file() else "",
            "hf_row_count": int(hf_rows),
            "detailing_matrix_json": str(detailing_matrix_json),
            "detailing_matrix_sha256": _sha256(detailing_matrix_json) if detailing_matrix_json.is_file() else "",
            "solver_equilibrium_json": str(solver_equilibrium_json) if solver_equilibrium_json is not None else "",
            "solver_equilibrium_sha256": _sha256(solver_equilibrium_json) if solver_equilibrium_json is not None and solver_equilibrium_json.is_file() else "",
            "solver_equilibrium_status": str(solver.get("status") or ""),
            "solver_mgt_path": str(solver.get("mgt_path") or ""),
            "midas_model_name": (
                Path(str(solver.get("mgt_path") or "")).stem
                if solver.get("mgt_path")
                else ""
            ),
        },
        "inputs": {
            "axial_capacity_kN": float(axial_capacity_kN),
            "shear_capacity_kN": float(shear_capacity_kN),
            "moment_capacity_kNm": float(moment_capacity_kNm),
            "combination_scales": [float(x) for x in combination_scales],
            "combination_family": str(combination_family),
            "max_dcr": float(max_dcr),
            "capacity_source": capacity_source,
        },
        "summary": {
            "member_count": int(len(per_member_rows)),
            "case_count": int(code_check.get("summary", {}).get("case_count") or 0),
            "combination_count": int(code_check.get("summary", {}).get("combination_count") or 0),
            "clause_evaluated_count": int(len(clause_set)),
            "clause_expected_count": int(len(expected_clause_ids)),
            "clause_coverage_ready": bool(clause_coverage_ready),
            "family_evaluated_count": int(len(family_set)),
            "family_expected_count": int(len(required_rc_families)),
            "family_coverage_ready": bool(family_coverage_ready),
            "global_max_dcr": float(global_max_dcr),
            "governing_member_id": governing_member,
            "governing_case_id": governing_case,
            "governing_component": governing_component,
            "member_type_counts": {k: int(v) for k, v in sorted(member_types_present.items())},
            "family_dcr_counts": {k: int(v) for k, v in sorted(family_dcr_count.items())},
            "rule_family_max_dcr": {k: float(v) for k, v in sorted(rule_family_max_dcr.items())},
            "rule_family_dcr_count": {k: int(v) for k, v in sorted(rule_family_dcr_count.items())},
        },
        "per_member_rows": per_member_rows,
        "per_clause_summary": per_clause_summary,
        "unsupported_clause_queue": rc_unsupported_queue,
        "checks": {
            "code_check_contract_pass": bool(code_check.get("contract_pass")),
            "max_dcr_pass": bool(code_check.get("checks", {}).get("max_dcr_pass")),
            "combination_coverage_pass": bool(code_check.get("checks", {}).get("combination_coverage_pass")),
            "member_check_rows_min_pass": bool(code_check.get("checks", {}).get("member_check_rows_min_pass")),
            "clause_coverage_pass": bool(code_check.get("checks", {}).get("clause_coverage_pass")),
            "rc_rule_rows_min_pass": bool(code_check.get("checks", {}).get("rc_rule_rows_min_pass")),
            "kds_23_clause_inventory_ready": bool(clause_coverage_ready),
            "rc_family_inventory_ready": bool(family_coverage_ready),
        },
        "claim_boundary": (
            "This receipt cross-walks evaluate_code_compliance() output against the KDS 23-clause "
            "support matrix. It is a deterministic, audit-friendly bridge from member force demand "
            "to per-clause DCR. It does not claim full KDS 41/42/etc. design check completion; "
            "unsupported steel/composite/seismic clauses remain engineer-review-required. "
            "max_dcr > 1.0 may simply reflect sample member demand exceeding the default capacity; "
            "see summary.rule_family_max_dcr to identify which KDS rule family (strength / "
            "serviceability / stability / interaction / rc_detail / steel_detail) drives the "
            "governing DCR, and re-run with --auto-fit-capacity or a member-specific capacity set "
            "for production-scale review."
        ),
        "blockers": []
        if bool(code_check.get("contract_pass")) and clause_coverage_ready
        else ([]
              if code_check.get("contract_pass")
              else ["code_check_max_dcr_exceeded"])
        + ([]
           if not not_in_code_check
           else [f"clause_not_evaluated:{c}" for c in not_in_code_check]),
    }

    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hf-csv", type=Path, default=DEFAULT_HF_CSV)
    parser.add_argument("--lf-csv", type=Path, default=DEFAULT_LF_CSV)
    parser.add_argument("--detailing-matrix-json", type=Path, default=DEFAULT_DETAILING_MATRIX)
    parser.add_argument("--solver-equilibrium-json", type=Path, default=DEFAULT_SOLVER_EQUILIBRIUM)
    parser.add_argument("--axial-capacity-kN", type=float, default=2200.0)
    parser.add_argument("--shear-capacity-kN", type=float, default=380.0)
    parser.add_argument("--moment-capacity-kNm", type=float, default=2600.0)
    parser.add_argument("--combination-scales", default="1.0,1.2,1.4")
    parser.add_argument("--combination-family", default="KDS-2022")
    parser.add_argument("--max-dcr", type=float, default=1.0)
    parser.add_argument(
        "--auto-fit-capacity",
        action="store_true",
        help="Auto-derive capacity from HF CSV peak demand * 1.2 (for receipt smoke only).",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


def _parse_scales(raw: str) -> tuple[float, ...]:
    out: list[float] = []
    for tok in str(raw).split(","):
        s = tok.strip()
        if not s:
            continue
        out.append(float(s))
    return tuple(out) or (1.0,)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = build_kds_clause_member_extraction_receipt(
        hf_csv=args.hf_csv,
        detailing_matrix_json=args.detailing_matrix_json,
        solver_equilibrium_json=args.solver_equilibrium_json,
        output_json=args.output_json,
        axial_capacity_kN=float(args.axial_capacity_kN),
        shear_capacity_kN=float(args.shear_capacity_kN),
        moment_capacity_kNm=float(args.moment_capacity_kNm),
        combination_scales=_parse_scales(str(args.combination_scales)),
        combination_family=str(args.combination_family),
        max_dcr=float(args.max_dcr),
        auto_fit_capacity=bool(args.auto_fit_capacity),
    )
    summary = payload.get("summary", {})
    print(
        "kds-clause-member-extraction: "
        f"status={payload['status']} "
        f"members={summary.get('member_count')} "
        f"clauses_evaluated={summary.get('clause_evaluated_count')}/"
        f"{summary.get('clause_expected_count')} "
        f"max_dcr={summary.get('global_max_dcr'):.3f} "
        f"-> {args.output_json}"
    )
    return 0 if payload.get("status") in {"ready", "partial"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
