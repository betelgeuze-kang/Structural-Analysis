"""Explicit optional CPU batch execution of the existing steel return mapping.

This is an execution adapter, not a different material law or authority profile.
The caller supplies a compiled library; there is no build or fallback on import.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
import ctypes
import hashlib
import math
import os
from pathlib import Path
from threading import Lock
from typing import Iterator, Sequence, cast

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
_BULK_RESPONSE_LIMIT = 16_384
_SIGNATURE_ROW_SHARING_LIMIT = 256


class NativeSteelBatch:
    """FP64 independent trials, with deterministic per-fiber output ordering."""

    def __init__(
        self, library: str | Path, *, workers: int = 1, prepared: bool = False
    ) -> None:
        if type(prepared) is not bool:
            raise ValueError("prepared must be a boolean")
        if type(workers) is not int or not 1 <= workers <= min(
            os.cpu_count() or 1, 256
        ):
            raise ValueError("workers must be an available positive CPU thread count")
        path = Path(library).resolve(strict=True)
        self.library_path = str(path)
        self.library_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self.workers = workers
        self.prepared = prepared
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
        self.prepared_calls = 0
        self.prepared_points = 0
        self.group_calls = 0
        self.plan_builds = 0
        self.buffer_allocations = 0
        self._prepared_workspaces: OrderedDict[tuple, _PreparedSteelWorkspace] = (
            OrderedDict()
        )
        self._prepared_cache_lock = Lock()

    def execution_configuration(self) -> dict[str, object]:
        """Fixed execution choices, independent of accumulated trial counters."""
        return {
            "backend": "cpp_openmp_steel_batch.v1",
            "workers": self.workers,
            "library_sha256": self.library_sha256,
            "precision": "binary64",
            "fallback": "forbidden",
            "prepared": self.prepared,
        }

    def metadata(self) -> dict[str, object]:
        return {
            **self.execution_configuration(),
            "calls": self.calls,
            "points": self.points,
            "prepared_calls": self.prepared_calls,
            "prepared_points": self.prepared_points,
            "group_calls": self.group_calls,
            "plan_builds": self.plan_builds,
            "buffer_allocations": self.buffer_allocations,
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
        self._evaluate_arrays_into(values, laws, states, output)
        output.setflags(write=False)
        return output

    def _evaluate_arrays_into(
        self,
        values: np.ndarray,
        laws: np.ndarray,
        states: np.ndarray,
        output: np.ndarray,
        *,
        prepared_groups: int = 0,
    ) -> None:
        """Use owned scratch only after shape, alignment and alias admission."""
        self._validate_arrays(values, laws, states, output)
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
        if prepared_groups:
            self.prepared_calls += 1
            self.prepared_points += values.size
            self.group_calls += int(prepared_groups > 1)
        if status != 0:
            raise ValueError(
                f"native steel batch rejected status={status} index={bad.value}"
            )
        if not np.all(np.isfinite(output)) or not np.all(
            np.isin(output[:, 10], (0.0, 1.0))
        ):
            raise ValueError("native steel batch returned invalid values")

    @staticmethod
    def _validate_arrays(
        values: np.ndarray, laws: np.ndarray, states: np.ndarray, output: np.ndarray
    ) -> None:
        arrays = (values, laws, states, output)
        if any(
            not isinstance(array, np.ndarray)
            or array.dtype != np.dtype(np.float64)
            or not array.flags.c_contiguous
            or not array.flags.aligned
            for array in arrays
        ):
            raise ValueError("native steel arrays must be aligned contiguous float64")
        if values.ndim != 1 or not 1 <= values.size <= 1_000_000:
            raise ValueError("strains must contain 1..1000000 material points")
        if (
            laws.shape != (values.size, 5)
            or states.shape != (values.size, 4)
            or output.shape != (values.size, 11)
        ):
            raise ValueError("material/state/output array shape mismatch")
        if not output.flags.writeable or any(
            np.shares_memory(output, array) for array in arrays[:3]
        ):
            raise ValueError(
                "native steel output must be writable and not alias inputs"
            )

    def prepare(
        self, materials: Sequence[BilinearCombinedHardeningSteel]
    ) -> PreparedNativeSteelBatch:
        """Bind current law values to reusable packing; this is explicitly opt-in."""
        if not self.prepared:
            raise ValueError("prepared batches require prepared=True")
        current = tuple(materials)
        signature = _steel_material_signature(current)
        with self._prepared_cache_lock:
            workspace = self._prepared_workspaces.get(signature)
            if workspace is None:
                workspace = _PreparedSteelWorkspace(signature)
                self._prepared_workspaces[signature] = workspace
                self.plan_builds += 1
                while len(self._prepared_workspaces) > 8:
                    self._prepared_workspaces.popitem(last=False)
            else:
                self._prepared_workspaces.move_to_end(signature)
        return PreparedNativeSteelBatch(self, current, signature, workspace)

    def integrate_many(
        self,
        materials: Sequence[BilinearCombinedHardeningSteel],
        strains_by_point: Sequence[Sequence[float]],
        parents_by_point: Sequence[Sequence[UniaxialPlasticityState]],
    ) -> tuple[tuple[UniaxialPlasticityResponse, ...], ...]:
        """One C ABI call for point-major trials sharing one fiber-law layout."""
        plan = self.prepare(materials)
        # prepare() just captured the current primitive values in this call.
        return plan._integrate_many(
            strains_by_point, parents_by_point, verify_current=False
        )

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
        if self.prepared:
            return self.integrate_many(materials, (strains,), (parents,))[0]
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


def _steel_material_signature(
    materials: tuple[BilinearCombinedHardeningSteel, ...],
) -> tuple:
    if not 1 <= len(materials) <= 1_000_000:
        raise ValueError("materials must contain 1..1000000 material points")
    # This map lives for one snapshot only. Ordinary exact laws have no field
    # access hooks, so repeated references can share that call's fresh row.
    # Custom descriptors/accessors keep the original per-occurrence reads.
    plain_access = (
        BilinearCombinedHardeningSteel.__getattribute__ is object.__getattribute__
        and all(
            type(vars(BilinearCombinedHardeningSteel).get(name)) in (float, str)
            for name in (
                "elastic_modulus_mpa",
                "yield_stress_mpa",
                "isotropic_hardening_modulus_mpa",
                "kinematic_hardening_modulus_mpa",
                "yield_tolerance_mpa",
                "material_id",
            )
        )
    )
    shared: dict[int, tuple[BilinearCombinedHardeningSteel, tuple]] = {}
    rows: list[tuple[tuple[object, ...], ...]] = []
    for material in materials:
        if type(material) is not BilinearCombinedHardeningSteel:
            raise ValueError("native batch requires the exact supported steel law")
        previous = shared.get(id(material)) if plain_access else None
        if previous is not None and previous[0] is material:
            rows.append(previous[1])
            continue
        row: list[tuple[object, ...]] = []
        for value in (
            material.elastic_modulus_mpa,
            material.yield_stress_mpa,
            material.isotropic_hardening_modulus_mpa,
            material.kinematic_hardening_modulus_mpa,
            material.yield_tolerance_mpa,
            material.material_id,
        ):
            kind = type(value)
            if kind is float:
                floating = cast(float, value)
                if not math.isfinite(floating):
                    raise ValueError("prepared steel material values must be finite")
                # Packed arithmetic, unlike canonical JSON, must retain -0.0.
                row.append(
                    (
                        "float",
                        floating,
                        floating == 0.0 and math.copysign(1.0, floating) < 0.0,
                    )
                )
            elif kind is int:
                row.append(("integer", value))
            elif kind is bool:
                row.append(("boolean", value))
            elif kind is str:
                row.append(("string", value))
            else:
                raise ValueError(
                    "prepared steel material fields must be plain scalar values"
                )
        copied = tuple(row)
        rows.append(copied)
        if plain_access and len(shared) < _SIGNATURE_ROW_SHARING_LIMIT:
            shared[id(material)] = (material, copied)
    return tuple(rows)


class _SteelTrialBuffers:
    def __init__(self, materials: np.ndarray) -> None:
        self.materials = materials
        self.strains = np.empty(materials.shape[0], dtype=np.float64)
        self.parents = np.empty((materials.shape[0], 4), dtype=np.float64)
        self.output = np.empty((materials.shape[0], 11), dtype=np.float64)


class _PreparedSteelWorkspace:
    def __init__(self, signature: tuple) -> None:
        packed = np.asarray(
            [[item[1] for item in row[:5]] for row in signature], dtype=np.float64
        )
        self.materials = np.frombuffer(packed.tobytes(), dtype=np.float64).reshape(
            packed.shape
        )
        self.buffers: OrderedDict[int, _SteelTrialBuffers] = OrderedDict()
        self.lock = Lock()

    def trial_buffers(
        self, groups: int, backend: NativeSteelBatch
    ) -> _SteelTrialBuffers:
        buffers = self.buffers.get(groups)
        if buffers is None:
            materials = self.materials
            if groups != 1:
                packed = np.tile(materials, (groups, 1))
                materials = np.frombuffer(packed.tobytes(), dtype=np.float64).reshape(
                    packed.shape
                )
            buffers = _SteelTrialBuffers(materials)
            self.buffers[groups] = buffers
            backend.buffer_allocations += 1
            while len(self.buffers) > 2:
                self.buffers.popitem(last=False)
        else:
            self.buffers.move_to_end(groups)
        return buffers


class PreparedNativeSteelBatch:
    """Reusable scratch bound to fresh law values and immutable accepted parents.

    No array view escapes. Responses are reconstructed before the shared
    workspace lock is released, so a subsequent trial cannot alter an earlier
    result. Held plans reject changed law objects; backend.prepare() may instead
    select a new value-keyed workspace. Locks reject concurrent/reentrant use.
    """

    def __init__(
        self,
        backend: NativeSteelBatch,
        materials: tuple[BilinearCombinedHardeningSteel, ...],
        signature: tuple,
        workspace: _PreparedSteelWorkspace,
    ) -> None:
        self._backend = backend
        self._materials = materials
        self._signature = signature
        self._workspace = workspace

    def integrate(
        self,
        strains: Sequence[float],
        parents: Sequence[UniaxialPlasticityState],
    ) -> tuple[UniaxialPlasticityResponse, ...]:
        return self.integrate_many((strains,), (parents,))[0]

    def integrate_many(
        self,
        strains_by_point: Sequence[Sequence[float]],
        parents_by_point: Sequence[Sequence[UniaxialPlasticityState]],
    ) -> tuple[tuple[UniaxialPlasticityResponse, ...], ...]:
        return self._integrate_many(
            strains_by_point, parents_by_point, verify_current=True
        )

    def _integrate_many(
        self,
        strains_by_point: Sequence[Sequence[float]],
        parents_by_point: Sequence[Sequence[UniaxialPlasticityState]],
        *,
        verify_current: bool,
    ) -> tuple[tuple[UniaxialPlasticityResponse, ...], ...]:
        count = len(self._materials)
        groups = len(strains_by_point)
        if (
            groups == 0
            or groups != len(parents_by_point)
            or groups * count > 1_000_000
            or any(len(row) != count for row in strains_by_point)
            or any(len(row) != count for row in parents_by_point)
        ):
            raise ValueError("point batches must have the same nonzero fiber layout")
        if (
            verify_current
            and _steel_material_signature(self._materials) != self._signature
        ):
            raise ValueError(
                "prepared steel material values changed; prepare a new plan"
            )
        if not self._workspace.lock.acquire(blocking=False):
            raise ValueError("prepared native steel workspace is already in use")
        try:
            buffers = self._workspace.trial_buffers(groups, self._backend)
            self._backend._validate_arrays(
                buffers.strains, buffers.materials, buffers.parents, buffers.output
            )
            if (
                not buffers.strains.flags.writeable
                or not buffers.parents.flags.writeable
                or np.shares_memory(buffers.strains, buffers.parents)
                or np.shares_memory(buffers.strains, buffers.materials)
                or np.shares_memory(buffers.parents, buffers.materials)
            ):
                raise ValueError(
                    "prepared steel input scratch must be writable and independent"
                )
            flat_parents = []
            index = 0
            for strains, parents in zip(
                strains_by_point, parents_by_point, strict=True
            ):
                for material, strain, parent in zip(
                    self._materials, strains, parents, strict=True
                ):
                    material.validate_state_admissibility(parent)
                    buffers.strains[index] = _require_finite("total_strain", strain)
                    buffers.parents[index] = (
                        parent.plastic_strain,
                        parent.backstress_mpa,
                        parent.accumulated_plastic_strain,
                        parent.dissipated_energy_density_mj_per_m3,
                    )
                    flat_parents.append(parent)
                    index += 1
            self._backend._evaluate_arrays_into(
                buffers.strains,
                buffers.materials,
                buffers.parents,
                buffers.output,
                prepared_groups=groups,
            )
            # Detach exact scratch arrays in one C-level conversion instead of
            # creating a NumPy row/scalar object for every response field.
            # Bound extra Python float/list storage independently of the native
            # 1M-point admission. Larger batches and array subclasses keep the
            # original lazy row/scalar indexing path.
            response_strains = (
                buffers.strains.tolist()
                if type(buffers.strains) is np.ndarray
                and buffers.strains.size <= _BULK_RESPONSE_LIMIT
                else buffers.strains
            )
            response_rows = (
                buffers.output.tolist()
                if type(buffers.output) is np.ndarray
                and buffers.output.shape[0] <= _BULK_RESPONSE_LIMIT
                else buffers.output
            )
            responses = []
            for strain, parent, row in zip(
                response_strains, flat_parents, response_rows, strict=True
            ):
                yielded = bool(row[10])
                state = (
                    UniaxialPlasticityState(*map(float, row[6:10]))
                    if yielded
                    else parent
                )
                responses.append(
                    UniaxialPlasticityResponse(
                        total_strain=float(strain),
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
            return tuple(
                tuple(responses[start : start + count])
                for start in range(0, len(responses), count)
            )
        finally:
            self._workspace.lock.release()


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
