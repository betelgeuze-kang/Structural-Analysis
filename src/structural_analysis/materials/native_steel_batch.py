"""Explicit optional CPU batch execution of the existing steel return mapping.

This is an execution adapter, not a different material law or authority profile.
The caller supplies a compiled library; there is no build or fallback on import.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import ctypes
import hashlib
import os
from pathlib import Path
from typing import Iterator, Sequence

import numpy as np

from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
    UniaxialPlasticityResponse,
    UniaxialPlasticityState,
    _require_finite,
)

_ACTIVE: ContextVar[NativeSteelBatch | None] = ContextVar(
    "native_steel_batch", default=None
)


class NativeSteelBatch:
    """FP64 independent trials, with deterministic per-fiber output ordering."""

    def __init__(self, library: str | Path, *, workers: int = 1) -> None:
        if type(workers) is not int or not 1 <= workers <= min(
            os.cpu_count() or 1, 256
        ):
            raise ValueError("workers must be an available positive CPU thread count")
        path = Path(library).resolve(strict=True)
        self.library_path = str(path)
        self.library_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.workers = workers
        self._library = ctypes.CDLL(str(path))
        self._call = self._library.sa_steel_batch_v1
        pointer = ctypes.POINTER(ctypes.c_double)
        self._call.argtypes = [
            ctypes.c_size_t,
            pointer,
            pointer,
            pointer,
            ctypes.c_int,
            pointer,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._call.restype = ctypes.c_int
        self._observed_workers = self._library.sa_steel_batch_last_workers_v1
        self._observed_workers.argtypes = []
        self._observed_workers.restype = ctypes.c_int
        self.last_observed_workers = 0
        self.calls = 0
        self.points = 0

    def metadata(self) -> dict[str, object]:
        return {
            "backend": "cpp_openmp_steel_batch.v1",
            "workers": self.workers,
            "library_sha256": self.library_sha256,
            "calls": self.calls,
            "points": self.points,
            "precision": "binary64",
            "fallback": "forbidden",
        }

    def evaluate_arrays(
        self, strains: np.ndarray, materials: np.ndarray, parents: np.ndarray
    ) -> np.ndarray:
        """Evaluate packed arrays; native validation rejects the whole batch."""
        values = np.require(strains, dtype=np.float64, requirements=["C", "A"])
        laws = np.require(materials, dtype=np.float64, requirements=["C", "A"])
        states = np.require(parents, dtype=np.float64, requirements=["C", "A"])
        if values.ndim != 1 or not 1 <= values.size <= 1_000_000:
            raise ValueError("strains must contain 1..1000000 material points")
        if laws.shape != (values.size, 5) or states.shape != (values.size, 4):
            raise ValueError("material/state array shape mismatch")
        output = np.empty((values.size, 11), dtype=np.float64)
        bad = ctypes.c_size_t()
        pointer = ctypes.POINTER(ctypes.c_double)
        status = self._call(
            values.size,
            values.ctypes.data_as(pointer),
            laws.ctypes.data_as(pointer),
            states.ctypes.data_as(pointer),
            self.workers,
            output.ctypes.data_as(pointer),
            ctypes.byref(bad),
        )
        self.calls += 1
        self.points += values.size
        self.last_observed_workers = self._observed_workers()
        if status != 0:
            raise ValueError(
                f"native steel batch rejected status={status} index={bad.value}"
            )
        if not np.all(np.isfinite(output)) or not np.all(
            np.isin(output[:, 10], (0.0, 1.0))
        ):
            raise ValueError("native steel batch returned invalid values")
        output.setflags(write=False)
        return output

    def integrate(
        self,
        materials: Sequence[BilinearCombinedHardeningSteel],
        strains: Sequence[float],
        parents: Sequence[UniaxialPlasticityState],
    ) -> tuple[UniaxialPlasticityResponse, ...]:
        if (
            len(materials) != len(strains)
            or len(parents) != len(strains)
            or len(strains) == 0
        ):
            raise ValueError("batch sequences must have the same nonzero length")
        laws, states, values = [], [], []
        for material, strain, parent in zip(materials, strains, parents, strict=True):
            if type(material) is not BilinearCombinedHardeningSteel:
                raise ValueError("native batch requires the exact supported steel law")
            material.validate_state_admissibility(parent)
            values.append(_require_finite("total_strain", strain))
            laws.append(
                [
                    material.elastic_modulus_mpa,
                    material.yield_stress_mpa,
                    material.isotropic_hardening_modulus_mpa,
                    material.kinematic_hardening_modulus_mpa,
                    material.yield_tolerance_mpa,
                ]
            )
            states.append(
                [
                    parent.plastic_strain,
                    parent.backstress_mpa,
                    parent.accumulated_plastic_strain,
                    parent.dissipated_energy_density_mj_per_m3,
                ]
            )
        output = self.evaluate_arrays(
            np.asarray(values), np.asarray(laws), np.asarray(states)
        )
        responses = []
        for strain, parent, row in zip(values, parents, output, strict=True):
            yielded = bool(row[10])
            state = (
                UniaxialPlasticityState(*map(float, row[6:10])) if yielded else parent
            )
            responses.append(
                UniaxialPlasticityResponse(
                    total_strain=strain,
                    stress_mpa=float(row[0]),
                    consistent_tangent_mpa=float(row[1]),
                    elastic_strain=float(row[2]),
                    yielded=yielded,
                    plastic_multiplier_increment=float(row[3]),
                    trial_yield_function_mpa=float(row[4]),
                    final_yield_function_mpa=float(row[5]),
                    committed_state_hash=parent.state_hash,
                    state=state,
                )
            )
        return tuple(responses)


def active_native_steel_batch() -> NativeSteelBatch | None:
    return _ACTIVE.get()


@contextmanager
def use_native_steel_batch(backend: NativeSteelBatch) -> Iterator[NativeSteelBatch]:
    """Scope an explicitly requested backend to this Python execution context."""
    if type(backend) is not NativeSteelBatch:
        raise ValueError("backend must be a NativeSteelBatch")
    token = _ACTIVE.set(backend)
    try:
        yield backend
    finally:
        _ACTIVE.reset(token)
