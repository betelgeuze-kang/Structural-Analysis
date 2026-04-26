#!/usr/bin/env python3
"""Classify bounded contact-readiness evidence and remaining structural contact gaps."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "bounded wheel-rail contact evidence is present; broader structural contact remains a tracked gap",
    "ERR_INVALID_INPUT": "invalid contact-readiness gate input",
    "ERR_CONTACT_SCHEMA_MISSING": "contact schema evidence is missing",
    "ERR_CONTACT_SOLVER_EVIDENCE_FAIL": "contact solver evidence is missing or does not satisfy the contract",
    "ERR_CONTACT_WHITEBOX_EVIDENCE_FAIL": "contact-force validation evidence is missing or does not satisfy the contract",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "vehicle_model_schema",
        "vti_report",
        "whitebox_report",
        "roadmap",
        "min_converged_ratio",
        "min_contact_force_n",
        "max_whitebox_contact_rel_err",
        "out",
    ],
    "properties": {
        "vehicle_model_schema": {"type": "string", "minLength": 1},
        "vti_report": {"type": "string", "minLength": 1},
        "whitebox_report": {"type": "string", "minLength": 1},
        "roadmap": {"type": "string", "minLength": 1},
        "min_converged_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "min_contact_force_n": {"type": "number", "minimum": 0.0},
        "max_whitebox_contact_rel_err": {"type": "number", "minimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _schema_contact_evidence(schema_payload: dict) -> dict:
    props = schema_payload.get("properties") if isinstance(schema_payload.get("properties"), dict) else {}
    contact_model = props.get("contact_model") if isinstance(props.get("contact_model"), dict) else {}
    hertz_contact = props.get("hertz_contact") if isinstance(props.get("hertz_contact"), dict) else {}
    enum_values = contact_model.get("enum") if isinstance(contact_model.get("enum"), list) else []
    contact_model_present = bool(contact_model)
    hertz_contact_present = bool(hertz_contact)
    hertzian_enum_present = any(str(item).strip() == "hertzian" for item in enum_values)
    schema_pass = bool(contact_model_present and hertz_contact_present and hertzian_enum_present)
    return {
        "contact_model_present": bool(contact_model_present),
        "hertz_contact_present": bool(hertz_contact_present),
        "hertzian_enum_present": bool(hertzian_enum_present),
        "schema_pass": schema_pass,
    }


def _solver_contact_evidence(report_payload: dict, *, min_converged_ratio: float, min_contact_force_n: float) -> dict:
    checks = report_payload.get("checks") if isinstance(report_payload.get("checks"), dict) else {}
    metrics = report_payload.get("metrics") if isinstance(report_payload.get("metrics"), dict) else {}
    inputs = report_payload.get("inputs") if isinstance(report_payload.get("inputs"), dict) else {}
    config = inputs.get("config") if isinstance(inputs.get("config"), dict) else {}

    converged_ratio = float(metrics.get("converged_ratio", 0.0) or 0.0)
    max_contact_force_n = float(metrics.get("max_contact_force_n", 0.0) or 0.0)
    hertz_stiffness = float(config.get("hertz_k_n_m_3_2", 0.0) or 0.0)

    finite_response = bool(checks.get("finite_response", False))
    coupling_pass = bool(checks.get("coupling_converged_ratio_pass", False)) and converged_ratio >= float(min_converged_ratio)
    adaptive_newton_pass = bool(checks.get("adaptive_newton_converged_pass", False))
    contact_force_pass = max_contact_force_n >= float(min_contact_force_n)
    hertz_stiffness_pass = hertz_stiffness > 0.0

    solver_pass = bool(
        finite_response
        and coupling_pass
        and adaptive_newton_pass
        and contact_force_pass
        and hertz_stiffness_pass
    )
    return {
        "finite_response": finite_response,
        "coupling_pass": coupling_pass,
        "adaptive_newton_pass": adaptive_newton_pass,
        "contact_force_pass": contact_force_pass,
        "hertz_stiffness_pass": hertz_stiffness_pass,
        "converged_ratio": converged_ratio,
        "max_contact_force_n": max_contact_force_n,
        "hertz_k_n_m_3_2": hertz_stiffness,
        "solver_pass": solver_pass,
    }


def _parse_whitebox_contact_row(report_text: str) -> dict:
    for raw_line in report_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0] == "Domain":
            continue
        metric = str(cells[2]).strip()
        if metric != "contact_force_kN":
            continue
        try:
            gnn_rel_err = float(cells[4])
        except Exception:
            gnn_rel_err = float("inf")
        improved = str(cells[5]).strip().lower() == "true"
        return {
            "row_present": True,
            "domain": str(cells[0]).strip(),
            "case": str(cells[1]).strip(),
            "metric": metric,
            "lf_rel_err": float(cells[3]),
            "gnn_rel_err": gnn_rel_err,
            "improved": improved,
        }
    return {
        "row_present": False,
        "domain": "",
        "case": "",
        "metric": "",
        "lf_rel_err": None,
        "gnn_rel_err": None,
        "improved": False,
    }


def _whitebox_contact_evidence(report_text: str, *, max_whitebox_contact_rel_err: float) -> dict:
    row = _parse_whitebox_contact_row(report_text)
    gnn_rel_err = row.get("gnn_rel_err")
    rel_err_pass = isinstance(gnn_rel_err, float) and gnn_rel_err <= float(max_whitebox_contact_rel_err)
    whitebox_pass = bool(row.get("row_present", False) and row.get("improved", False) and rel_err_pass)
    row["rel_err_pass"] = bool(rel_err_pass)
    row["whitebox_pass"] = whitebox_pass
    return row


def _roadmap_contact_gap_state(roadmap_text: str) -> dict:
    text = roadmap_text.lower()
    tracked_gap_markers = {
        "broad_contact_gap": "contact / gap / uplift / compression-only".lower() in text,
        "special_link_gap": "gap, uplift, bearing, isolator, friction, pounding".lower() in text,
        "event_sequence_target": "contact / uplift event sequence mismatch".lower() in text,
    }
    tracked_gap = any(tracked_gap_markers.values())
    return {
        "tracked_gap": tracked_gap,
        "markers": tracked_gap_markers,
    }


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="contact_readiness_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vehicle-model-schema", default="implementation/phase1/vehicle_model_schema.json")
    parser.add_argument("--vti-report", default="implementation/phase1/vti_coupled_solver_report.json")
    parser.add_argument("--whitebox-report", default="implementation/phase1/whitebox_validation_report.md")
    parser.add_argument("--roadmap", default="implementation/phase1/commercial_tool_replacement_roadmap.md")
    parser.add_argument("--min-converged-ratio", type=float, default=0.95)
    parser.add_argument("--min-contact-force-n", type=float, default=1e-6)
    parser.add_argument("--max-whitebox-contact-rel-err", type=float, default=0.05)
    parser.add_argument("--out", default="implementation/phase1/contact_readiness_report.json")
    args = parser.parse_args()

    input_payload = {
        "vehicle_model_schema": str(args.vehicle_model_schema),
        "vti_report": str(args.vti_report),
        "whitebox_report": str(args.whitebox_report),
        "roadmap": str(args.roadmap),
        "min_converged_ratio": float(args.min_converged_ratio),
        "min_contact_force_n": float(args.min_contact_force_n),
        "max_whitebox_contact_rel_err": float(args.max_whitebox_contact_rel_err),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_contact_readiness_gate")

        schema_path = Path(args.vehicle_model_schema)
        vti_path = Path(args.vti_report)
        whitebox_path = Path(args.whitebox_report)
        roadmap_path = Path(args.roadmap)

        schema_evidence = _schema_contact_evidence(_load_json(schema_path))
        solver_evidence = _solver_contact_evidence(
            _load_json(vti_path),
            min_converged_ratio=float(args.min_converged_ratio),
            min_contact_force_n=float(args.min_contact_force_n),
        )
        whitebox_evidence = _whitebox_contact_evidence(
            _load_text(whitebox_path),
            max_whitebox_contact_rel_err=float(args.max_whitebox_contact_rel_err),
        )
        roadmap_gap = _roadmap_contact_gap_state(_load_text(roadmap_path))

        checks = {
            "contact_schema_pass": bool(schema_evidence["schema_pass"]),
            "contact_solver_evidence_pass": bool(solver_evidence["solver_pass"]),
            "contact_whitebox_evidence_pass": bool(whitebox_evidence["whitebox_pass"]),
            "structural_contact_gap_tracked": bool(roadmap_gap["tracked_gap"]),
        }
        contract_pass = bool(
            checks["contact_schema_pass"]
            and checks["contact_solver_evidence_pass"]
            and checks["contact_whitebox_evidence_pass"]
        )
        if not checks["contact_schema_pass"]:
            reason_code = "ERR_CONTACT_SCHEMA_MISSING"
        elif not checks["contact_solver_evidence_pass"]:
            reason_code = "ERR_CONTACT_SOLVER_EVIDENCE_FAIL"
        elif not checks["contact_whitebox_evidence_pass"]:
            reason_code = "ERR_CONTACT_WHITEBOX_EVIDENCE_FAIL"
        else:
            reason_code = "PASS"

        coverage_scope = "wheel_rail_hertzian_contact_only"
        coverage_grade = "bounded_contact_ready" if contract_pass else "tracked_gap"
        structural_gap_label = "tracked_gap" if checks["structural_contact_gap_tracked"] else "undocumented"
        summary_line = (
            f"Contact readiness: {('PASS' if contract_pass else 'GAP')} | "
            f"scope={coverage_scope} | "
            f"schema={('yes' if checks['contact_schema_pass'] else 'no')} | "
            f"solver={('yes' if checks['contact_solver_evidence_pass'] else 'no')}"
            f"(ratio={solver_evidence['converged_ratio']:.3f},max_force={solver_evidence['max_contact_force_n']:.6g}N) | "
            f"whitebox={('yes' if checks['contact_whitebox_evidence_pass'] else 'no')}"
            f"(err={whitebox_evidence['gnn_rel_err'] if whitebox_evidence['gnn_rel_err'] is not None else 'n/a'}) | "
            f"structural_contact={structural_gap_label}"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-contact-readiness-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "coverage_scope": coverage_scope,
            "coverage_grade": coverage_grade,
            "schema_evidence": {
                **schema_evidence,
                "path": str(schema_path),
                "sha256": _sha256(schema_path) if schema_path.exists() else "",
            },
            "solver_evidence": {
                **solver_evidence,
                "path": str(vti_path),
                "sha256": _sha256(vti_path) if vti_path.exists() else "",
            },
            "whitebox_evidence": {
                **whitebox_evidence,
                "path": str(whitebox_path),
                "sha256": _sha256(whitebox_path) if whitebox_path.exists() else "",
            },
            "roadmap_gap_state": {
                **roadmap_gap,
                "path": str(roadmap_path),
                "sha256": _sha256(roadmap_path) if roadmap_path.exists() else "",
            },
            "limitations": [
                "This gate only certifies bounded wheel-rail Hertzian contact evidence.",
                "Broader structural contact/gap/uplift/compression-only workflows remain a tracked roadmap gap.",
            ],
            "summary_line": summary_line,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive([str(out), str(schema_path), str(vti_path), str(whitebox_path), str(roadmap_path)])
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote contact readiness gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-contact-readiness-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote contact readiness gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
