from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/build_cases_from_megastructure_open.py")


def _write_wave_csv(path: Path, *, rows: int = 80) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "acc_x_g", "disp_top_mm", "disp_mid_mm"])
        for i in range(rows):
            t = i * 0.01
            acc = 0.08 * (1.0 if (i % 10) < 5 else -1.0)
            d1 = 2.0 * acc * (i / max(1, rows - 1))
            d2 = 1.3 * acc * (i / max(1, rows - 1))
            w.writerow([f"{t:.4f}", f"{acc:.6f}", f"{d1:.6f}", f"{d2:.6f}"])


def test_sanity_source_is_blocked(tmp_path: Path) -> None:
    csv_path = tmp_path / "el_centro_like_local.csv"
    _write_wave_csv(csv_path)
    report_path = tmp_path / "report.json"

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--input-path",
        str(tmp_path),
        "--report-out",
        str(report_path),
        "--dynamic-out",
        str(tmp_path / "dynamic.jsonl"),
        "--benchmark-out",
        str(tmp_path / "benchmark.json"),
        "--window-len",
        "20",
        "--window-stride",
        "10",
        "--max-cases",
        "16",
        "--forbid-local-sanity-wave",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["reason_code"] == "ERR_SYNTHETIC_SOURCE"


def test_real_source_manifest_pass(tmp_path: Path) -> None:
    csv_path = tmp_path / "field_sensor_record.csv"
    _write_wave_csv(csv_path)
    report_path = tmp_path / "report_ok.json"

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--input-path",
        str(tmp_path),
        "--report-out",
        str(report_path),
        "--dynamic-out",
        str(tmp_path / "dynamic_ok.jsonl"),
        "--benchmark-out",
        str(tmp_path / "benchmark_ok.json"),
        "--window-len",
        "20",
        "--window-stride",
        "10",
        "--max-cases",
        "16",
        "--forbid-local-sanity-wave",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["source_manifest_pass"] is True
    assert payload["checks"]["synthetic_source_detected"] is False
    assert isinstance(payload.get("raw_file_hashes"), dict)
    assert payload["raw_file_hashes"]


def test_open_benchmark_cases_embed_source_family_and_element_mix(tmp_path: Path) -> None:
    csv_path = tmp_path / "field_sensor_record.csv"
    _write_wave_csv(csv_path, rows=160)
    report_path = tmp_path / "report_meta.json"
    benchmark_path = tmp_path / "benchmark_meta.json"

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--input-path",
        str(tmp_path),
        "--candidate-id",
        "zenodo_atwood_highrise_shm_2025",
        "--report-out",
        str(report_path),
        "--dynamic-out",
        str(tmp_path / "dynamic_meta.jsonl"),
        "--benchmark-out",
        str(benchmark_path),
        "--window-len",
        "20",
        "--window-stride",
        "5",
        "--max-cases",
        "16",
        "--forbid-local-sanity-wave",
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    summary = benchmark["source_family_summary"]
    assert summary["distinct_source_family_count"] == 1
    assert summary["source_families"] == ["zenodo_atwood_highrise_shm_2025"]
    assert summary["shell_beam_mix_case_count"] >= 1
    assert "shell_beam_mix" in summary["element_mixes"]
    assert benchmark["source"]["source_family"] == "zenodo_atwood_highrise_shm_2025"
    assert benchmark["source"]["source_manifest_out"].endswith(".source_manifest.json")
    assert all(str(row.get("source_family", "")).strip() == "zenodo_atwood_highrise_shm_2025" for row in benchmark["cases"])
    assert any(str(row.get("element_mix", "")).strip() == "shell_beam_mix" for row in benchmark["cases"])
