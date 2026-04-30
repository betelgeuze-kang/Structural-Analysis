#!/usr/bin/env python3
"""Summarize P1 benchmark breadth readiness without bypassing the P0 gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_p1_readiness_status import build_status as build_p1_readiness_status  # noqa: E402


DEFAULT_COMMERCIAL_READINESS = Path("implementation/phase1/commercial_readiness_report.json")
DEFAULT_BENCHMARK_REPORTS = (
    Path("implementation/phase1/hf_benchmark_report.json"),
    Path("implementation/phase1/hf_benchmark_report.rwth_zenodo.json"),
    Path("implementation/phase1/hf_benchmark_report.from_csv.json"),
    Path("implementation/phase1/hf_benchmark_report.atwood_open.json"),
    Path("implementation/phase1/hf_benchmark_report.opstool_pr.json"),
    Path("implementation/phase1/hf_benchmark_report.opstool_nightly.json"),
    Path("implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json"),
    Path("implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json"),
    Path("implementation/phase1/open_data/irregular/irregular_top5_execution_manifest.json"),
    Path("implementation/phase1/open_data/korea/korean_public_structure_collection_report.json"),
)
REQUIRED_COMMERCIAL_CHECKS = (
    "real_source_pass",
    "benchmark_breadth_pass",
    "measured_dynamic_targets_pass",
    "measured_source_family_pass",
    "measured_case_count_pass",
    "accuracy_pass",
    "noise_robustness_pass",
    "ood_safety_pass",
    "gpu_strict_pass",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _status(ok: bool) -> str:
    return "ready" if ok else "blocked"


def _report_pass(payload: dict[str, Any]) -> bool:
    if isinstance(payload.get("contract_pass"), bool):
        return bool(payload["contract_pass"])
    if isinstance(payload.get("all_pass"), bool):
        return bool(payload["all_pass"])
    if isinstance(payload.get("pass"), bool):
        return bool(payload["pass"])
    return False


def _summary_line(payload: dict[str, Any], path: Path) -> str:
    direct = str(payload.get("summary_line", "") or "").strip()
    if direct:
        return direct
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    nested = str(summary.get("summary_line", "") or "").strip()
    return nested or path.name


def _commercial_gate(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    missing_checks = [name for name in REQUIRED_COMMERCIAL_CHECKS if not bool(checks.get(name, False))]
    exists = path.exists()
    ok = bool(exists and _report_pass(payload) and not missing_checks)
    return {
        "label": "Commercial readiness breadth",
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
        "missing_required_checks": missing_checks,
    }


def _benchmark_gate(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    exists = path.exists()
    ok = bool(exists and _report_pass(payload))
    return {
        "label": path.stem.replace("_", " "),
        "path": str(path),
        "status": _status(ok),
        "ok": ok,
        "exists": exists,
        "reason_code": str(payload.get("reason_code", "") or ""),
        "summary_line": _summary_line(payload, path),
    }


def _read_or_build_p1(path: Path | None) -> dict[str, Any]:
    if path is not None:
        return _load_json(path)
    return build_p1_readiness_status()


def _p1_gate(payload: dict[str, Any]) -> dict[str, Any]:
    p1_execution_unblocked = bool(payload.get("p1_execution_unblocked", False))
    return {
        "label": "P1 execution prerequisite",
        "status": _status(p1_execution_unblocked),
        "ok": p1_execution_unblocked,
        "p1_inputs_ready": bool(payload.get("p1_inputs_ready", False)),
        "p1_execution_unblocked": p1_execution_unblocked,
        "p0_release_blocker": bool(payload.get("p0_release_blocker", True)),
    }


def build_status(
    *,
    p1_readiness_status: Path | None = None,
    commercial_readiness: Path = DEFAULT_COMMERCIAL_READINESS,
    benchmark_reports: list[Path] | tuple[Path, ...] | None = None,
) -> dict[str, Any]:
    p1_gate = _p1_gate(_read_or_build_p1(p1_readiness_status))
    reports = list(benchmark_reports if benchmark_reports is not None else DEFAULT_BENCHMARK_REPORTS)
    evidence_gates = [_commercial_gate(commercial_readiness), *[_benchmark_gate(path) for path in reports]]
    benchmark_breadth_inputs_ready = all(bool(gate["ok"]) for gate in evidence_gates)
    p1_benchmark_execution_unblocked = bool(benchmark_breadth_inputs_ready and p1_gate["p1_execution_unblocked"])
    if not benchmark_breadth_inputs_ready:
        next_action = "fix blocked P1 benchmark breadth evidence"
    elif bool(p1_gate["p0_release_blocker"]):
        next_action = "close P0-1 release publication before running P1 benchmark breadth"
    elif not bool(p1_gate["p1_inputs_ready"]):
        next_action = "fix blocked P1 readiness gates"
    else:
        next_action = "run P1 quality/fallback/benchmark breadth execution"
    pass_count = sum(1 for gate in evidence_gates if bool(gate["ok"]))
    return {
        "schema_version": "p1-benchmark-breadth-status.v1",
        "status": "ready" if p1_benchmark_execution_unblocked else "blocked",
        "benchmark_breadth_inputs_ready": benchmark_breadth_inputs_ready,
        "p1_benchmark_execution_unblocked": p1_benchmark_execution_unblocked,
        "p1_execution_unblocked": bool(p1_gate["p1_execution_unblocked"]),
        "p0_release_blocker": bool(p1_gate["p0_release_blocker"]),
        "summary": {
            "evidence_gate_count": len(evidence_gates),
            "evidence_gate_pass_count": pass_count,
            "benchmark_report_count": len(reports),
        },
        "gates": [p1_gate, *evidence_gates],
        "next_action": next_action,
    }


def _markdown(status: dict[str, Any]) -> str:
    lines = [
        "# P1 Benchmark Breadth Status",
        "",
        f"- Benchmark inputs ready: `{bool(status['benchmark_breadth_inputs_ready'])}`",
        f"- P1 benchmark execution unblocked: `{bool(status['p1_benchmark_execution_unblocked'])}`",
        f"- P0 release blocker: `{bool(status['p0_release_blocker'])}`",
        f"- Next action: `{status['next_action']}`",
        "",
        "| Gate | Status | Evidence |",
        "| --- | --- | --- |",
    ]
    for gate in status["gates"]:
        evidence = str(gate.get("summary_line", "") or gate.get("path", ""))
        lines.append(f"| {gate['label']} | `{gate['status']}` | {evidence} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize P1 benchmark breadth readiness.")
    parser.add_argument("--p1-readiness-status", type=Path)
    parser.add_argument("--commercial-readiness", type=Path, default=DEFAULT_COMMERCIAL_READINESS)
    parser.add_argument(
        "--benchmark-report",
        action="append",
        type=Path,
        dest="benchmark_reports",
        help="Benchmark evidence report. Repeat to override the default report set.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--out-md", type=Path)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = build_status(
            p1_readiness_status=args.p1_readiness_status,
            commercial_readiness=args.commercial_readiness,
            benchmark_reports=args.benchmark_reports,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"P1 benchmark breadth status check failed: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(status), encoding="utf-8")
    print(payload if args.json else _markdown(status))
    return 1 if args.fail_blocked and not bool(status["p1_benchmark_execution_unblocked"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
