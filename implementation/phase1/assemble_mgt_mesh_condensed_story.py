#!/usr/bin/env python3
"""Condense MGT roundtrip NPZ mesh into a story-level nonlinear frame model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def assemble_story_model_from_mgt_npz(
    *,
    roundtrip_npz: Path,
    max_stories: int = 48,
) -> dict[str, Any]:
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        edge_index = np.asarray(archive["edge_index"], dtype=np.int64)

    z = node_xyz[:, 2]
    z_round = np.round(z, 3)
    levels = np.unique(z_round)
    levels.sort()
    if levels.size < 2:
        raise ValueError("MGT NPZ must contain at least two distinct elevation levels")

    story_edges = np.linspace(float(levels[0]), float(levels[-1]), num=min(int(max_stories), int(levels.size)) + 1)
    if story_edges.size < 2:
        story_edges = np.asarray([float(levels[0]), float(levels[-1])], dtype=np.float64)

    n_story = int(story_edges.size - 1)
    story_h = np.diff(story_edges)
    story_h = np.maximum(story_h, 0.5)

    elem_per_story = np.zeros(n_story, dtype=np.int64)
    if edge_index.shape[0] == 2 and edge_index.shape[1] > 0:
        mid_z = []
        for col in range(edge_index.shape[1]):
            i = int(edge_index[0, col])
            j = int(edge_index[1, col])
            if i < 0 or j < 0 or i >= node_xyz.shape[0] or j >= node_xyz.shape[0]:
                continue
            mid_z.append(0.5 * (float(node_xyz[i, 2]) + float(node_xyz[j, 2])))
        if mid_z:
            mid_z_arr = np.asarray(mid_z, dtype=np.float64)
            band = np.digitize(mid_z_arr, story_edges[1:-1], right=False)
            band = np.clip(band, 0, n_story - 1)
            for b in range(n_story):
                elem_per_story[b] = int(np.count_nonzero(band == b))

    elem_per_story = np.maximum(elem_per_story, 1)
    density_scale = elem_per_story.astype(np.float64) / float(np.max(elem_per_story))

    base_k = np.linspace(380000.0, 140000.0, n_story, dtype=np.float64)
    story_k = base_k * (0.55 + 0.45 * density_scale)
    story_axial = np.linspace(1.2e7, 1.8e6, n_story, dtype=np.float64) * (0.7 + 0.3 * density_scale)
    story_yield = story_h * np.clip(0.009 + 0.22 * density_scale, 0.006, 0.032)
    floor_load = story_axial * 0.082
    story_mass = story_axial / 9.80665 * 0.018
    story_damp = 0.052 * np.sqrt(np.maximum(story_k, 1.0) * np.maximum(story_mass, 1.0))

    return {
        "story_count": n_story,
        "elevation_levels_m": [float(v) for v in story_edges.tolist()],
        "elem_per_story": [int(v) for v in elem_per_story.tolist()],
        "story_k_n_per_m": story_k,
        "story_h_m": story_h,
        "story_axial_n": story_axial,
        "story_yield_drift_m": story_yield,
        "floor_load_base_n": floor_load,
        "story_mass_kg": story_mass,
        "story_damping_n_s_per_m": story_damp,
    }
