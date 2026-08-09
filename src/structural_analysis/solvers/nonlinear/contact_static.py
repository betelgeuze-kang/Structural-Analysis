"""Bounded frictionless unilateral-gap static contact solver."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import itertools
import math
from typing import Any, Sequence

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash


CONTACT_STATIC_PROFILE = "frictionless.unilateral-gap.active-set.v1"
CONTACT_STATIC_SCHEMA_VERSION = "contact-static-solution.v1"
CONTACT_CHECKPOINT_SCHEMA_VERSION = "contact-static-checkpoint.v1"
_ZERO_HASH = "sha256:" + "0" * 64


class ContactStaticError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContactStaticModel:
    model_id: str
    dof_ids: tuple[str, ...]
    contact_ids: tuple[str, ...]
    stiffness_n_per_m: tuple[tuple[float, ...], ...]
    load_n: tuple[float, ...]
    gap_upper_m: tuple[float, ...]

    def __init__(
        self,
        *,
        model_id: str,
        dof_ids: Sequence[str],
        contact_ids: Sequence[str],
        stiffness_n_per_m: Sequence[Sequence[float]],
        load_n: Sequence[float],
        gap_upper_m: Sequence[float],
    ) -> None:
        dofs = tuple(map(str, dof_ids))
        contacts = tuple(map(str, contact_ids))
        stiffness = np.asarray(stiffness_n_per_m, dtype=np.float64)
        load = np.asarray(load_n, dtype=np.float64)
        gap = np.asarray(gap_upper_m, dtype=np.float64)
        size = len(dofs)
        if (
            size < 1
            or len(set(dofs)) != size
            or len(contacts) != size
            or len(set(contacts)) != size
        ):
            raise ValueError("contact DOF/contact identity is invalid")
        if (
            stiffness.shape != (size, size)
            or not np.all(np.isfinite(stiffness))
            or not np.allclose(stiffness, stiffness.T, rtol=0.0, atol=1.0e-12)
        ):
            raise ValueError("contact stiffness must be finite and symmetric")
        if (
            load.shape != (size,)
            or gap.shape != (size,)
            or not np.all(np.isfinite(load))
            or not np.all(np.isfinite(gap))
        ):
            raise ValueError("contact load/gap vectors are invalid")
        try:
            np.linalg.cholesky(stiffness)
        except np.linalg.LinAlgError as exc:
            raise ValueError("contact stiffness must be positive definite") from exc
        object.__setattr__(self, "model_id", str(model_id))
        object.__setattr__(self, "dof_ids", dofs)
        object.__setattr__(self, "contact_ids", contacts)
        object.__setattr__(
            self, "stiffness_n_per_m", tuple(map(tuple, stiffness.tolist()))
        )
        object.__setattr__(self, "load_n", tuple(map(float, load)))
        object.__setattr__(self, "gap_upper_m", tuple(map(float, gap)))

    @property
    def model_hash(self) -> str:
        return canonical_hash(asdict(self) | {"profile": CONTACT_STATIC_PROFILE})


@dataclass(frozen=True)
class ContactStaticCheckpoint:
    schema_version: str
    profile: str
    model_hash: str
    stiffness_hash: str
    load_hash: str
    displacement_m: tuple[float, ...]
    contact_multiplier_n: tuple[float, ...]
    active_contact_ids: tuple[str, ...]
    checkpoint_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContactStaticSolution:
    schema_version: str
    profile: str
    model_hash: str
    stiffness_hash: str
    load_hash: str
    displacement_m: tuple[float, ...]
    contact_multiplier_n: tuple[float, ...]
    gap_remaining_m: tuple[float, ...]
    equilibrium_residual_n: tuple[float, ...]
    complementarity_n_m: tuple[float, ...]
    active_contact_ids: tuple[str, ...]
    active_set_trials: int
    maximum_equilibrium_residual_n: float
    maximum_penetration_m: float
    minimum_contact_multiplier_n: float
    maximum_complementarity_n_m: float
    strain_energy_j: float
    external_work_j: float
    checkpoint: ContactStaticCheckpoint
    result_hash: str
    fallback_used: bool
    regularization_used: bool
    contract_pass: bool


def solve_contact_static(
    model: ContactStaticModel, *, tolerance: float = 1.0e-10
) -> ContactStaticSolution:
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise ValueError("contact tolerance must be positive")
    stiffness = np.asarray(model.stiffness_n_per_m)
    load = np.asarray(model.load_n)
    gap = np.asarray(model.gap_upper_m)
    size = load.size
    feasible: list[tuple[tuple[bool, ...], np.ndarray, np.ndarray]] = []
    trials = 0
    for mask in itertools.product((False, True), repeat=size):
        trials += 1
        active = np.flatnonzero(mask)
        free = np.flatnonzero(np.logical_not(mask))
        displacement = np.zeros(size)
        multiplier = np.zeros(size)
        if active.size:
            displacement[active] = gap[active]
        if free.size:
            rhs = load[free] - (
                stiffness[np.ix_(free, active)] @ displacement[active]
                if active.size
                else 0.0
            )
            displacement[free] = np.linalg.solve(stiffness[np.ix_(free, free)], rhs)
        multiplier[active] = (
            load[active] - stiffness[np.ix_(active, np.arange(size))] @ displacement
        )
        remaining = gap - displacement
        scale_gap = max(
            float(np.max(np.abs(gap))), float(np.max(np.abs(displacement))), 1.0
        )
        scale_force = max(float(np.max(np.abs(load))), 1.0)
        if (
            float(np.min(remaining)) >= -tolerance * scale_gap
            and float(np.min(multiplier)) >= -tolerance * scale_force
        ):
            feasible.append((mask, displacement, multiplier))
    if not feasible:
        raise ContactStaticError("no feasible unilateral contact active set")
    mask, displacement, multiplier = min(feasible, key=lambda row: row[0])
    multiplier[
        np.abs(multiplier) <= tolerance * max(float(np.max(np.abs(load))), 1.0)
    ] = 0.0
    remaining = gap - displacement
    residual = stiffness @ displacement + multiplier - load
    complementarity = multiplier * remaining
    maximum_residual = float(np.max(np.abs(residual)))
    maximum_penetration = max(0.0, -float(np.min(remaining)))
    minimum_multiplier = float(np.min(multiplier))
    maximum_complementarity = float(np.max(np.abs(complementarity)))
    force_scale = max(float(np.max(np.abs(load))), 1.0)
    length_scale = max(
        float(np.max(np.abs(gap))), float(np.max(np.abs(displacement))), 1.0
    )
    contract_pass = bool(
        maximum_residual <= tolerance * force_scale
        and maximum_penetration <= tolerance * length_scale
        and minimum_multiplier >= -tolerance * force_scale
        and maximum_complementarity <= tolerance * force_scale * length_scale
    )
    if not contract_pass:
        raise ContactStaticError("contact KKT physical gate failed")
    stiffness_hash = canonical_hash(stiffness.tolist())
    load_hash = canonical_hash(load.tolist())
    active_ids = tuple(
        model.contact_ids[index] for index, value in enumerate(mask) if value
    )
    checkpoint0 = ContactStaticCheckpoint(
        CONTACT_CHECKPOINT_SCHEMA_VERSION,
        CONTACT_STATIC_PROFILE,
        model.model_hash,
        stiffness_hash,
        load_hash,
        tuple(map(float, displacement)),
        tuple(map(float, multiplier)),
        active_ids,
        _ZERO_HASH,
    )
    payload = checkpoint0.to_dict()
    payload.pop("checkpoint_hash")
    checkpoint = replace(checkpoint0, checkpoint_hash=canonical_hash(payload))
    provisional = ContactStaticSolution(
        CONTACT_STATIC_SCHEMA_VERSION,
        CONTACT_STATIC_PROFILE,
        model.model_hash,
        stiffness_hash,
        load_hash,
        tuple(map(float, displacement)),
        tuple(map(float, multiplier)),
        tuple(map(float, remaining)),
        tuple(map(float, residual)),
        tuple(map(float, complementarity)),
        active_ids,
        trials,
        maximum_residual,
        maximum_penetration,
        minimum_multiplier,
        maximum_complementarity,
        0.5 * float(displacement @ stiffness @ displacement),
        float(displacement @ load),
        checkpoint,
        _ZERO_HASH,
        False,
        False,
        contract_pass,
    )
    result_payload = asdict(provisional)
    result_payload.pop("result_hash")
    return replace(provisional, result_hash=canonical_hash(result_payload))


def resume_contact_static(
    model: ContactStaticModel, checkpoint: ContactStaticCheckpoint
) -> ContactStaticSolution:
    if (
        checkpoint.schema_version != CONTACT_CHECKPOINT_SCHEMA_VERSION
        or checkpoint.profile != CONTACT_STATIC_PROFILE
        or checkpoint.model_hash != model.model_hash
    ):
        raise ContactStaticError("contact checkpoint binding mismatch")
    payload = checkpoint.to_dict()
    claimed = payload.pop("checkpoint_hash")
    if canonical_hash(payload) != claimed:
        raise ContactStaticError("contact checkpoint hash mismatch")
    replay = solve_contact_static(model)
    if replay.checkpoint != checkpoint:
        raise ContactStaticError("contact checkpoint exact replay mismatch")
    return replay


__all__ = [
    "CONTACT_CHECKPOINT_SCHEMA_VERSION",
    "CONTACT_STATIC_PROFILE",
    "CONTACT_STATIC_SCHEMA_VERSION",
    "ContactStaticCheckpoint",
    "ContactStaticError",
    "ContactStaticModel",
    "ContactStaticSolution",
    "resume_contact_static",
    "solve_contact_static",
]
