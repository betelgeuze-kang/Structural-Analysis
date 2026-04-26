#!/usr/bin/env python3
"""Normalize Canton Tower reduced SHM raw text bundles into CSV for phase1 intake."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any
from zipfile import ZipFile

try:
    from implementation.phase1.canton_tower_reduced_order_utils import summarize_canton_tower_system_matrices
except ImportError:  # pragma: no cover - direct script execution fallback
    from canton_tower_reduced_order_utils import summarize_canton_tower_system_matrices


DEFAULT_ROOT = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm")
DEFAULT_ZIP = DEFAULT_ROOT / "Phase_I_data_all.zip"
DEFAULT_OUT_DIR = DEFAULT_ROOT / "normalized_csv"
DEFAULT_REPORT = DEFAULT_ROOT / "canton_tower_normalization_report.json"
DEFAULT_MATRIX_SUMMARY = DEFAULT_ROOT / "canton_tower_reduced_order_summary.json"
DT = 0.02


def _parse_matrix_lines(raw: bytes) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append([float(token) for token in stripped.split()])
    return rows


def _parse_vector_lines(raw: bytes) -> list[float]:
    out: list[float] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        out.append(float(stripped))
    return out


def _demean(values: list[float]) -> list[float]:
    if not values:
        return []
    mean = sum(values) / len(values)
    return [float(v - mean) for v in values]


def _integrate_acc_to_disp(acc: list[float], dt: float) -> list[float]:
    velocity = 0.0
    disp = 0.0
    out: list[float] = []
    for a in acc:
        velocity += dt * float(a) * 9.80665
        disp += dt * velocity
        out.append(disp)
    return _demean(out)


def _transpose_rows(rows: list[list[float]]) -> list[list[float]]:
    if not rows:
        return []
    col_count = len(rows[0])
    cols = [[] for _ in range(col_count)]
    for row in rows:
        for idx, value in enumerate(row):
            cols[idx].append(float(value))
    return cols


def _expand_hour_values(hour_values: list[float], sample_count: int) -> list[float]:
    if not hour_values or sample_count <= 0:
        return []
    if len(hour_values) == sample_count:
        return [float(value) for value in hour_values]
    out: list[float] = []
    scale = len(hour_values) / float(sample_count)
    for sample_idx in range(sample_count):
        source_idx = min(int(math.floor(sample_idx * scale)), len(hour_values) - 1)
        out.append(float(hour_values[source_idx]))
    return out


def _hour_index_from_name(name: str, ordered_names: list[str]) -> int:
    return ordered_names.index(name)


def normalize_package(
    zip_path: Path,
    out_dir: Path,
    *,
    start_hour_index: int = 0,
    hour_count: int = 1,
    matrix_path: Path | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    with ZipFile(zip_path) as zf:
        names = zf.namelist()
        acc_names = sorted(name for name in names if name.startswith("Acc data/") and name.endswith(".txt"))
        dir_names = sorted(name for name in names if name.startswith("Wind data/direction/") and name.endswith(".txt"))
        speed_names = sorted(name for name in names if name.startswith("Wind data/speed/") and name.endswith(".txt"))
        temp = _parse_vector_lines(zf.read("Temperature data/Temperature.txt"))

        chosen_acc = acc_names[start_hour_index : start_hour_index + hour_count]
        generated_rows: list[dict[str, Any]] = []
        for acc_name in chosen_acc:
            idx = _hour_index_from_name(acc_name, acc_names)
            wind_dir_name = dir_names[idx]
            wind_speed_name = speed_names[idx]

            acc_rows = _parse_matrix_lines(zf.read(acc_name))
            acc_cols = _transpose_rows(acc_rows)
            sample_count = len(acc_rows)
            channel_count = len(acc_cols)
            wind_dir = _parse_vector_lines(zf.read(wind_dir_name))
            wind_speed = _parse_vector_lines(zf.read(wind_speed_name))
            if len(wind_dir) != sample_count or len(wind_speed) != sample_count:
                raise ValueError(f"wind sample count mismatch for {acc_name}")

            temp_hour = temp[idx * 60 : (idx + 1) * 60]
            if len(temp_hour) != 60:
                raise ValueError(f"temperature slice mismatch for hour index {idx}")
            temperature = _expand_hour_values(temp_hour, sample_count)

            disp_cols = [_integrate_acc_to_disp(col, DT) for col in acc_cols]

            stem = Path(acc_name).stem
            out_path = out_dir / f"{stem}.csv"
            header = (
                ["time_sec"]
                + [f"acc_ch{col_idx + 1:02d}_g" for col_idx in range(channel_count)]
                + [f"disp_ch{col_idx + 1:02d}_m" for col_idx in range(channel_count)]
                + ["wind_direction_deg", "wind_speed_mps", "temperature_c"]
            )
            with out_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                for row_idx in range(sample_count):
                    writer.writerow(
                        [f"{row_idx * DT:.6f}"]
                        + [f"{acc_cols[col_idx][row_idx]:.10e}" for col_idx in range(channel_count)]
                        + [f"{disp_cols[col_idx][row_idx]:.10e}" for col_idx in range(channel_count)]
                        + [
                            f"{wind_dir[row_idx]:.10e}",
                            f"{wind_speed[row_idx]:.10e}",
                            f"{temperature[row_idx]:.10e}",
                        ]
                    )

            generated_rows.append(
                {
                    "source_acc_file": acc_name,
                    "source_wind_direction_file": wind_dir_name,
                    "source_wind_speed_file": wind_speed_name,
                    "target_csv": str(out_path),
                    "sample_count": sample_count,
                    "channel_count": channel_count,
                    "dt": DT,
                }
            )

    matrix_summary: dict[str, Any] = {}
    if matrix_path is not None and matrix_path.exists():
        try:
            matrix_summary = summarize_canton_tower_system_matrices(matrix_path)
        except Exception:
            matrix_summary = {}

    return {
        "schema_version": "1.0",
        "run_id": "phase1-normalize-canton-tower-reduced-shm-package",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "zip_path": str(zip_path),
        "out_dir": str(out_dir),
        "matrix_path": str(matrix_path) if matrix_path is not None else "",
        "summary": {
            "generated_csv_count": len(generated_rows),
            "generated_sample_count_total": sum(int(row["sample_count"]) for row in generated_rows),
            "generated_channel_count_max": max((int(row["channel_count"]) for row in generated_rows), default=0),
        },
        "generated_rows": generated_rows,
        "matrix_summary": matrix_summary,
        "contract_pass": bool(generated_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip-path", default=str(DEFAULT_ZIP))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--report-out", default=str(DEFAULT_REPORT))
    parser.add_argument("--matrix-path", default=str(DEFAULT_ROOT / "system_matrices.mat"))
    parser.add_argument("--matrix-summary-out", default=str(DEFAULT_MATRIX_SUMMARY))
    parser.add_argument("--start-hour-index", type=int, default=0)
    parser.add_argument("--hour-count", type=int, default=1)
    args = parser.parse_args()

    matrix_path = Path(args.matrix_path)
    payload = normalize_package(
        Path(args.zip_path),
        Path(args.out_dir),
        start_hour_index=int(args.start_hour_index),
        hour_count=int(args.hour_count),
        matrix_path=matrix_path if matrix_path.exists() else None,
    )
    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)
    report_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    matrix_summary = payload.get("matrix_summary")
    if isinstance(matrix_summary, dict) and matrix_summary:
        matrix_summary_out = Path(args.matrix_summary_out)
        matrix_summary_out.parent.mkdir(parents=True, exist_ok=True)
        matrix_summary_out.write_text(json.dumps(matrix_summary, indent=2), encoding="utf-8")
    print(f"Wrote Canton Tower normalization report: {report_out}")


if __name__ == "__main__":
    main()
