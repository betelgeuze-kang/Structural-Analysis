#!/usr/bin/env python3
"""Multi-dataset real-source gate (toy-free + metric-source + public HF count)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "multi real-source gate passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_CASES_MISSING": "one or more case files are missing/invalid",
    "ERR_REAL_SOURCE_FAIL": "one or more case files failed real-source checks",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cases", "accepted_metric_sources", "min_public_hf_cases", "forbid_toy_markers", "out"],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
        "min_public_hf_cases": {"type": "integer", "minimum": 1},
        "forbid_toy_markers": {"type": "boolean"},
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


def _parse_csv(text: str) -> list[str]:
    return [x.strip() for x in str(text).split(",") if x.strip()]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _metric_source_gate(cases_payload: dict, accepted: set[str]) -> tuple[bool, list[str], int]:
    rows = cases_payload.get("cases")
    if not isinstance(rows, list) or not rows:
        return False, ["cases[] missing"], 0
    bad: list[str] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            bad.append(f"case[{i}] not object")
            continue
        src = str(row.get("metric_source", "")).strip()
        if not src:
            bad.append(f"{row.get('case_id', f'case-{i}')}: metric_source missing")
        elif src not in accepted:
            bad.append(f"{row.get('case_id', f'case-{i}')}: metric_source={src}")
    return len(bad) == 0, bad, len(rows)


def _contains_toy_marker(path: Path, payload: dict) -> tuple[bool, list[str]]:
    markers = ("atwood", "toy", "synthetic", "sanity", "sample", "demo", "mock")
    hits: list[str] = []

    def _scan_text(label: str, text: object) -> None:
        s = str(text).strip().lower()
        if not s:
            return
        for tok in markers:
            if tok in s:
                hits.append(f"{label}:{tok}")
                break

    _scan_text("path", str(path))
    if isinstance(payload, dict):
        _scan_text("run_id", payload.get("run_id", ""))
        src = payload.get("source")
        if isinstance(src, dict):
            for k in ("dataset", "source_name", "id", "url", "name"):
                _scan_text(f"source.{k}", src.get(k, ""))
        rows = payload.get("cases")
        if isinstance(rows, list):
            for i, row in enumerate(rows[:10]):
                if not isinstance(row, dict):
                    continue
                _scan_text(f"cases[{i}].case_id", row.get("case_id", ""))
                _scan_text(f"cases[{i}].source_name", row.get("source_name", ""))
    return (len(hits) > 0), hits[:20]


def _public_hf_count(payload: dict) -> int:
    rows = payload.get("public_benchmark_cases")
    if isinstance(rows, list):
        return len(rows)
    return 0


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="real_source_multi_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json"
        ),
    )
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    p.add_argument("--min-public-hf-cases", type=int, default=3)
    p.add_argument("--forbid-toy-markers", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--out", default="implementation/phase1/real_source_multi_gate_report.json")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "accepted_metric_sources": str(args.accepted_metric_sources),
        "min_public_hf_cases": int(args.min_public_hf_cases),
        "forbid_toy_markers": bool(args.forbid_toy_markers),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_real_source_multi_gate")
        case_paths = [Path(x) for x in _parse_csv(args.cases)]
        if not case_paths:
            raise ValueError("no case files")

        accepted = {x.strip() for x in str(args.accepted_metric_sources).split(",") if x.strip()}
        rows: list[dict] = []
        all_exist = True
        all_real = True
        all_toy_free = True

        for cp in case_paths:
            payload = _load_json(cp)
            metric_ok, metric_errors, case_count = _metric_source_gate(payload, accepted)
            public_hf_case_count = _public_hf_count(payload)
            toy_detected, toy_hits = _contains_toy_marker(cp, payload)
            exists = cp.exists()
            source_ok = bool(
                exists
                and metric_ok
                and int(public_hf_case_count) >= int(args.min_public_hf_cases)
            )
            toy_free_ok = bool((not bool(args.forbid_toy_markers)) or (not toy_detected))
            row_pass = bool(source_ok and toy_free_ok)

            rows.append(
                {
                    "cases_path": str(cp),
                    "cases_sha256": _sha256(cp) if exists else "",
                    "exists": bool(exists),
                    "case_count": int(case_count),
                    "public_hf_case_count": int(public_hf_case_count),
                    "metric_source_pass": bool(metric_ok),
                    "metric_source_errors": metric_errors[:20],
                    "toy_marker_detected": bool(toy_detected),
                    "toy_marker_hits": toy_hits[:20],
                    "source_pass": bool(source_ok),
                    "toy_free_pass": bool(toy_free_ok),
                    "row_pass": bool(row_pass),
                }
            )
            all_exist = bool(all_exist and exists)
            all_real = bool(all_real and source_ok)
            all_toy_free = bool(all_toy_free and toy_free_ok)

        checks = {
            "cases_present_pass": bool(all_exist),
            "all_real_source_pass": bool(all_real),
            "all_toy_free_pass": bool(all_toy_free),
        }
        contract_pass = bool(all(checks.values()))
        if not checks["cases_present_pass"]:
            reason_code = "ERR_CASES_MISSING"
        elif not contract_pass:
            reason_code = "ERR_REAL_SOURCE_FAIL"
        else:
            reason_code = "PASS"

        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-real-source-multi-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "rows": rows,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        archive_manifest = _archive([str(out), *[str(x) for x in case_paths]])
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote real-source multi gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase3-real-source-multi-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote real-source multi gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

