"""Tests for trust-region line search helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_equilibrium_line_search import (  # noqa: E402
    max_alpha_within_displacement_cap,
    trust_region_line_search_alphas,
)


def _translation_metrics(u: np.ndarray, node_xyz: np.ndarray) -> dict[str, float]:
    dof = 6
    translations = u.reshape(-1, dof)[:, :3]
    return {"max_translation_m": float(np.max(np.linalg.norm(translations, axis=1)))}


def test_max_alpha_within_displacement_cap_brackets_step() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    u = np.zeros(12, dtype=np.float64)
    delta = np.zeros(12, dtype=np.float64)
    delta[2] = 10.0
    alpha = max_alpha_within_displacement_cap(
        u=u,
        delta=delta,
        node_xyz=node_xyz,
        displacement_cap_m=2.0,
        translation_metrics=_translation_metrics,
    )
    assert 0.0 < alpha < 1.0
    trial = u + alpha * delta
    assert _translation_metrics(trial, node_xyz)["max_translation_m"] <= 2.0 + 1.0e-12


def test_max_alpha_honors_per_step_increment_cap() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0]], dtype=np.float64)
    u = np.zeros(6, dtype=np.float64)
    u[2] = 3.0
    delta = np.asarray([0.0, 0.0, 10.0, 0.0, 0.0, 0.0], dtype=np.float64)
    alpha = max_alpha_within_displacement_cap(
        u=u,
        delta=delta,
        node_xyz=node_xyz,
        displacement_cap_m=5.0,
        max_translation_increment_m=0.5,
        translation_metrics=_translation_metrics,
    )
    trial = u + alpha * delta
    assert _translation_metrics(trial, node_xyz)["max_translation_m"] <= 3.5 + 1.0e-9


def test_trust_region_line_search_alphas_respects_cap() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0]], dtype=np.float64)
    u = np.zeros(6, dtype=np.float64)
    delta = np.asarray([0.0, 0.0, 8.0, 0.0, 0.0, 0.0], dtype=np.float64)
    alphas = trust_region_line_search_alphas(
        u=u,
        delta=delta,
        node_xyz=node_xyz,
        displacement_cap_m=1.0,
        translation_metrics=_translation_metrics,
    )
    assert alphas
    assert max(alphas) <= 0.125 + 1.0e-9


def test_trust_region_line_search_can_include_signed_alphas() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0]], dtype=np.float64)
    u = np.zeros(6, dtype=np.float64)
    delta = np.asarray([0.0, 0.0, 2.0, 0.0, 0.0, 0.0], dtype=np.float64)

    alphas = trust_region_line_search_alphas(
        u=u,
        delta=delta,
        node_xyz=node_xyz,
        displacement_cap_m=3.0,
        translation_metrics=_translation_metrics,
        include_negative=True,
    )

    assert any(alpha < 0.0 for alpha in alphas)
    assert any(alpha > 0.0 for alpha in alphas)
