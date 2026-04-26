#!/usr/bin/env python3
"""Run global-authority validation tracks (OpenSees/SAC/NHERI).

This gate is strict-real-source first:
- OpenSees: parse and topology-contract validation.
- SAC/NHERI: require explicit source provenance + local reference artifacts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

import numpy as np


REASONS = {
    "PASS": "global authority gate passed",
    "ERR_INVALID_INPUT": "invalid gate input",
    "ERR_OPENSEES_FAIL": "opensees authority track failed",
    "ERR_HOLDOUT_LEAK": "holdout manifest validation failed",
    "ERR_METRICS_GENERATION_FAIL": "authority metrics generation failed",
    "ERR_SAC_MISSING": "sac authority track required but missing cases",
    "ERR_SAC_MIN_CASES": "sac authority track has fewer than required cases",
    "ERR_SAC_FAIL": "sac authority track failed",
    "ERR_SAC_SOURCE_DIVERSITY": "sac authority track input diversity/integrity failed",
    "ERR_NHERI_MISSING": "nheri authority track required but missing cases",
    "ERR_NHERI_MIN_CASES": "nheri authority track has fewer than required cases",
    "ERR_NHERI_FAIL": "nheri authority track failed",
    "ERR_NHERI_SOURCE_DIVERSITY": "nheri authority track input diversity/integrity failed",
}


def _run(cmd: list[str]) -> tuple[bool, float, int, str, str]:
    t0 = time.time()
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    dt = time.time() - t0
    return (
        proc.returncode == 0,
        dt,
        int(proc.returncode),
        (proc.stdout or "")[-3000:],
        (proc.stderr or "")[-3000:],
    )


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _bool(x: object) -> bool:
    return bool(x)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_source_integrity(case: dict, source_key: str) -> bool:
    source_path = str(case.get(source_key, "")).strip()
    source_sha = str(case.get("source_sha256", "")).strip().lower()
    if not source_path and not source_sha:
        return True
    if not source_path:
        return False
    p = Path(source_path)
    if not p.exists() or not p.is_file():
        return False
    if not source_sha:
        return True
    if len(source_sha) != 64:
        return False
    return _sha256_file(p) == source_sha


def _validate_file_with_hash(path_text: str, hash_text: str) -> bool:
    path_text = str(path_text).strip()
    hash_text = str(hash_text).strip().lower()
    if not path_text:
        return False
    p = Path(path_text)
    if not p.exists() or not p.is_file():
        return False
    if not hash_text:
        return True
    if len(hash_text) != 64:
        return False
    return _sha256_file(p) == hash_text


def _is_sample_like_path(path_text: str) -> bool:
    s = str(path_text).strip().lower()
    if not s:
        return False
    markers = ("sample", "toy", "synthetic", "sanity", "demo", "atwood")
    return any(m in s for m in markers)


def _load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _validate_metrics_report(
    path: str,
    required_checks: tuple[str, ...],
    required_metrics: tuple[str, ...],
) -> bool:
    report = _load_json(path)
    if not isinstance(report, dict):
        return False
    checks = report.get("checks")
    metrics = report.get("metrics")
    if not isinstance(checks, dict) or not isinstance(metrics, dict):
        return False
    if report.get("metric_source") != "direct_reference":
        return False
    if report.get("contract_pass") is not True:
        return False
    for key in required_checks:
        if checks.get(key) is not True:
            return False
    for key in required_metrics:
        if key not in metrics:
            return False
        try:
            float(metrics[key])
        except Exception:
            return False
    return True


def _default_case_metrics_npz_out(report_out: Path) -> Path:
    if report_out.suffix:
        return report_out.with_suffix(".metrics.npz")
    return report_out.parent / f"{report_out.name}.metrics.npz"


def _write_case_metrics_npz(
    path: Path,
    *,
    opensees_models: list[dict],
    sac_cases: list[dict],
    nheri_cases: list[dict],
    steps: list[dict],
) -> dict[str, object]:
    opensees_ids = [str(m.get("id", "")) for m in opensees_models if isinstance(m, dict)]
    opensees_real = [bool(m.get("real_source", False)) for m in opensees_models if isinstance(m, dict)]
    sac_ids = [str(c.get("case_id", "")) for c in sac_cases if isinstance(c, dict)]
    sac_real = [bool(c.get("real_source", False)) for c in sac_cases if isinstance(c, dict)]
    nheri_ids = [str(c.get("case_id", "")) for c in nheri_cases if isinstance(c, dict)]
    nheri_real = [bool(c.get("real_source", False)) for c in nheri_cases if isinstance(c, dict)]
    step_names = [str(s.get("step", "")) for s in steps if isinstance(s, dict)]
    step_rc = [int(s.get("return_code", 0)) for s in steps if isinstance(s, dict)]
    step_seconds = [float(s.get("seconds", 0.0)) for s in steps if isinstance(s, dict)]

    payload = {
        "opensees_model_ids": np.asarray(opensees_ids, dtype="<U128"),
        "opensees_real_source": np.asarray(opensees_real, dtype=np.bool_),
        "sac_case_ids": np.asarray(sac_ids, dtype="<U128"),
        "sac_real_source": np.asarray(sac_real, dtype=np.bool_),
        "nheri_case_ids": np.asarray(nheri_ids, dtype="<U128"),
        "nheri_real_source": np.asarray(nheri_real, dtype=np.bool_),
        "step_names": np.asarray(step_names, dtype="<U128"),
        "step_return_code": np.asarray(step_rc, dtype=np.int32),
        "step_seconds": np.asarray(step_seconds, dtype=np.float64),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **payload)
    return {
        "path": str(path),
        "case_count": int(len(opensees_ids) + len(sac_ids) + len(nheri_ids)),
        "step_count": int(len(step_names)),
        "storage": "npz_external",
    }


def _split_sets(manifest: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"train": set(), "val": set(), "test": set(), "holdout": set()}
    if not isinstance(manifest, dict):
        return out
    for key in tuple(out.keys()):
        raw = manifest.get(key)
        if isinstance(raw, list):
            out[key] = {str(x).strip() for x in raw if str(x).strip()}
    return out


def _holdout_only_case(case_id: str, split_sets: dict[str, set[str]]) -> bool:
    cid = str(case_id).strip()
    if not cid:
        return False
    if cid not in split_sets.get("holdout", set()):
        return False
    for key in ("train", "val", "test"):
        if cid in split_sets.get(key, set()):
            return False
    return True


def _run_metric_generation(
    *,
    mode: str,
    out_path: Path,
    steps: list[dict],
    **kwargs: str,
) -> bool:
    cmd = [
        sys.executable,
        "implementation/phase1/compute_global_authority_metrics.py",
        "--mode",
        str(mode),
        "--out",
        str(out_path),
    ]
    for key, value in kwargs.items():
        v = str(value).strip()
        if v:
            cmd.extend([f"--{key.replace('_', '-')}", v])
    ok, sec, rc, so, se = _run(cmd)
    steps.append(
        {
            "step": f"generate_{mode}_metrics",
            "seconds": float(sec),
            "return_code": int(rc),
            "command": shlex.join(cmd),
            "stdout_tail": so,
            "stderr_tail": se,
        }
    )
    return bool(out_path.exists())


def _validate_sac_case(case: dict) -> bool:
    if not isinstance(case, dict):
        return False
    if not str(case.get("case_id", "")).strip():
        return False
    if not _bool(case.get("real_source", False)):
        return False
    if not str(case.get("source_url", "")).strip():
        return False
    ref = str(case.get("reference_metrics_path", "")).strip()
    holdout_split = str(case.get("holdout_split", "holdout")).strip()
    if holdout_split != "holdout":
        return False
    if not (bool(ref) and Path(ref).exists()):
        return False
    if not _validate_source_integrity(case, "source_file_path"):
        return False
    return _validate_metrics_report(
        ref,
        required_checks=(
            "drift_within_5pct",
            "base_shear_within_5pct",
            "mac_above_095",
            "member_force_components_5d_pass",
        ),
        required_metrics=("drift_error_pct", "base_shear_error_pct", "mode_shape_mac"),
    )


def _validate_nheri_case(case: dict) -> bool:
    if not isinstance(case, dict):
        return False
    if not str(case.get("case_id", "")).strip():
        return False
    if not _bool(case.get("real_source", False)):
        return False
    if not str(case.get("source_url", "")).strip():
        return False
    sensor = str(case.get("sensor_csv_path", "")).strip()
    baseline = str(case.get("baseline_csv_path", "")).strip()
    waveform = str(case.get("waveform_metrics_path", "")).strip()
    if not bool(sensor and baseline and waveform):
        return False
    if not (Path(sensor).exists() and Path(baseline).exists() and Path(waveform).exists()):
        return False
    if not _validate_source_integrity(case, "source_file_path"):
        return False
    return _validate_metrics_report(
        waveform,
        required_checks=("waveform_corr_pass", "phase_error_pass", "residual_drift_pass"),
        required_metrics=("waveform_corr", "phase_error_ms", "residual_drift_mm"),
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--catalog",
        default="implementation/phase1/open_data/global_authority/authority_source_catalog.json",
    )
    p.add_argument(
        "--workdir-out",
        default="implementation/phase1/open_data/global_authority/run_artifacts",
    )
    p.add_argument("--require-opensees", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-sac", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--require-nheri", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--min-sac-cases", type=int, default=3)
    p.add_argument("--min-nheri-cases", type=int, default=3)
    p.add_argument("--require-distinct-sac-inputs", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-distinct-nheri-inputs", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--forbid-sample-authority-inputs", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--split-manifest", default="")
    p.add_argument("--auto-generate-metrics", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--sac-hf-csv-default", default="implementation/phase1/commercial_hf_export_sample.csv")
    p.add_argument("--sac-lf-csv-default", default="implementation/phase1/commercial_lf_export_sample.csv")
    p.add_argument("--nheri-sensor-csv-default", default="implementation/phase1/open_data/megastructure/field_sensor_record.csv")
    p.add_argument("--nheri-baseline-csv-default", default="implementation/phase1/open_data/megastructure/field_sensor_record.csv")
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--case-metrics-npz-out", default="")
    p.add_argument(
        "--out",
        default="implementation/phase1/global_authority_gate_report.json",
    )
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    case_metrics_npz_out = (
        Path(str(args.case_metrics_npz_out))
        if str(args.case_metrics_npz_out).strip()
        else _default_case_metrics_npz_out(out)
    )
    workdir_out = Path(args.workdir_out)
    workdir_out.mkdir(parents=True, exist_ok=True)

    reason_code = "PASS"
    steps: list[dict] = []

    catalog = _load(str(args.catalog))
    tracks = catalog.get("tracks") if isinstance(catalog.get("tracks"), dict) else {}
    if not tracks:
        reason_code = "ERR_INVALID_INPUT"

    opensees = tracks.get("opensees") if isinstance(tracks.get("opensees"), dict) else {}
    sac = tracks.get("sac") if isinstance(tracks.get("sac"), dict) else {}
    nheri = tracks.get("nheri") if isinstance(tracks.get("nheri"), dict) else {}
    split_manifest_path = str(args.split_manifest).strip() or str(catalog.get("split_manifest_path", "")).strip()
    split_manifest = _load(split_manifest_path) if split_manifest_path else {}
    split_sets = _split_sets(split_manifest)
    holdout_manifest_pass = True if not split_manifest_path else bool(split_sets.get("holdout"))

    opensees_models = opensees.get("models") if isinstance(opensees.get("models"), list) else []
    opensees_required = bool(args.require_opensees) or bool(opensees.get("enabled", False))

    opensees_pass = True
    opensees_case_count = 0
    opensees_contract_pass_count = 0
    if opensees_required:
        if not opensees_models:
            opensees_pass = False
            reason_code = "ERR_OPENSEES_FAIL"
        for model in opensees_models:
            if not isinstance(model, dict):
                opensees_pass = False
                continue
            model_id = str(model.get("id", "model")).strip() or "model"
            model_path = Path(str(model.get("model_path", "")).strip())
            real_source = bool(model.get("real_source", False))
            require_mix = bool(model.get("require_shell_beam_mix", bool(args.require_shell_beam_mix)))
            if not model_path.exists() or not real_source:
                opensees_pass = False
                continue
            opensees_case_count += 1
            model_out_dir = workdir_out / "opensees"
            model_out_dir.mkdir(parents=True, exist_ok=True)
            report_path = model_out_dir / f"{model_id}_topology_report.json"
            edges_path = model_out_dir / f"{model_id}_edges.json"
            csr_path = model_out_dir / f"{model_id}_csr.npz"
            cmd = [
                sys.executable,
                "implementation/phase1/parse_opensees_to_csr.py",
                "--model",
                str(model_path),
                "--edges-out",
                str(edges_path),
                "--csr-out",
                str(csr_path),
                "--report-out",
                str(report_path),
                "--require-real-topology",
                "--forbid-synthetic-source",
            ]
            if require_mix:
                cmd.append("--require-shell-beam-mix")
            else:
                cmd.append("--no-require-shell-beam-mix")
            ok, sec, rc, so, se = _run(cmd)
            steps.append(
                {
                    "step": f"opensees_{model_id}",
                    "seconds": float(sec),
                    "return_code": int(rc),
                    "command": shlex.join(cmd),
                    "stdout_tail": so,
                    "stderr_tail": se,
                }
            )
            if not ok or not report_path.exists():
                opensees_pass = False
                continue
            rep = _load(str(report_path))
            checks = rep.get("checks") if isinstance(rep.get("checks"), dict) else {}
            one_pass = bool(
                rep.get("contract_pass", False)
                and str(rep.get("reason_code", "")) == "PASS"
                and bool(checks.get("source_is_opensees_text", False))
                and bool(checks.get("source_manifest_pass", False))
                and (not require_mix or bool(checks.get("shell_beam_mix_pass", False)))
            )
            if one_pass:
                opensees_contract_pass_count += 1
            else:
                opensees_pass = False
        if opensees_case_count == 0:
            opensees_pass = False
    if reason_code == "PASS" and not opensees_pass:
        reason_code = "ERR_OPENSEES_FAIL"

    sac_cases = sac.get("cases") if isinstance(sac.get("cases"), list) else []
    sac_required = bool(args.require_sac) or bool(sac.get("enabled", False))
    sac_case_count = len([c for c in sac_cases if isinstance(c, dict)])
    sac_valid_count = 0
    sac_input_pairs_seen: set[tuple[str, str]] = set()
    sac_duplicate_input_pair_count = 0
    sac_sample_input_blocked = True
    sac_hash_integrity_pass = True
    for case in sac_cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id", "unknown")).strip() or "unknown"
        hf_csv = str(case.get("hf_csv_path", "")).strip()
        lf_csv = str(case.get("lf_csv_path", "")).strip()
        hf_hash = str(case.get("hf_csv_sha256", "")).strip()
        lf_hash = str(case.get("lf_csv_sha256", "")).strip()
        hf_hash_valid = True
        lf_hash_valid = True
        if bool(args.require_distinct_sac_inputs) and hf_csv and lf_csv:
            pair = (hf_csv, lf_csv)
            if pair in sac_input_pairs_seen:
                sac_duplicate_input_pair_count += 1
            else:
                sac_input_pairs_seen.add(pair)
        if bool(args.forbid_sample_authority_inputs) and (
            (hf_csv and _is_sample_like_path(hf_csv)) or (lf_csv and _is_sample_like_path(lf_csv))
        ):
            sac_sample_input_blocked = False
        if hf_csv or hf_hash:
            hf_hash_valid = _validate_file_with_hash(hf_csv, hf_hash)
            if not hf_hash_valid:
                sac_hash_integrity_pass = False
        if lf_csv or lf_hash:
            lf_hash_valid = _validate_file_with_hash(lf_csv, lf_hash)
            if not lf_hash_valid:
                sac_hash_integrity_pass = False
        if bool(args.auto_generate_metrics) and hf_csv and lf_csv:
            metric_path_raw = str(case.get("reference_metrics_path", "")).strip()
            if metric_path_raw:
                metric_path = Path(metric_path_raw)
                metric_path.parent.mkdir(parents=True, exist_ok=True)
                gen_ok = _run_metric_generation(
                    mode="sac",
                    out_path=metric_path,
                    steps=steps,
                    hf_csv=hf_csv,
                    lf_csv=lf_csv,
                )
                if not gen_ok and reason_code == "PASS":
                    reason_code = "ERR_METRICS_GENERATION_FAIL"
        holdout_ok = _holdout_only_case(case_id, split_sets) if split_manifest_path else True
        valid = bool(_validate_sac_case(case) and holdout_ok)
        if valid:
            sac_valid_count += 1
        holdout_manifest_pass = bool(holdout_manifest_pass and holdout_ok)
        steps.append(
            {
                "step": f"sac_{case_id}",
                "return_code": 0 if valid else 1,
                "validation_only": True,
                "holdout_only": bool(holdout_ok),
                "hf_csv": hf_csv,
                "lf_csv": lf_csv,
                "hf_hash_valid": bool(hf_hash_valid),
                "lf_hash_valid": bool(lf_hash_valid),
            }
        )
    sac_pass = True
    sac_min_case_count_pass = bool(sac_case_count >= int(args.min_sac_cases))
    sac_source_diversity_pass = bool(
        (not bool(args.require_distinct_sac_inputs)) or sac_duplicate_input_pair_count == 0
    )
    sac_source_integrity_pass = bool(sac_sample_input_blocked and sac_hash_integrity_pass)
    if sac_required:
        if sac_case_count == 0:
            sac_pass = False
            if reason_code == "PASS":
                reason_code = "ERR_SAC_MISSING"
        elif not sac_min_case_count_pass:
            sac_pass = False
            if reason_code == "PASS":
                reason_code = "ERR_SAC_MIN_CASES"
        else:
            sac_pass = bool(
                sac_valid_count == sac_case_count
                and sac_source_diversity_pass
                and sac_source_integrity_pass
            )
            if reason_code == "PASS" and not sac_source_diversity_pass:
                reason_code = "ERR_SAC_SOURCE_DIVERSITY"
            elif reason_code == "PASS" and not sac_source_integrity_pass:
                reason_code = "ERR_SAC_SOURCE_DIVERSITY"
            elif reason_code == "PASS" and not sac_pass:
                reason_code = "ERR_SAC_FAIL"

    nheri_cases = nheri.get("cases") if isinstance(nheri.get("cases"), list) else []
    nheri_required = bool(args.require_nheri) or bool(nheri.get("enabled", False))
    nheri_case_count = len([c for c in nheri_cases if isinstance(c, dict)])
    nheri_valid_count = 0
    nheri_input_pairs_seen: set[tuple[str, str]] = set()
    nheri_duplicate_input_pair_count = 0
    nheri_sample_input_blocked = True
    nheri_hash_integrity_pass = True
    nheri_distinct_pair_pass = True
    for case in nheri_cases:
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id", "unknown")).strip() or "unknown"
        sensor_csv = str(case.get("sensor_csv_path", "")).strip() or str(args.nheri_sensor_csv_default)
        baseline_csv = str(case.get("baseline_csv_path", "")).strip() or str(args.nheri_baseline_csv_default)
        sensor_hash = str(case.get("sensor_csv_sha256", "")).strip() or str(case.get("source_sha256", "")).strip()
        baseline_hash = str(case.get("baseline_csv_sha256", "")).strip()
        if bool(args.require_distinct_nheri_inputs):
            pair = (sensor_csv, baseline_csv)
            if pair in nheri_input_pairs_seen:
                nheri_duplicate_input_pair_count += 1
            else:
                nheri_input_pairs_seen.add(pair)
            if sensor_csv == baseline_csv:
                nheri_distinct_pair_pass = False
        if bool(args.forbid_sample_authority_inputs) and (
            _is_sample_like_path(sensor_csv) or _is_sample_like_path(baseline_csv)
        ):
            nheri_sample_input_blocked = False
        if not _validate_file_with_hash(sensor_csv, sensor_hash):
            nheri_hash_integrity_pass = False
        if not _validate_file_with_hash(baseline_csv, baseline_hash):
            nheri_hash_integrity_pass = False
        if bool(args.auto_generate_metrics):
            metric_path_raw = str(case.get("waveform_metrics_path", "")).strip()
            if metric_path_raw:
                metric_path = Path(metric_path_raw)
                metric_path.parent.mkdir(parents=True, exist_ok=True)
                gen_ok = _run_metric_generation(
                    mode="nheri",
                    out_path=metric_path,
                    steps=steps,
                    sensor_csv=sensor_csv,
                    baseline_csv=baseline_csv,
                )
                if not gen_ok and reason_code == "PASS":
                    reason_code = "ERR_METRICS_GENERATION_FAIL"
        holdout_ok = _holdout_only_case(case_id, split_sets) if split_manifest_path else True
        valid = bool(_validate_nheri_case(case) and holdout_ok)
        if valid:
            nheri_valid_count += 1
        holdout_manifest_pass = bool(holdout_manifest_pass and holdout_ok)
        steps.append(
            {
                "step": f"nheri_{case_id}",
                "return_code": 0 if valid else 1,
                "validation_only": True,
                "holdout_only": bool(holdout_ok),
                "sensor_csv": sensor_csv,
                "baseline_csv": baseline_csv,
                "sensor_hash_valid": bool(_validate_file_with_hash(sensor_csv, sensor_hash)),
                "baseline_hash_valid": bool(_validate_file_with_hash(baseline_csv, baseline_hash)),
            }
        )
    nheri_pass = True
    nheri_min_case_count_pass = bool(nheri_case_count >= int(args.min_nheri_cases))
    nheri_source_diversity_pass = bool(
        ((not bool(args.require_distinct_nheri_inputs)) or nheri_duplicate_input_pair_count == 0)
        and nheri_distinct_pair_pass
    )
    nheri_source_integrity_pass = bool(nheri_sample_input_blocked and nheri_hash_integrity_pass)
    if nheri_required:
        if nheri_case_count == 0:
            nheri_pass = False
            if reason_code == "PASS":
                reason_code = "ERR_NHERI_MISSING"
        elif not nheri_min_case_count_pass:
            nheri_pass = False
            if reason_code == "PASS":
                reason_code = "ERR_NHERI_MIN_CASES"
        else:
            nheri_pass = bool(
                nheri_valid_count == nheri_case_count
                and nheri_source_diversity_pass
                and nheri_source_integrity_pass
            )
            if reason_code == "PASS" and not nheri_source_diversity_pass:
                reason_code = "ERR_NHERI_SOURCE_DIVERSITY"
            elif reason_code == "PASS" and not nheri_source_integrity_pass:
                reason_code = "ERR_NHERI_SOURCE_DIVERSITY"
            elif reason_code == "PASS" and not nheri_pass:
                reason_code = "ERR_NHERI_FAIL"

    if reason_code == "PASS" and split_manifest_path and not holdout_manifest_pass:
        reason_code = "ERR_HOLDOUT_LEAK"

    checks = {
        "opensees_pass": bool(opensees_pass),
        "sac_pass": bool(sac_pass),
        "nheri_pass": bool(nheri_pass),
        "holdout_manifest_pass": bool(holdout_manifest_pass),
        "sac_min_case_count_pass": bool(sac_min_case_count_pass),
        "sac_source_diversity_pass": bool(sac_source_diversity_pass),
        "sac_source_integrity_pass": bool(sac_source_integrity_pass),
        "nheri_min_case_count_pass": bool(nheri_min_case_count_pass),
        "nheri_source_diversity_pass": bool(nheri_source_diversity_pass),
        "nheri_source_integrity_pass": bool(nheri_source_integrity_pass),
        "opensees_required": bool(opensees_required),
        "sac_required": bool(sac_required),
        "nheri_required": bool(nheri_required),
    }
    contract_pass = bool(reason_code == "PASS" and checks["opensees_pass"] and checks["sac_pass"] and checks["nheri_pass"])
    if reason_code == "PASS" and not contract_pass:
        reason_code = "ERR_INVALID_INPUT"

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-global-authority-gate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "catalog": str(args.catalog),
            "workdir_out": str(args.workdir_out),
            "require_opensees": bool(args.require_opensees),
            "require_sac": bool(args.require_sac),
            "require_nheri": bool(args.require_nheri),
            "min_sac_cases": int(args.min_sac_cases),
            "min_nheri_cases": int(args.min_nheri_cases),
            "require_distinct_sac_inputs": bool(args.require_distinct_sac_inputs),
            "require_distinct_nheri_inputs": bool(args.require_distinct_nheri_inputs),
            "forbid_sample_authority_inputs": bool(args.forbid_sample_authority_inputs),
            "split_manifest": str(split_manifest_path),
            "auto_generate_metrics": bool(args.auto_generate_metrics),
            "require_shell_beam_mix": bool(args.require_shell_beam_mix),
            "case_metrics_npz_out": str(case_metrics_npz_out),
        },
        "summary": {
            "opensees_case_count": int(opensees_case_count),
            "opensees_contract_pass_count": int(opensees_contract_pass_count),
            "sac_case_count": int(sac_case_count),
            "sac_valid_count": int(sac_valid_count),
            "sac_duplicate_input_pair_count": int(sac_duplicate_input_pair_count),
            "nheri_case_count": int(nheri_case_count),
            "nheri_valid_count": int(nheri_valid_count),
            "nheri_duplicate_input_pair_count": int(nheri_duplicate_input_pair_count),
            "device_artifact_consumer": "not_applicable_reference_only",
            "response_binary_consumer": "npz_external_primary",
        },
        "checks": checks,
        "steps": steps,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    metrics_npz_summary = _write_case_metrics_npz(
        case_metrics_npz_out,
        opensees_models=opensees_models,
        sac_cases=sac_cases,
        nheri_cases=nheri_cases,
        steps=steps,
    )
    payload["artifacts"] = {
        "report_json": str(out),
        "case_metrics_npz_out": str(case_metrics_npz_out),
    }
    payload["summary"]["response_storage"] = "npz_external+inline_summary"
    payload["summary"]["case_metrics_npz_case_count"] = int(metrics_npz_summary.get("case_count", 0))
    payload["summary"]["case_metrics_npz_step_count"] = int(metrics_npz_summary.get("step_count", 0))
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote global authority gate report: {out}")
    if not contract_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
