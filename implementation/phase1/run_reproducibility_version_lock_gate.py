#!/usr/bin/env python3
"""Deterministic replay + version lock gate for legal-grade reproducibility."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import platform
import sys

import numpy as np

from experiment_artifact_archive import archive_test_outputs
from rust_nonlinear_frame_bridge import RustNonlinearFrameConfig, build_story_load_profile, solve_nonlinear_frame
from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


REASONS = {
    "PASS": "reproducibility version-lock gate passed",
    "ERR_INVALID_INPUT": "invalid reproducibility input",
    "ERR_CASES": "insufficient cases for deterministic replay",
    "ERR_MODEL_HASH": "model artifact hash lock failed",
    "ERR_REPLAY_MISMATCH": "replay outputs mismatch under locked seed",
    "ERR_LOCK_WRITE": "version-lock manifest write failed",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "cases",
        "target_split",
        "min_case_count",
        "max_case_count",
        "seed",
        "replay_runs",
        "model_artifacts",
        "lock_manifest_out",
        "out",
    ],
    "properties": {
        "cases": {"type": "string", "minLength": 1},
        "target_split": {"type": "string", "enum": ["all", "train", "val", "test"]},
        "min_case_count": {"type": "integer", "minimum": 1},
        "max_case_count": {"type": "integer", "minimum": 1},
        "seed": {"type": "integer"},
        "replay_runs": {"type": "integer", "minimum": 2},
        "model_artifacts": {"type": "string"},
        "lock_manifest_out": {"type": "string", "minLength": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _story_count_for_topology(topology: str) -> int:
    t = str(topology).strip().lower()
    if t == "outrigger":
        return 24
    if t == "wall-frame":
        return 20
    if t == "truss":
        return 16
    if t == "rahmen":
        return 12
    return 14


def _build_story_stiffness_from_drift(
    *,
    floor_load_n: np.ndarray,
    story_h_m: np.ndarray,
    drift_ratio_hf: float,
) -> np.ndarray:
    n = int(story_h_m.shape[0])
    s = np.linspace(1.0, 1.25, num=n, dtype=np.float64)
    shear = np.cumsum(np.flip(floor_load_n))
    shear = np.flip(shear)
    denom = np.maximum(story_h_m * s, 1e-9)
    base = float(np.max(shear / denom) / max(float(drift_ratio_hf), 1e-6))
    return np.maximum(1e3, base) * s


def _snapshot_hash(rows: list[dict]) -> str:
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_model_artifacts(raw: str) -> list[str]:
    out: list[str] = []
    for tok in str(raw).split(","):
        s = tok.strip()
        if s:
            out.append(s)
    return out


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="reproducibility_version_lock_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    logger = get_logger("phase3.run_reproducibility_version_lock_gate")
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="implementation/phase1/commercial_benchmark_cases.from_csv.json")
    p.add_argument("--target-split", choices=["all", "train", "val", "test"], default="all")
    p.add_argument("--min-case-count", type=int, default=2)
    p.add_argument("--max-case-count", type=int, default=4)
    p.add_argument("--seed", type=int, default=23)
    p.add_argument("--replay-runs", type=int, default=3)
    p.add_argument(
        "--model-artifacts",
        default="implementation/phase1/winning_ticket_backprop_report.json,implementation/phase1/tgnn_multidomain_report.json",
    )
    p.add_argument("--lock-manifest-out", default="implementation/phase1/release/version_lock_manifest.json")
    p.add_argument("--out", default="implementation/phase1/reproducibility_version_lock_report.json")
    args = p.parse_args()

    input_payload = {
        "cases": str(args.cases),
        "target_split": str(args.target_split),
        "min_case_count": int(args.min_case_count),
        "max_case_count": int(args.max_case_count),
        "seed": int(args.seed),
        "replay_runs": int(args.replay_runs),
        "model_artifacts": str(args.model_artifacts),
        "lock_manifest_out": str(args.lock_manifest_out),
        "out": str(args.out),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase3.run_reproducibility_version_lock_gate")
        log_event(logger, logging.INFO, "repro_lock.start", inputs=input_payload)

        raw = _load_json(Path(args.cases))
        cases = raw.get("cases")
        if not isinstance(cases, list):
            raise ValueError("cases[] missing")
        rows = [c for c in cases if isinstance(c, dict)]
        if str(args.target_split) != "all":
            rows = [c for c in rows if str(c.get("split", "")) == str(args.target_split)]
        rows = rows[: int(args.max_case_count)]
        if len(rows) < int(args.min_case_count):
            raise ValueError(f"selected cases {len(rows)} < min_case_count {int(args.min_case_count)}")

        cfg = RustNonlinearFrameConfig(
            tolerance=1e-7,
            max_iter=80,
            hardening_ratio=0.20,
            pdelta_factor=1.0,
        )

        replay_hashes: list[str] = []
        replay_rows: list[list[dict]] = []
        rust_backend_all = True

        for ridx in range(int(args.replay_runs)):
            rng = np.random.default_rng(int(args.seed))
            run_rows: list[dict] = []
            for case in rows:
                case_id = str(case.get("case_id", "unknown"))
                topology = str(case.get("topology_type", "rahmen"))
                n_story = _story_count_for_topology(topology)
                story_h = np.full(n_story, 3.2, dtype=np.float64)

                drift_hf_pct = float((((case.get("metrics") or {}).get("drift_ratio_pct") or {}).get("hf", 1.2)))
                base_hf_kn = float((((case.get("metrics") or {}).get("base_shear_kN") or {}).get("hf", 1000.0)))
                base_hf_n = max(1.0, base_hf_kn * 1000.0)
                floor_load = build_story_load_profile(n_story, base_hf_n, mode="triangular")
                story_k = _build_story_stiffness_from_drift(
                    floor_load_n=floor_load,
                    story_h_m=story_h,
                    drift_ratio_hf=max(drift_hf_pct / 100.0, 1e-6),
                )
                # Deterministic imperfection generated from locked seed.
                imperf = rng.normal(loc=1.0, scale=0.005, size=n_story).astype(np.float64)
                story_k = np.maximum(1e3, story_k * imperf)
                story_yield = np.maximum(1e-4, 0.58 * (drift_hf_pct / 100.0) * story_h)
                story_axial = (4.1e6 * float(case.get("load_scale", 1.0))) * np.linspace(1.28, 0.86, num=n_story, dtype=np.float64)

                solve = solve_nonlinear_frame(
                    story_k_n_per_m=story_k,
                    story_h_m=story_h,
                    story_axial_n=story_axial,
                    story_yield_drift_m=story_yield,
                    floor_load_n=floor_load,
                    cfg=cfg,
                )
                rust_ok = bool(str(solve.get("backend", "")).startswith("rust_ffi_"))
                rust_backend_all = bool(rust_backend_all and rust_ok)
                run_rows.append(
                    {
                        "case_id": case_id,
                        "backend": str(solve.get("backend", "")),
                        "converged": bool(solve.get("converged", False)),
                        "iterations": int(solve.get("iterations", 0)),
                        "residual_inf": round(float(solve.get("residual_inf", 0.0)), 12),
                        "top_displacement_m": round(float(solve.get("top_displacement_m", 0.0)), 12),
                        "base_shear_kn": round(float(solve.get("base_shear_kn", 0.0)), 12),
                        "plastic_story_count": int(solve.get("plastic_story_count", 0)),
                    }
                )
            replay_rows.append(run_rows)
            replay_hashes.append(_snapshot_hash(run_rows))

        replay_exact_match = bool(len(set(replay_hashes)) == 1)

        model_artifacts = _parse_model_artifacts(args.model_artifacts)
        model_hashes: dict[str, str] = {}
        missing_models: list[str] = []
        for ap in model_artifacts:
            pth = Path(ap)
            if pth.exists() and pth.is_file():
                model_hashes[str(pth)] = _sha256_file(pth)
            else:
                missing_models.append(str(pth))

        input_hashes = {
            str(Path(args.cases)): _sha256_file(Path(args.cases)),
            str(Path(__file__)): _sha256_file(Path(__file__)),
        }

        lock_manifest = {
            "schema_version": "1.0",
            "run_id": "phase3-version-lock-manifest",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "seed": int(args.seed),
            "replay_runs": int(args.replay_runs),
            "platform": {
                "python": sys.version.split()[0],
                "system": platform.system(),
                "machine": platform.machine(),
            },
            "input_hashes": input_hashes,
            "model_hashes": model_hashes,
            "replay_hashes": replay_hashes,
            "replay_digest": replay_hashes[0] if replay_hashes else "",
        }
        lock_path = Path(args.lock_manifest_out)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(lock_manifest, indent=2), encoding="utf-8")

        checks = {
            "case_count_pass": bool(len(rows) >= int(args.min_case_count)),
            "seed_locked": bool(isinstance(args.seed, int)),
            "input_hashes_frozen": bool(all(len(v) == 64 for v in input_hashes.values())),
            "model_hashes_frozen": bool(len(model_hashes) > 0 and all(len(v) == 64 for v in model_hashes.values())),
            "no_missing_model_artifacts": bool(len(missing_models) == 0),
            "rust_backend_used_pass": bool(rust_backend_all),
            "replay_exact_match": bool(replay_exact_match),
            "lock_manifest_written": bool(lock_path.exists()),
        }
        contract_pass = bool(all(checks.values()))

        if not checks["case_count_pass"]:
            reason_code = "ERR_CASES"
        elif not checks["model_hashes_frozen"] or not checks["no_missing_model_artifacts"]:
            reason_code = "ERR_MODEL_HASH"
        elif not checks["replay_exact_match"] or not checks["rust_backend_used_pass"]:
            reason_code = "ERR_REPLAY_MISMATCH"
        elif not checks["lock_manifest_written"]:
            reason_code = "ERR_LOCK_WRITE"
        else:
            reason_code = "PASS"

        report = {
            "schema_version": "1.0",
            "run_id": "phase3-reproducibility-version-lock-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": {
                "case_count": int(len(rows)),
                "replay_runs": int(args.replay_runs),
                "seed": int(args.seed),
                "replay_hashes": replay_hashes,
                "missing_model_artifacts": missing_models,
            },
            "lock_manifest": str(lock_path),
            "rows_head": replay_rows[0][:16] if replay_rows else [],
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact_archive_manifest"] = _archive([str(out), str(lock_path), str(args.cases)])
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")

        log_event(logger, logging.INFO, "repro_lock.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote reproducibility version-lock gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (ValueError, FileNotFoundError, InputContractError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase3-reproducibility-version-lock-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "repro_lock.invalid_input", error=str(exc))
        print(f"Wrote reproducibility version-lock gate report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

