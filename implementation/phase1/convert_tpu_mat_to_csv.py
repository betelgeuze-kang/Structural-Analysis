#!/usr/bin/env python3
"""Convert a TPU MAT case into a flat CSV plus conversion summary."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat


RUN_ID = "phase1-convert-tpu-mat-to-csv"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "TPU MAT file converted into flat CSV successfully.",
    "ERR_INPUT_MODE": "provide either --input-mat or --source-manifest.",
    "ERR_SOURCE_MANIFEST_INVALID": "source manifest is missing or does not point to a readable MAT file.",
    "ERR_MAT_LOAD": "MAT file could not be loaded or parsed.",
    "ERR_DATASET_NOT_FOUND": "requested dataset key is not available in the MAT payload.",
    "ERR_NO_NUMERIC_DATASET": "no usable numeric dataset could be inferred from the MAT payload.",
    "ERR_DATASET_INVALID": "selected dataset is not a 1D/2D real numeric array.",
    "ERR_TIME_KEY_INVALID": "requested time key is present but does not align with the selected dataset.",
}

TIME_HINTS = ("time", "time_s", "time_sec", "timeseries", "timestamp", "second", "seconds", "sec")
SIGNAL_HINTS = ("pressure", "cp", "force", "load", "coef", "coeff", "balance")
SAMPLE_FREQUENCY_HINTS = ("sample_frequency", "sample_frequecny", "sampling_frequency")
SAMPLE_PERIOD_HINTS = ("sample_period", "sampling_period")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_float(value: Any, default: float = math.nan) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _path_split(path: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    buffer = ""
    idx = 0
    raw = str(path).strip()
    while idx < len(raw):
        char = raw[idx]
        if char == ".":
            if buffer:
                tokens.append(("key", buffer))
                buffer = ""
            idx += 1
            continue
        if char == "[":
            if buffer:
                tokens.append(("key", buffer))
                buffer = ""
            end = raw.find("]", idx)
            if end < 0:
                raise KeyError(path)
            index_text = raw[idx + 1 : end].strip()
            if not index_text:
                raise KeyError(path)
            tokens.append(("index", int(index_text)))
            idx = end + 1
            continue
        buffer += char
        idx += 1
    if buffer:
        tokens.append(("key", buffer))
    return tokens


def _resolve_path(payload: dict[str, Any], raw_path: str) -> Any:
    current: Any = payload
    for kind, value in _path_split(raw_path):
        if kind == "key":
            if isinstance(current, dict):
                if value not in current:
                    raise KeyError(raw_path)
                current = current[value]
            elif isinstance(current, np.ndarray) and current.dtype.names and value in current.dtype.names:
                current = current[value]
            else:
                raise KeyError(raw_path)
        else:
            if isinstance(current, (list, tuple)):
                current = current[int(value)]
            elif isinstance(current, np.ndarray):
                current = current[int(value)]
            else:
                raise KeyError(raw_path)
    return current


def _is_real_numeric_array(value: Any) -> bool:
    try:
        arr = np.asarray(value)
    except Exception:
        return False
    if arr.dtype.kind in {"O", "U", "S", "V"}:
        return False
    if not np.issubdtype(arr.dtype, np.number):
        return False
    return not np.iscomplexobj(arr)


def _candidate_row(path: str, value: Any) -> dict[str, Any]:
    arr = np.asarray(value)
    tokens = tuple(re.findall(r"[A-Za-z0-9]+", path.lower()))
    joined = "_".join(tokens)
    is_time_like = joined in TIME_HINTS or any(token in TIME_HINTS for token in tokens)
    is_signal_like = joined in SIGNAL_HINTS or any(token in SIGNAL_HINTS for token in tokens)
    return {
        "path": path,
        "shape": [int(v) for v in arr.shape],
        "ndim": int(arr.ndim),
        "size": int(arr.size),
        "dtype": str(arr.dtype),
        "time_like": bool(is_time_like),
        "signal_like": bool(is_signal_like),
    }


def _collect_numeric_candidates(node: Any, path: str, out: list[dict[str, Any]], seen: set[int]) -> None:
    if isinstance(node, dict):
        obj_id = id(node)
        if obj_id in seen:
            return
        seen.add(obj_id)
        for key in sorted(node):
            key_name = str(key)
            child_path = f"{path}.{key_name}" if path else key_name
            _collect_numeric_candidates(node[key], child_path, out, seen)
        return
    if isinstance(node, (list, tuple)):
        obj_id = id(node)
        if obj_id in seen:
            return
        seen.add(obj_id)
        for idx, item in enumerate(node):
            child_path = f"{path}[{idx}]"
            _collect_numeric_candidates(item, child_path, out, seen)
        return
    if isinstance(node, np.ndarray) and node.dtype.names:
        base_path = path
        for field_name in node.dtype.names:
            child_path = f"{base_path}.{field_name}" if base_path else str(field_name)
            _collect_numeric_candidates(node[field_name], child_path, out, seen)
        return
    if _is_real_numeric_array(node):
        arr = np.asarray(node)
        if int(arr.size) > 0:
            out.append(_candidate_row(path, arr))


def _select_dataset_key(candidates: list[dict[str, Any]], explicit_key: str) -> str:
    if explicit_key:
        return explicit_key
    if not candidates:
        return ""
    preferred: list[tuple[int, int, str]] = []
    fallback: list[tuple[int, int, str]] = []
    for row in candidates:
        path = str(row["path"])
        path_lower = path.lower()
        ndim = int(row["ndim"])
        size = int(row["size"])
        if ndim not in {1, 2} or size <= 1:
            continue
        score = size
        if bool(row["signal_like"]):
            score += 1_000_000
        if bool(row["time_like"]):
            score -= 1_000_000
        if ndim == 2:
            score += 100_000
        preferred.append((score, size, path))
        fallback.append((size, size, path))
        if re.search(r"(pressure|cp|force|load)", path_lower):
            preferred.append((score + 250_000, size, path))
    if preferred:
        preferred.sort(reverse=True)
        return str(preferred[0][2])
    fallback.sort(reverse=True)
    return str(fallback[0][2]) if fallback else ""


def _select_time_key(candidates: list[dict[str, Any]], explicit_key: str, sample_sizes: tuple[int, ...]) -> str:
    if explicit_key:
        return explicit_key
    ranked: list[tuple[int, int, str]] = []
    for row in candidates:
        if int(row["ndim"]) != 1:
            continue
        size = int(row["size"])
        if size not in sample_sizes:
            continue
        score = size
        if bool(row["time_like"]):
            score += 1_000_000
        ranked.append((score, size, str(row["path"])))
    ranked.sort(reverse=True)
    return str(ranked[0][2]) if ranked else ""


def _positive_dt(values: np.ndarray) -> float | None:
    if values.size < 2:
        return None
    diffs = np.diff(values.astype(float))
    positive = diffs[np.isfinite(diffs) & (diffs > 0.0)]
    if positive.size <= 0:
        return None
    return float(np.min(positive))


def _infer_dt_from_scalar_metadata(candidates: list[dict[str, Any]], payload_root: dict[str, Any], row_count: int) -> tuple[float | None, str]:
    if row_count <= 1:
        return None, ""
    sample_freq: float | None = None
    sample_period: float | None = None
    for row in candidates:
        if int(row.get("size", 0)) != 1:
            continue
        path = str(row.get("path", "") or "")
        tokens = tuple(re.findall(r"[A-Za-z0-9]+", path.lower()))
        joined = "_".join(tokens)
        try:
            value = float(np.asarray(_resolve_path(payload_root, path)).reshape(-1)[0])
        except Exception:
            continue
        if not math.isfinite(value) or value <= 0.0:
            continue
        if joined in SAMPLE_FREQUENCY_HINTS or ("sample" in tokens and ("frequency" in tokens or "frequecny" in tokens)):
            sample_freq = value
        elif joined in SAMPLE_PERIOD_HINTS or ("sample" in tokens and "period" in tokens):
            sample_period = value
    if sample_freq is not None and sample_freq > 0.0:
        return 1.0 / float(sample_freq), "scalar_sample_frequency"
    if sample_period is not None and sample_period > 0.0:
        if sample_period <= 1.0:
            return float(sample_period), "scalar_sample_period"
        return float(sample_period) / float(max(row_count - 1, 1)), "scalar_sample_period_total"
    return None, ""


def _matlab_char_to_text(data: Any) -> Any:
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="ignore")
    if isinstance(data, np.ndarray):
        if data.dtype.kind in {"S", "U"}:
            flattened = data.reshape(-1)
            return "".join(str(v) for v in flattened).strip()
        if data.dtype.kind in {"u", "i"} and data.ndim >= 1:
            values = data.reshape(-1)
            if values.size and np.all((values >= 0) & (values <= 0x10FFFF)):
                try:
                    return "".join(chr(int(v)) for v in values).strip()
                except Exception:
                    return data
    return data


def _load_h5_dataset(dataset: h5py.Dataset, root: h5py.File) -> Any:
    data = dataset[()]
    if h5py.check_dtype(ref=dataset.dtype) is not None:
        refs = np.asarray(data)
        resolved: list[Any] = []
        for ref in refs.reshape(-1):
            if not ref:
                resolved.append(None)
            else:
                resolved.append(_load_h5_node(root[ref], root))
        return resolved if refs.ndim <= 1 else np.array(resolved, dtype=object).reshape(refs.shape)
    if dataset.attrs.get("MATLAB_class") in {b"char", "char"}:
        return _matlab_char_to_text(data)
    return data


def _load_h5_node(node: h5py.Group | h5py.Dataset, root: h5py.File) -> Any:
    if isinstance(node, h5py.Dataset):
        return _load_h5_dataset(node, root)
    payload: dict[str, Any] = {}
    for key in node.keys():
        if str(key).startswith("#"):
            continue
        payload[str(key)] = _load_h5_node(node[key], root)
    return payload


def _load_mat_payload(path: Path) -> tuple[dict[str, Any], str]:
    try:
        loaded = loadmat(path, simplify_cells=True)
        payload = {
            str(key): value
            for key, value in loaded.items()
            if not str(key).startswith("__")
        }
        return payload, "scipy.io.loadmat"
    except NotImplementedError:
        pass
    except ValueError as exc:
        if "7.3" not in str(exc):
            raise
    with h5py.File(path, "r") as root:
        payload = {
            str(key): _load_h5_node(root[key], root)
            for key in root.keys()
            if not str(key).startswith("#")
        }
    return payload, "h5py"


def _default_paths(mat_path: Path) -> tuple[Path, Path]:
    stem = mat_path.with_suffix("")
    return stem.with_suffix(".csv"), stem.with_suffix(".convert_report.json")


def _resolve_input_path(input_mat: str, source_manifest: str) -> tuple[Path | None, dict[str, Any], str, str]:
    manifest_payload: dict[str, Any] = {}
    manifest_path = str(source_manifest).strip()
    if str(input_mat).strip():
        return Path(str(input_mat).strip()), manifest_payload, "", ""
    if not manifest_path:
        return None, manifest_payload, "", ""
    manifest_payload = _load_json(Path(manifest_path))
    data_path = str(manifest_payload.get("data_path", "") or "").strip()
    return (Path(data_path) if data_path else None), manifest_payload, manifest_path, data_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-mat", default="")
    parser.add_argument("--source-manifest", default="")
    parser.add_argument("--dataset-key", default="")
    parser.add_argument("--time-key", default="")
    parser.add_argument("--sample-axis", type=int, choices=[0, 1], default=-1)
    parser.add_argument("--column-prefix", default="signal")
    parser.add_argument("--dt-s", type=float, default=math.nan)
    parser.add_argument("--summary-only", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--out-csv", default="")
    parser.add_argument("--out-report", default="")
    args = parser.parse_args()

    reason_code = "PASS"
    reason = REASONS[reason_code]

    mat_path, source_manifest_payload, source_manifest_path, manifest_data_path = _resolve_input_path(
        input_mat=str(args.input_mat).strip(),
        source_manifest=str(args.source_manifest).strip(),
    )

    if mat_path is None:
        if str(args.source_manifest).strip():
            reason_code = "ERR_SOURCE_MANIFEST_INVALID"
        else:
            reason_code = "ERR_INPUT_MODE"
        reason = REASONS[reason_code]
        default_csv = Path(str(args.out_csv).strip()) if str(args.out_csv).strip() else Path(
            "implementation/phase1/open_data/wind/tpu.csv"
        )
        default_report = (
            Path(str(args.out_report).strip())
            if str(args.out_report).strip()
            else Path("implementation/phase1/open_data/wind/tpu.convert_report.json")
        )
        out_csv = default_csv
        out_report = default_report
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": reason,
            "inputs": {
                "input_mat": str(args.input_mat).strip(),
                "source_manifest": str(args.source_manifest).strip(),
                "dataset_key": str(args.dataset_key).strip(),
                "time_key": str(args.time_key).strip(),
            },
            "summary": {
                "dataset_name": "",
                "row_count": 0,
                "has_time_column": False,
                "dt_s": None,
            },
            "artifacts": {
                "out_csv": "",
            },
        }
        _write_json(out_report, payload)
        raise SystemExit(1)

    if str(args.out_csv).strip():
        out_csv = Path(str(args.out_csv).strip())
    else:
        out_csv = _default_paths(mat_path)[0]
    if str(args.out_report).strip():
        out_report = Path(str(args.out_report).strip())
    else:
        out_report = _default_paths(mat_path)[1]

    candidates: list[dict[str, Any]] = []
    loader_backend = ""
    payload_root: dict[str, Any] = {}
    if reason_code == "PASS":
        if str(args.source_manifest).strip() and (not mat_path.exists()):
            reason_code = "ERR_SOURCE_MANIFEST_INVALID"
            reason = REASONS[reason_code]
        elif not mat_path.exists():
            reason_code = "ERR_SOURCE_MANIFEST_INVALID" if str(args.source_manifest).strip() else "ERR_MAT_LOAD"
            reason = REASONS[reason_code]
        else:
            try:
                payload_root, loader_backend = _load_mat_payload(mat_path)
                _collect_numeric_candidates(payload_root, "", candidates, set())
                candidates.sort(key=lambda row: (-int(row["size"]), str(row["path"])))
            except Exception:
                reason_code = "ERR_MAT_LOAD"
                reason = REASONS[reason_code]

    dataset_key = str(args.dataset_key).strip()
    selected_dataset: np.ndarray | None = None
    selected_time: np.ndarray | None = None
    selected_time_key = str(args.time_key).strip()
    selected_sample_axis: int | None = None
    row_count = 0
    signal_count = 0
    has_time_column = False
    dt_s: float | None = None
    time_source_mode = ""
    out_csv_written = ""

    if reason_code == "PASS":
        dataset_key = _select_dataset_key(candidates, dataset_key)
        if not bool(args.summary_only):
            if not dataset_key:
                reason_code = "ERR_NO_NUMERIC_DATASET"
                reason = REASONS[reason_code]
            else:
                try:
                    selected_dataset = np.asarray(_resolve_path(payload_root, dataset_key))
                except Exception:
                    reason_code = "ERR_DATASET_NOT_FOUND"
                    reason = REASONS[reason_code]
                else:
                    if (
                        selected_dataset.dtype.kind in {"O", "U", "S", "V"}
                        or np.iscomplexobj(selected_dataset)
                        or selected_dataset.ndim not in {1, 2}
                        or int(selected_dataset.size) <= 0
                    ):
                        reason_code = "ERR_DATASET_INVALID"
                        reason = REASONS[reason_code]

    if reason_code == "PASS" and selected_dataset is not None:
        if selected_dataset.ndim == 1:
            selected_sample_axis = 0
            signal_matrix = selected_dataset.reshape(-1, 1)
        else:
            selected_time_key = _select_time_key(candidates, selected_time_key, tuple(int(v) for v in selected_dataset.shape))
            time_length = None
            if selected_time_key:
                try:
                    candidate_time = np.asarray(_resolve_path(payload_root, selected_time_key)).reshape(-1)
                except Exception:
                    reason_code = "ERR_TIME_KEY_INVALID"
                    reason = REASONS[reason_code]
                    candidate_time = np.array([], dtype=float)
                else:
                    time_length = int(candidate_time.size)
            if reason_code == "PASS":
                if int(args.sample_axis) in {0, 1}:
                    selected_sample_axis = int(args.sample_axis)
                elif time_length is not None and time_length == int(selected_dataset.shape[0]) and time_length != int(selected_dataset.shape[1]):
                    selected_sample_axis = 0
                elif time_length is not None and time_length == int(selected_dataset.shape[1]) and time_length != int(selected_dataset.shape[0]):
                    selected_sample_axis = 1
                else:
                    selected_sample_axis = 0 if int(selected_dataset.shape[0]) >= int(selected_dataset.shape[1]) else 1
                signal_matrix = selected_dataset if selected_sample_axis == 0 else selected_dataset.T
        signal_matrix = np.asarray(signal_matrix, dtype=float)
        row_count = int(signal_matrix.shape[0])
        signal_count = int(signal_matrix.shape[1]) if signal_matrix.ndim == 2 else 0

        if reason_code == "PASS":
            if selected_time_key:
                try:
                    selected_time = np.asarray(_resolve_path(payload_root, selected_time_key), dtype=float).reshape(-1)
                except Exception:
                    reason_code = "ERR_TIME_KEY_INVALID"
                    reason = REASONS[reason_code]
                else:
                    if int(selected_time.size) != row_count:
                        reason_code = "ERR_TIME_KEY_INVALID"
                        reason = REASONS[reason_code]
                    else:
                        has_time_column = True
                        dt_s = _positive_dt(selected_time)
                        time_source_mode = "explicit_time_key"
            elif math.isfinite(float(args.dt_s)):
                has_time_column = True
                selected_time = np.arange(row_count, dtype=float) * float(args.dt_s)
                dt_s = float(args.dt_s)
                time_source_mode = "cli_dt"
            else:
                inferred_dt, inferred_mode = _infer_dt_from_scalar_metadata(candidates, payload_root, row_count)
                if inferred_dt is not None and math.isfinite(float(inferred_dt)) and inferred_dt > 0.0:
                    has_time_column = True
                    selected_time = np.arange(row_count, dtype=float) * float(inferred_dt)
                    dt_s = float(inferred_dt)
                    time_source_mode = inferred_mode
                else:
                    dt_s = None

        if reason_code == "PASS" and not bool(args.summary_only):
            out_csv.parent.mkdir(parents=True, exist_ok=True)
            with out_csv.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                header = []
                if has_time_column:
                    header.append("time_s")
                header.extend(
                    f"{str(args.column_prefix).strip() or 'signal'}_{idx + 1:02d}"
                    for idx in range(signal_count)
                )
                writer.writerow(header)
                for row_idx in range(row_count):
                    row: list[Any] = []
                    if has_time_column and selected_time is not None:
                        row.append(float(selected_time[row_idx]))
                    row.extend(float(value) for value in signal_matrix[row_idx])
                    writer.writerow(row)
            out_csv_written = str(out_csv)

    report_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": reason,
        "inputs": {
            "input_mat": str(args.input_mat).strip(),
            "source_manifest": str(args.source_manifest).strip(),
            "source_manifest_data_path": manifest_data_path,
            "dataset_key": str(args.dataset_key).strip(),
            "time_key": str(args.time_key).strip(),
            "sample_axis": None if int(args.sample_axis) < 0 else int(args.sample_axis),
            "column_prefix": str(args.column_prefix).strip() or "signal",
            "dt_s": None if not math.isfinite(float(args.dt_s)) else float(args.dt_s),
            "summary_only": bool(args.summary_only),
        },
            "summary": {
                "source_name": str(source_manifest_payload.get("source_name", "") or ""),
                "source_origin_class": str(source_manifest_payload.get("source_origin_class", "") or ""),
                "loader_backend": loader_backend,
                "candidate_numeric_dataset_count": int(len(candidates)),
                "dataset_name": dataset_key,
                "time_name": selected_time_key,
                "row_count": int(row_count),
                "signal_column_count": int(signal_count),
                "has_time_column": bool(has_time_column),
                "dt_s": None if dt_s is None or not math.isfinite(float(dt_s)) else float(dt_s),
                "duration_hours": None if dt_s is None or row_count <= 1 else float((float(dt_s) * float(max(row_count - 1, 0))) / 3600.0),
                "selected_sample_axis": selected_sample_axis,
                "time_source_mode": time_source_mode,
            },
        "candidates": candidates,
        "artifacts": {
            "out_csv": out_csv_written,
        },
    }
    _write_json(out_report, report_payload)
    print(f"Wrote TPU MAT conversion report: {out_report}")
    if out_csv_written:
        print(f"Wrote TPU MAT CSV: {out_csv}")

    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
