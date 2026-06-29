#!/usr/bin/env python3
"""Run real-data accuracy validation on RWTH Zenodo dataset.

Pipeline:
1) Build cases from RWTH CSV time-histories
2) Train/evaluate top-k benchmark
3) Run multi-seed precision stability suite
4) Emit compact validation summary
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import time

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_VERSION = "structural-optimization-workbench@1.0.0"

REASONS = {
    "PASS": "real accuracy validation passed",
    "ERR_INVALID_INPUT": "invalid input parameter range",
    "ERR_BUILD_CASES_FAIL": "rwth case generation failed",
    "ERR_BENCHMARK_FAIL": "top-k benchmark failed",
    "ERR_SUITE_FAIL": "multi-seed top-k suite failed",
    "ERR_VALIDATION_FAIL": "validation checks failed",
}

REAL_ACC_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["zip", "epochs", "branches", "top_k", "target_split", "summary_out"],
    "properties": {
        "zip": {"type": "string", "minLength": 1},
        "cases_out": {"type": "string", "minLength": 1},
        "benchmark_out": {"type": "string", "minLength": 1},
        "comparison_out": {"type": "string", "minLength": 1},
        "suite_out": {"type": "string", "minLength": 1},
        "summary_out": {"type": "string", "minLength": 1},
        "metric_source": {"type": "string", "minLength": 1},
        "accepted_metric_sources": {"type": "string", "minLength": 1},
        "min_public_hf_cases": {"type": "integer", "minimum": 1},
        "min_source_families": {"type": "integer", "minimum": 1},
        "require_shell_beam_mix": {"type": "boolean"},
        "story_height_mm": {"type": "number", "exclusiveMinimum": 0.0},
        "effective_mass_kg": {"type": "number", "exclusiveMinimum": 0.0},
        "epochs": {"type": "integer", "minimum": 1},
        "branches": {"type": "integer", "minimum": 2},
        "top_k": {"type": "integer", "minimum": 2},
        "lr": {"type": "number", "exclusiveMinimum": 0.0},
        "epsilon": {"type": "number", "exclusiveMinimum": 0.0},
        "temperature": {"type": "number", "exclusiveMinimum": 0.0},
        "seed": {"type": "integer"},
        "seeds": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
    },
}


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _path_key(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _sha256_or_missing(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _input_checksums(paths: list[Path]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in paths:
        checksums[_path_key(path)] = _sha256_or_missing(path)
    return checksums


def _source_tracking_metadata(paths: list[Path]) -> dict[str, object]:
    return {
        "source_commit_sha": _git_head(),
        "engine_version": ENGINE_VERSION,
        "input_checksums": _input_checksums(paths),
        "reused_evidence": False,
        "reuse_policy": "fresh_real_accuracy_validation_run",
    }


def _source_tracking_paths(args: argparse.Namespace) -> list[Path]:
    return [
        _resolve_repo_path("implementation/phase1/run_real_accuracy_validation.py"),
        _resolve_repo_path("implementation/phase1/build_cases_from_rwth_zenodo.py"),
        _resolve_repo_path("implementation/phase1/benchmark_kpi_contract.py"),
        _resolve_repo_path("implementation/phase1/run_topk_precision_experiments.py"),
        _resolve_repo_path("implementation/phase1/runtime_contracts.py"),
        _resolve_repo_path(args.zip),
        _resolve_repo_path(args.cases_out),
        _resolve_repo_path(args.benchmark_out),
        _resolve_repo_path(args.comparison_out),
        _resolve_repo_path(args.suite_out),
    ]


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-1500:],
        (proc.stderr or "")[-1500:],
    )


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    logger = get_logger("phase1.run_real_accuracy_validation")
    p = argparse.ArgumentParser()
    p.add_argument("--zip", default="implementation/phase1/open_data/rwth_zenodo_14173245/Data_v1.0.0.zip")
    p.add_argument("--cases-out", default="implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json")
    p.add_argument("--benchmark-out", default="implementation/phase1/hf_benchmark_report.rwth_zenodo.json")
    p.add_argument("--comparison-out", default="implementation/phase1/topk_comparison_experiment_report.rwth_zenodo.json")
    p.add_argument("--suite-out", default="implementation/phase1/topk_precision_suite_report.rwth_zenodo.json")
    p.add_argument("--summary-out", default="implementation/phase1/real_accuracy_validation_report.json")
    p.add_argument("--metric-source", default="open_data_measurement")
    p.add_argument("--accepted-metric-sources", default="engine_export_direct,commercial_solver_export,open_data_measurement")
    p.add_argument("--min-public-hf-cases", type=int, default=3)
    p.add_argument("--min-source-families", type=int, default=1)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--story-height-mm", type=float, default=3000.0)
    p.add_argument("--effective-mass-kg", type=float, default=250000.0)
    p.add_argument("--epochs", type=int, default=220)
    p.add_argument("--branches", type=int, default=10)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--lr", type=float, default=0.055)
    p.add_argument("--epsilon", type=float, default=0.11)
    p.add_argument("--temperature", type=float, default=0.32)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--seeds", default="11,17,23,31,47")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="test")
    args = p.parse_args()

    input_payload = {
        "zip": str(args.zip),
        "cases_out": str(args.cases_out),
        "benchmark_out": str(args.benchmark_out),
        "comparison_out": str(args.comparison_out),
        "suite_out": str(args.suite_out),
        "summary_out": str(args.summary_out),
        "metric_source": str(args.metric_source),
        "accepted_metric_sources": str(args.accepted_metric_sources),
        "min_public_hf_cases": int(args.min_public_hf_cases),
        "min_source_families": int(args.min_source_families),
        "require_shell_beam_mix": bool(args.require_shell_beam_mix),
        "story_height_mm": float(args.story_height_mm),
        "effective_mass_kg": float(args.effective_mass_kg),
        "epochs": int(args.epochs),
        "branches": int(args.branches),
        "top_k": int(args.top_k),
        "lr": float(args.lr),
        "epsilon": float(args.epsilon),
        "temperature": float(args.temperature),
        "seed": int(args.seed),
        "seeds": str(args.seeds),
        "target_split": str(args.target_split),
    }
    source_tracking = _source_tracking_metadata(_source_tracking_paths(args))

    Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)

    steps: list[dict] = []
    reason_code = "PASS"

    def _record(step: str, cmd: list[str]) -> bool:
        ok, seconds, return_code, stdout_tail, stderr_tail = _run(cmd)
        steps.append(
            {
                "step": step,
                "seconds": seconds,
                "command": shlex.join(cmd),
                "ok": bool(ok),
                "return_code": int(return_code),
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
            }
        )
        return bool(ok)

    try:
        validate_input_contract(input_payload, REAL_ACC_INPUT_SCHEMA, label="phase0.run_real_accuracy_validation")
        if int(args.top_k) > int(args.branches):
            raise ValueError("top_k cannot exceed branches")
        log_event(logger, logging.INFO, "real_accuracy.start", inputs=input_payload)

        cmd_build = [
            sys.executable,
            "implementation/phase1/build_cases_from_rwth_zenodo.py",
            "--zip",
            args.zip,
            "--out",
            args.cases_out,
            "--story-height-mm",
            str(args.story_height_mm),
            "--effective-mass-kg",
            str(args.effective_mass_kg),
            "--metric-source",
            args.metric_source,
            "--public-case-count",
            str(args.min_public_hf_cases),
            "--min-source-families",
            str(args.min_source_families),
            *(["--require-shell-beam-mix"] if bool(args.require_shell_beam_mix) else []),
        ]
        if not _record("build_cases_rwth", cmd_build):
            reason_code = "ERR_BUILD_CASES_FAIL"

        cmd_benchmark = [
            sys.executable,
            "implementation/phase1/benchmark_kpi_contract.py",
            "--cases",
            args.cases_out,
            "--out",
            args.benchmark_out,
            "--comparison-out",
            args.comparison_out,
            "--target-split",
            args.target_split,
            "--epochs",
            str(args.epochs),
            "--branches",
            str(args.branches),
            "--top-k",
            str(args.top_k),
            "--lr",
            str(args.lr),
            "--epsilon",
            str(args.epsilon),
            "--temperature",
            str(args.temperature),
            "--seed",
            str(args.seed),
            "--require-direct-metrics",
            "--accepted-metric-sources",
            args.accepted_metric_sources,
        ]
        if reason_code == "PASS" and not _record("benchmark_topk", cmd_benchmark):
            reason_code = "ERR_BENCHMARK_FAIL"

        cmd_suite = [
            sys.executable,
            "implementation/phase1/run_topk_precision_experiments.py",
            "--cases",
            args.cases_out,
            "--out",
            args.suite_out,
            "--seeds",
            args.seeds,
            "--epochs",
            str(args.epochs),
            "--branches",
            str(args.branches),
            "--top-k",
            str(args.top_k),
            "--lr",
            str(args.lr),
            "--epsilon",
            str(args.epsilon),
            "--temperature",
            str(args.temperature),
            "--target-split",
            args.target_split,
            "--require-direct-metrics",
            "--accepted-metric-sources",
            args.accepted_metric_sources,
        ]
        if reason_code == "PASS" and not _record("suite_multiseed", cmd_suite):
            reason_code = "ERR_SUITE_FAIL"

        cases_payload = _load(args.cases_out)
        benchmark = _load(args.benchmark_out)
        suite = _load(args.suite_out)
        public_cases = cases_payload.get("public_benchmark_cases", [])
        public_case_count = len(public_cases) if isinstance(public_cases, list) else 0
        public_cases_ok = bool(public_case_count >= int(args.min_public_hf_cases))
        case_metric_sources = sorted(
            {
                str(c.get("metric_source", ""))
                for c in cases_payload.get("cases", [])
                if isinstance(c, dict)
            }
        )
        source_families = sorted(
            {
                str(c.get("source_family", "")).strip()
                for c in cases_payload.get("cases", [])
                if isinstance(c, dict) and str(c.get("source_family", "")).strip()
            }
        )
        shell_beam_mix_count = sum(
            1
            for c in cases_payload.get("cases", [])
            if isinstance(c, dict) and str(c.get("element_mix", "unknown")).strip().lower() == "shell_beam_mix"
        )
        accepted_sources = {x.strip() for x in str(args.accepted_metric_sources).split(",") if x.strip()}
        direct_metric_source_ok = all(s in accepted_sources for s in case_metric_sources if s)
        source_family_ok = bool(len(source_families) >= int(args.min_source_families))
        shell_beam_mix_ok = bool((not bool(args.require_shell_beam_mix)) or shell_beam_mix_count > 0)

        summary = {
            "schema_version": "1.0",
            "run_id": "phase1-real-accuracy-validation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **source_tracking,
            "inputs": {
                "zip": args.zip,
                "cases_out": args.cases_out,
                "target_split": args.target_split,
                "epochs": int(args.epochs),
                "branches": int(args.branches),
                "top_k": int(args.top_k),
                "lr": float(args.lr),
                "epsilon": float(args.epsilon),
                "temperature": float(args.temperature),
                "seed": int(args.seed),
                "seeds": args.seeds,
                "min_public_hf_cases": int(args.min_public_hf_cases),
            },
            "dataset": {
                "source": cases_payload.get("source", {}),
                "split_counts": cases_payload.get("split_counts", {}),
                "case_count": len(cases_payload.get("cases", [])),
                "metric_sources": case_metric_sources,
                "source_families": source_families,
                "source_family_count": len(source_families),
                "shell_beam_mix_case_count": int(shell_beam_mix_count),
                "public_hf_case_count": public_case_count,
            },
            "checks": {
                "public_hf_case_count_pass": public_cases_ok,
                "direct_metric_source_pass": direct_metric_source_ok,
                "source_family_pass": source_family_ok,
                "shell_beam_mix_pass": shell_beam_mix_ok,
            },
            "benchmark": {
                "contract_pass": bool(benchmark.get("contract_pass", False)),
                "kpi_pass": bool(benchmark.get("kpi_pass", False)),
                "reason_code": benchmark.get("reason_code"),
                "metrics": benchmark.get("metrics", {}),
                "improvement_pct": benchmark.get("comparison", {}).get("improvement_pct", {}),
            },
            "stability_suite": {
                "suite_pass": bool(suite.get("checks", {}).get("suite_pass", False)),
                "quality_pass": bool(suite.get("checks", {}).get("quality_pass", False)),
                "stability_pass": bool(suite.get("checks", {}).get("stability_pass", False)),
                "summary_metrics": suite.get("summary_metrics", {}),
                "seed_count": len(suite.get("per_seed", [])),
            },
            "steps": steps,
            "overall_pass": (
                reason_code == "PASS"
                and bool(benchmark.get("contract_pass", False))
                and bool(suite.get("checks", {}).get("suite_pass", False))
                and public_cases_ok
                and direct_metric_source_ok
                and source_family_ok
                and shell_beam_mix_ok
            ),
        }
        if reason_code == "PASS" and not summary["overall_pass"]:
            reason_code = "ERR_VALIDATION_FAIL"
        summary["reason_code"] = reason_code

        out = Path(args.summary_out)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "real_accuracy.completed",
            overall_pass=bool(summary.get("overall_pass", False)),
            reason_code=reason_code,
        )
        print(f"Wrote real accuracy validation report: {out}")
        if not summary["overall_pass"]:
            raise SystemExit(1)
    except (ValueError, InputContractError) as exc:
        log_event(logger, logging.ERROR, "real_accuracy.invalid_input", error=str(exc))
        summary = {
            "schema_version": "1.0",
            "run_id": "phase1-real-accuracy-validation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **source_tracking,
            "inputs": input_payload,
            "steps": steps,
            "overall_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.summary_out)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote real accuracy validation report: {out}")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.ERROR, "real_accuracy.internal_error", error=repr(exc))
        summary = {
            "schema_version": "1.0",
            "run_id": "phase1-real-accuracy-validation",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **source_tracking,
            "inputs": input_payload,
            "steps": steps,
            "overall_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out = Path(args.summary_out)
        out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"Wrote real accuracy validation report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
