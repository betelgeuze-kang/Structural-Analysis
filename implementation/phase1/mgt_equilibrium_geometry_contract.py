#!/usr/bin/env python3
"""Shared equilibrium geometry contract for coupled assembly and replay."""

from __future__ import annotations

import numpy as np

EQUILIBRIUM_GEOMETRY_CONTRACT = "reference_node_xyz_u_only"


def assembly_node_xyz(*, node_xyz: np.ndarray, u: np.ndarray | None = None) -> np.ndarray:
    """Return the node map used for stiffness and replay assembly.

    Deformation enters only through ``u``; assembly must not pre-translate nodes.
    """
    _ = u
    return np.asarray(node_xyz, dtype=np.float64)
