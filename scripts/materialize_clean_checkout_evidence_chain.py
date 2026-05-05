#!/usr/bin/env python3
"""Materialize the clean-checkout evidence chain for release/P1 readiness."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "clean_checkout_evidence_chain.v1"
PUBLICATION_EVIDENCE_INDEX_SCHEMA = "release-publication-evidence-index.v1"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _publication_index_paths(path: Path | None) -> dict[str, Path]:
    if path is None:
        return {}
    payload = _load_json(path)
    if payload.get("schema_version") != PUBLICATION_EVIDENCE_INDEX_SCHEMA:
        raise ValueError(f"publication evidence index has unsupported schema: {path}")
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"publication evidence index paths must be an object: {path}")
    p0_status = paths.get("p0_status_json")
    if not p0_status:
        return {}
    candidate = Path(str(p0_status))
    if candidate.exists():
        return {"p0_status": candidate}
    sibling = path.parent / candidate.name
    return {"p0_status": sibling if sibling.exists() else candidate}


def _compact_summary(summary: object) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    compact: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            compact[str(key)] = value
    return compact


def _json_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "ok": False, "path": str(path)}
    try:
        payload = _load_json(path)
    except Exception as exc:
        return {"exists": True, "ok": False, "path": str(path), "reason": f"invalid_json: {exc}"}
    return {
        "exists": True,
        "ok": bool(payload.get("contract_pass", payload.get("pass", payload.get("ok", False)))),
        "path": str(path),
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary": _compact_summary(payload.get("summary")),
    }


def _materialize_evidence(
    *,
    label: str,
    source: Path,
    destination: Path,
    force: bool,
) -> dict[str, Any]:
    if destination.exists() and not force:
        summary = _json_summary(destination)
        summary.update(
            {
                "label": label,
                "source_evidence": str(source),
                "hydrated_from_source": False,
            }
        )
        return summary

    if not source.exists():
        return {
            "label": label,
            "exists": destination.exists(),
            "ok": False,
            "path": str(destination),
            "source_evidence": str(source),
            "hydrated_from_source": False,
            "reason": "source_evidence_missing",
        }

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    summary = _json_summary(destination)
    summary.update(
        {
            "label": label,
            "source_evidence": str(source),
            "hydrated_from_source": True,
        }
    )
    return summary


def _run_command(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _run_json_command(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    result = {
        "command": command,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }
    payload: dict[str, Any] = {}
    if proc.stdout:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {}
    result["json"] = payload
    return result


def _commercial_scope(path: Path) -> dict[str, Any]:
    payload = _load_json(path) if path.exists() else {}
    grade = payload.get("grade") if isinstance(payload.get("grade"), dict) else {}
    deployment = payload.get("deployment_model") if isinstance(payload.get("deployment_model"), dict) else {}
    return {
        "grade": str(grade.get("label", "unknown") or "unknown"),
        "commercial_pass": bool(grade.get("commercial_pass", payload.get("contract_pass", False))),
        "engineer_in_loop_accelerated_coverage_ready": bool(
            deployment.get("engineer_in_loop_accelerated_coverage_ready", False)
        ),
        "full_commercial_replacement_ready": bool(deployment.get("full_commercial_replacement_ready", False)),
        "accelerated_coverage_target_pct_range": deployment.get("accelerated_coverage_target_pct_range", []),
        "residual_holdout_target_pct_range": deployment.get("residual_holdout_target_pct_range", []),
    }


def build_chain(args: argparse.Namespace) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    index_paths = _publication_index_paths(args.publication_evidence_index)
    p0_status_path = args.p0_status or index_paths.get("p0_status")

    midas_step = _materialize_evidence(
        label="MIDAS/KDS validation report",
        source=args.midas_kds_source_evidence,
        destination=args.midas_kds_validation_report,
        force=args.force_hydrate,
    )
    steps.append(midas_step)

    commercial_step = _materialize_evidence(
        label="commercial readiness report",
        source=args.commercial_readiness_source_evidence,
        destination=args.commercial_readiness,
        force=args.force_hydrate,
    )
    steps.append(commercial_step)

    coverage_cmd = [
        sys.executable,
        "implementation/phase1/generate_real_project_parser_coverage_matrix.py",
        "--manifest",
        str(args.manifest),
        "--out",
        str(args.coverage_matrix),
    ]
    coverage_step = _run_command(coverage_cmd)
    coverage_step.update({"label": "real-project parser coverage matrix", "path": str(args.coverage_matrix)})
    steps.append(coverage_step)

    peer_cmd = [
        sys.executable,
        "implementation/phase1/build_peer_tbi_benchmark_metric_records.py",
        "--manifest",
        str(args.manifest),
        "--coverage-matrix",
        str(args.coverage_matrix),
        "--out",
        str(args.peer_metric_records),
    ]
    peer_step = _run_command(peer_cmd)
    peer_step.update({"label": "PEER TBI benchmark metric records", "path": str(args.peer_metric_records)})
    steps.append(peer_step)

    row_cmd = [
        sys.executable,
        "implementation/phase1/build_real_project_row_provenance_report.py",
        "--manifest",
        str(args.manifest),
        "--coverage-matrix",
        str(args.coverage_matrix),
        "--peer-metric-records",
        str(args.peer_metric_records),
        "--midas-kds-validation-report",
        str(args.midas_kds_validation_report),
        "--out",
        str(args.row_provenance),
    ]
    row_step = _run_command(row_cmd)
    row_step.update({"label": "real-project row provenance", "path": str(args.row_provenance)})
    steps.append(row_step)

    p1_cmd = [
        sys.executable,
        "scripts/check_p1_readiness_status.py",
        "--coverage-matrix",
        str(args.coverage_matrix),
        "--peer-metric-records",
        str(args.peer_metric_records),
        "--row-provenance",
        str(args.row_provenance),
        "--json",
    ]
    if p0_status_path is not None:
        p1_cmd.extend(["--p0-status", str(p0_status_path)])
    p1_step = _run_json_command(p1_cmd)
    p1_step.update({"label": "P1 readiness status"})
    steps.append(p1_step)

    p1_readiness_path = args.p1_readiness_out
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if p1_readiness_path is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="clean-checkout-evidence-chain-")
        p1_readiness_path = Path(temp_dir.name) / "p1-readiness-status.json"

    benchmark_cmd = [
        sys.executable,
        "scripts/check_p1_benchmark_breadth_status.py",
        "--commercial-readiness",
        str(args.commercial_readiness),
        "--json",
    ]
    p1_status = p1_step.get("json") if isinstance(p1_step.get("json"), dict) else {}
    _write_json(p1_readiness_path, p1_status)
    benchmark_cmd.extend(["--p1-readiness-status", str(p1_readiness_path)])
    benchmark_step = _run_json_command(benchmark_cmd)
    benchmark_step.update({"label": "P1 benchmark breadth status"})
    steps.append(benchmark_step)

    if temp_dir is not None:
        temp_dir.cleanup()

    if args.p1_benchmark_out and isinstance(benchmark_step.get("json"), dict):
        _write_json(args.p1_benchmark_out, benchmark_step["json"])

    midas_payload = _json_summary(args.midas_kds_validation_report)
    commercial_payload = _json_summary(args.commercial_readiness)
    row_payload = _json_summary(args.row_provenance)
    p1_readiness = p1_step.get("json") if isinstance(p1_step.get("json"), dict) else {}
    p1_benchmark = benchmark_step.get("json") if isinstance(benchmark_step.get("json"), dict) else {}
    contract_pass = bool(
        midas_payload.get("ok")
        and commercial_payload.get("ok")
        and row_payload.get("ok")
        and p1_readiness.get("p1_inputs_ready", False)
        and p1_benchmark.get("benchmark_breadth_inputs_ready", False)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_CLEAN_CHECKOUT_EVIDENCE_CHAIN_INCOMPLETE",
        "artifacts": {
            "manifest": str(args.manifest),
            "publication_evidence_index": (
                str(args.publication_evidence_index) if args.publication_evidence_index else ""
            ),
            "p0_status": str(p0_status_path) if p0_status_path else "",
            "coverage_matrix": str(args.coverage_matrix),
            "peer_metric_records": str(args.peer_metric_records),
            "midas_kds_validation_report": str(args.midas_kds_validation_report),
            "commercial_readiness": str(args.commercial_readiness),
            "row_provenance": str(args.row_provenance),
        },
        "midas_kds_validation": midas_payload,
        "commercial_readiness": {
            **commercial_payload,
            "commercial_scope": _commercial_scope(args.commercial_readiness),
        },
        "row_provenance": row_payload,
        "p1_readiness_status": p1_readiness,
        "p1_benchmark_breadth_status": p1_benchmark,
        "p0_release_blocker": bool(p1_readiness.get("p0_release_blocker", False)),
        "p1_execution_unblocked": bool(p1_readiness.get("p1_execution_unblocked", False)),
        "p1_benchmark_execution_unblocked": bool(
            p1_benchmark.get("p1_benchmark_execution_unblocked", False)
        ),
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("implementation/phase1/real_project_corpus_seed_manifest.json"))
    parser.add_argument("--coverage-matrix", type=Path, default=Path("implementation/phase1/real_project_parser_coverage_matrix.json"))
    parser.add_argument("--peer-metric-records", type=Path, default=Path("implementation/phase1/peer_tbi_benchmark_metric_records.json"))
    parser.add_argument("--row-provenance", type=Path, default=Path("implementation/phase1/real_project_row_provenance_report.json"))
    parser.add_argument(
        "--midas-kds-validation-report",
        type=Path,
        default=Path("implementation/phase1/midas_kds_geometry_bridge_validation_report.json"),
    )
    parser.add_argument(
        "--midas-kds-source-evidence",
        type=Path,
        default=Path("implementation/phase1/release_evidence/midas/midas_kds_geometry_bridge_validation_report.json"),
    )
    parser.add_argument("--commercial-readiness", type=Path, default=Path("implementation/phase1/commercial_readiness_report.json"))
    parser.add_argument(
        "--commercial-readiness-source-evidence",
        type=Path,
        default=Path("implementation/phase1/release_evidence/commercial/commercial_readiness_report.json"),
    )
    parser.add_argument(
        "--p0-status",
        type=Path,
        default=None,
        help="Published P0 closure status JSON. When provided, P1 readiness is evaluated against the closed release gate.",
    )
    parser.add_argument(
        "--publication-evidence-index",
        type=Path,
        default=None,
        help="Release publication evidence index. Supplies --p0-status for P1 handoff when --p0-status is omitted.",
    )
    parser.add_argument("--p1-readiness-out", type=Path, default=None)
    parser.add_argument("--p1-benchmark-out", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--force-hydrate", action="store_true")
    args = parser.parse_args()

    payload = build_chain(args)
    if args.out:
        _write_json(args.out, payload)
    if args.json or not args.out:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
