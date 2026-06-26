"""Package CLI for the generated Phase 3 benchmark seed runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from structural_analysis.benchmark.factory import (
    build_manifest,
    generated_benchmark_factory_cases,
    run_benchmark_cases,
)


def build_runner_summary(
    *,
    manifest: dict[str, Any],
    scorecard: dict[str, Any],
    manifest_out: Path | None,
    scorecard_out: Path | None,
) -> dict[str, Any]:
    contract_pass = bool(
        scorecard.get("contract_pass") is True
        and scorecard.get("expected_output_contract_pass") is True
        and manifest.get("case_count") == scorecard.get("case_count")
        and set(manifest.get("lanes", [])) == set(scorecard.get("lanes", []))
    )
    return {
        "schema_version": "phase3-benchmark-runner-cli-summary.v1",
        "status": "pass" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "runner": "structural-analysis-benchmark",
        "module_command": "python -m structural_analysis.benchmark.cli",
        "case_count": scorecard.get("case_count", 0),
        "pass_count": scorecard.get("pass_count", 0),
        "expected_output_comparison_count": scorecard.get(
            "expected_output_comparison_count",
            0,
        ),
        "expected_output_comparison_pass_count": scorecard.get(
            "expected_output_comparison_pass_count",
            0,
        ),
        "expected_output_contract_pass": bool(
            scorecard.get("expected_output_contract_pass") is True
        ),
        "lanes": scorecard.get("lanes", []),
        "manifest_out": str(manifest_out) if manifest_out else None,
        "scorecard_out": str(scorecard_out) if scorecard_out else None,
        "phase3_closure_claim": False,
        "developer_preview_release_candidate_claim": False,
        "claim_boundary": (
            "This package CLI runs the generated analytic-small, element-patch, "
            "and nonlinear material-mesh benchmark seed only. It does not acquire "
            "OpenSees/buildingSMART/commercial/large-model corpora and does not "
            "close full Phase 3, full nonlinear full-mesh, G1 solver-core, or "
            "Developer Preview RC gates."
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="structural-analysis-benchmark")
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--scorecard-out", type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = generated_benchmark_factory_cases()
    manifest = build_manifest(cases)
    scorecard = run_benchmark_cases(cases)
    summary = build_runner_summary(
        manifest=manifest,
        scorecard=scorecard,
        manifest_out=args.manifest_out,
        scorecard_out=args.scorecard_out,
    )
    if args.manifest_out:
        _write_json(args.manifest_out, manifest)
    if args.scorecard_out:
        _write_json(args.scorecard_out, scorecard)
    if args.summary_out:
        _write_json(args.summary_out, summary)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Benchmark runner: "
            f"{summary['status']} | cases={summary['case_count']} | "
            f"pass={summary['pass_count']}"
        )
    return 1 if args.fail_blocked and not summary["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
