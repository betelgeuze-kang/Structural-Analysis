#!/usr/bin/env python3
"""Helpers for Canton Tower reduced-order SHM matrix summaries."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat, whosmat
from scipy.linalg import eigh


_SEGMENT_KEY_RE = re.compile(r"^(?P<kind>kk|mm)_(?P<segment>\d{2})$")


def _matrix_inventory(mat_path: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for name, shape, dtype in whosmat(mat_path):
        inventory.append(
            {
                "name": str(name),
                "shape": [int(dim) for dim in shape],
                "dtype": str(dtype),
            }
        )
    return inventory


def _extract_segment_pairs(names: list[str]) -> list[str]:
    kk_segments = {
        match.group("segment")
        for name in names
        if (match := _SEGMENT_KEY_RE.match(name)) and match.group("kind") == "kk"
    }
    mm_segments = {
        match.group("segment")
        for name in names
        if (match := _SEGMENT_KEY_RE.match(name)) and match.group("kind") == "mm"
    }
    return sorted(kk_segments & mm_segments)


def _safe_modes_hz(stiffness: np.ndarray, mass: np.ndarray, *, max_modes: int = 6) -> list[float]:
    if stiffness.ndim != 2 or mass.ndim != 2:
        return []
    if stiffness.shape != mass.shape or stiffness.shape[0] != stiffness.shape[1]:
        return []
    dof = int(stiffness.shape[0])
    if dof <= 0:
        return []
    subset_hi = min(max(int(max_modes * 4), int(max_modes)), dof) - 1
    try:
        eigvals = eigh(
            stiffness,
            mass,
            eigvals_only=True,
            subset_by_index=(0, subset_hi),
            check_finite=False,
        )
    except Exception:
        try:
            eigvals = np.linalg.eigvals(np.linalg.solve(mass, stiffness))
        except Exception:
            return []
    modes: list[float] = []
    for value in np.asarray(eigvals).reshape(-1):
        real = float(np.real(value))
        if not math.isfinite(real) or real <= 0.0:
            continue
        freq = math.sqrt(real) / (2.0 * math.pi)
        if math.isfinite(freq) and freq > 0.0:
            modes.append(float(freq))
    modes = sorted(modes)
    return [round(mode, 6) for mode in modes[: max(1, int(max_modes))]]


def summarize_canton_tower_system_matrices(mat_path: Path, *, max_modes: int = 6) -> dict[str, Any]:
    inventory = _matrix_inventory(mat_path)
    names = [str(row.get("name", "") or "") for row in inventory]
    payload = loadmat(mat_path, squeeze_me=True, struct_as_record=False)

    kk_global = payload.get("kk_global")
    mm_global = payload.get("mm_global")
    kk_global = np.asarray(kk_global) if kk_global is not None else None
    mm_global = np.asarray(mm_global) if mm_global is not None else None

    segment_pairs = _extract_segment_pairs(names)
    segment_dimensions: list[int] = []
    segment_modes: dict[str, list[float]] = {}
    for segment in segment_pairs[:8]:
        kk_key = f"kk_{segment}"
        mm_key = f"mm_{segment}"
        kk = payload.get(kk_key)
        mm = payload.get(mm_key)
        if kk is None or mm is None:
            continue
        kk_arr = np.asarray(kk)
        mm_arr = np.asarray(mm)
        if kk_arr.ndim == 2 and kk_arr.shape[0] == kk_arr.shape[1]:
            segment_dimensions.append(int(kk_arr.shape[0]))
        segment_modes[segment] = _safe_modes_hz(kk_arr, mm_arr, max_modes=min(3, max_modes))

    global_modes = (
        _safe_modes_hz(kk_global, mm_global, max_modes=max_modes)
        if kk_global is not None and mm_global is not None
        else []
    )

    global_dof = 0
    if kk_global is not None and kk_global.ndim == 2 and kk_global.shape[0] == kk_global.shape[1]:
        global_dof = int(kk_global.shape[0])

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mat_path": str(mat_path),
        "global_dof_count": global_dof,
        "global_matrix_present": bool(global_dof and mm_global is not None),
        "matrix_key_count": len(inventory),
        "segment_matrix_pair_count": len(segment_pairs),
        "segment_dimensions": sorted({int(value) for value in segment_dimensions}),
        "global_mode_frequencies_hz": global_modes,
        "segment_mode_frequencies_hz": segment_modes,
        "matrix_inventory": inventory,
    }

