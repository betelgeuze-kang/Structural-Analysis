"""Stateful translational links coupled to a corotational 2D fiber frame.

The existing frame checkpoint remains unchanged.  This bounded coupling layer
nests that checkpoint with one immutable state per scalar force-deformation
link and commits both state families atomically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import struct
from typing import Any, Iterable, Literal

import numpy as np

from structural_analysis.assembly.stateful_corotational_fiber_frame2d import (
    StatefulCorotationalFiberFrame2DAssembly,
    StatefulCorotationalFiberFrame2DProblem,
    assemble_stateful_corotational_fiber_frame2d,
    initial_stateful_corotational_fiber_frame2d_checkpoint,
    validate_stateful_corotational_fiber_frame2d_checkpoint,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_state import (
    StatefulCorotationalFiberFrame2DCheckpoint,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.bilinear_link import (
    BilinearCombinedHardeningLink,
    BilinearLinkResponse,
    BilinearLinkState,
)
from structural_analysis.solvers.nonlinear.newton import (
    NO_SOLVE_REACTION_ONLY_DISPOSITION,
    RESIDUAL_FORMULA,
    RESIDUAL_FORMULA_HASH,
    SOLVE_FREE_EQUATIONS_DISPOSITION,
    NewtonRaphsonConfig,
    NewtonRaphsonVectorSolution,
    newton_raphson_vector,
)


STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-link-coupling.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-link-checkpoint.v1"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY = (
    "f_internal=f_frame+sum(scatter_link([-force,+force]));"
    "K_material=K_frame_material+sum(scatter_link([[k,-k],[-k,k]]));"
    "K_consistent=K_material+K_frame_geometric"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY = (
    "This coupling supports one or more global-axis scalar translational "
    "force-deformation links between planar frame nodes. It does not provide "
    "rotational or multi-axis coupling, local-axis transformations, gap/contact, "
    "friction, uplift, damping, rate effects, degradation or pinching, shells, "
    "three-dimensional frames, production sparse execution, ROCm/HIP parity, "
    "full-building equilibrium, G1 closure, or commercial-readiness evidence."
)
_CHECKPOINT_HASH_DOMAIN = (
    b"structural-analysis/stateful-corotational-fiber-frame2d-link-checkpoint/v1\0"
)


def _finite(value: Any, *, name: str) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _sha256_hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _readonly(values: Any, *, shape: tuple[int, ...], name: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite array with shape {shape}") from exc
    if array.shape != shape or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a finite array with shape {shape}")
    result = np.array(array, dtype=np.float64, copy=True, order="C")
    result.setflags(write=False)
    return result


def _exact_float64_equal(left: Any, right: Any) -> bool:
    left_array = np.ascontiguousarray(left, dtype="<f8")
    right_array = np.ascontiguousarray(right, dtype="<f8")
    return left_array.shape == right_array.shape and (
        left_array.tobytes(order="C") == right_array.tobytes(order="C")
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLink:
    """One scalar global-axis translational link between two frame nodes."""

    link_id: str
    node_i: int
    node_j: int
    component: Literal["ux", "uy"]
    material: BilinearCombinedHardeningLink

    def __post_init__(self) -> None:
        normalized_id = str(self.link_id).strip()
        if not normalized_id:
            raise ValueError("link_id must be non-empty")
        object.__setattr__(self, "link_id", normalized_id)
        if (
            type(self.node_i) is not int
            or type(self.node_j) is not int
            or self.node_i < 0
            or self.node_j < 0
            or self.node_i == self.node_j
        ):
            raise ValueError("link node indices must be distinct and non-negative")
        if self.component not in ("ux", "uy"):
            raise ValueError("link component must be 'ux' or 'uy'")
        if type(self.material) is not BilinearCombinedHardeningLink:
            raise ValueError("link material must be a BilinearCombinedHardeningLink")

    @property
    def component_offset(self) -> int:
        return 0 if self.component == "ux" else 1

    def global_dofs(self) -> tuple[int, int]:
        offset = self.component_offset
        return 3 * self.node_i + offset, 3 * self.node_j + offset

    def contract_payload(self) -> dict[str, Any]:
        material = self.material
        return {
            "link_id": self.link_id,
            "node_i": self.node_i,
            "node_j": self.node_j,
            "component": self.component,
            "material": {
                "material_id": material.material_id,
                "initial_stiffness_kn_per_m": material.initial_stiffness_kn_per_m,
                "yield_force_kn": material.yield_force_kn,
                "isotropic_hardening_kn_per_m": (material.isotropic_hardening_kn_per_m),
                "kinematic_hardening_kn_per_m": (material.kinematic_hardening_kn_per_m),
                "yield_tolerance_kn": material.yield_tolerance_kn,
            },
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkProblem:
    """A pre-existing corotational frame plus scalar translational links."""

    case_id: str
    frame_problem: StatefulCorotationalFiberFrame2DProblem
    links: tuple[StatefulCorotationalFiberFrame2DLink, ...]

    def __post_init__(self) -> None:
        normalized_id = str(self.case_id).strip()
        if not normalized_id:
            raise ValueError("case_id must be non-empty")
        object.__setattr__(self, "case_id", normalized_id)
        if type(self.frame_problem) is not StatefulCorotationalFiberFrame2DProblem:
            raise ValueError(
                "frame_problem must be a StatefulCorotationalFiberFrame2DProblem"
            )
        if (
            not isinstance(self.links, tuple)
            or not self.links
            or not all(
                type(link) is StatefulCorotationalFiberFrame2DLink
                for link in self.links
            )
        ):
            raise ValueError("links must be a non-empty tuple of link definitions")
        node_count = len(self.frame_problem.node_coordinates_m)
        fixed = set(self.frame_problem.fixed_global_dofs)
        link_ids: set[str] = set()
        endpoint_pairs: set[tuple[int, int]] = set()
        for link in self.links:
            if link.link_id in link_ids:
                raise ValueError("link_id values must be unique")
            link_ids.add(link.link_id)
            if link.node_i >= node_count or link.node_j >= node_count:
                raise ValueError("link node index is out of range")
            dofs = link.global_dofs()
            if dofs in endpoint_pairs or tuple(reversed(dofs)) in endpoint_pairs:
                raise ValueError("duplicate link endpoint/component pair")
            endpoint_pairs.add(dofs)
            if all(dof in fixed for dof in dofs):
                raise ValueError("each link must connect at least one free global DOF")
        member_ids = {member.member_id for member in self.frame_problem.members}
        if member_ids.intersection(link_ids):
            raise ValueError("link_id values must not collide with frame member IDs")

    @property
    def global_dof_count(self) -> int:
        return self.frame_problem.global_dof_count

    @property
    def free_global_dofs(self) -> tuple[int, ...]:
        return self.frame_problem.free_global_dofs

    @property
    def fixed_global_dofs(self) -> tuple[int, ...]:
        return self.frame_problem.fixed_global_dofs

    @property
    def physical_coordinate_scale(self) -> np.ndarray:
        return self.frame_problem.physical_coordinate_scale

    def reference_force_scale(self) -> float:
        return self.frame_problem.reference_force_scale()

    @property
    def contract_hash(self) -> str:
        return canonical_hash(
            {
                "schema_version": (
                    STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION
                ),
                "case_id": self.case_id,
                "frame_problem_contract_hash": self.frame_problem.contract_hash,
                "links": [link.contract_payload() for link in self.links],
                "assembly": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY,
                "residual_formula": RESIDUAL_FORMULA,
            }
        )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkCheckpoint:
    """One accepted atomic frame-plus-link state."""

    case_id: str
    problem_contract_hash: str
    epoch: int
    step_index: int
    load_factor: float
    parent_state_hash: str | None
    frame_checkpoint: StatefulCorotationalFiberFrame2DCheckpoint
    link_states: tuple[BilinearLinkState, ...]
    role: Literal["committed"] = "committed"
    state_hash: str = ""

    def __post_init__(self) -> None:
        normalized_id = str(self.case_id).strip()
        if not normalized_id:
            raise ValueError("case_id must be non-empty")
        object.__setattr__(self, "case_id", normalized_id)
        object.__setattr__(
            self,
            "problem_contract_hash",
            _sha256_hash(
                self.problem_contract_hash,
                name="problem_contract_hash",
            ),
        )
        if type(self.epoch) is not int or self.epoch < 0:
            raise ValueError("epoch must be a non-negative integer")
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        if self.epoch != self.step_index:
            raise ValueError("epoch and step_index must advance together")
        object.__setattr__(
            self,
            "load_factor",
            _finite(self.load_factor, name="load_factor"),
        )
        if self.role != "committed":
            raise ValueError("role must be 'committed'")
        if self.epoch == 0:
            if self.parent_state_hash is not None:
                raise ValueError("epoch-zero checkpoint cannot have a parent hash")
        elif self.parent_state_hash is None:
            raise ValueError("positive-epoch checkpoint must have a parent hash")
        else:
            object.__setattr__(
                self,
                "parent_state_hash",
                _sha256_hash(self.parent_state_hash, name="parent_state_hash"),
            )
        if (
            type(self.frame_checkpoint)
            is not StatefulCorotationalFiberFrame2DCheckpoint
        ):
            raise ValueError("frame_checkpoint type is invalid")
        if (
            not isinstance(self.link_states, tuple)
            or not self.link_states
            or not all(type(state) is BilinearLinkState for state in self.link_states)
        ):
            raise ValueError("link_states must be a non-empty tuple of link states")
        if (
            self.frame_checkpoint.epoch != self.epoch
            or self.frame_checkpoint.step_index != self.step_index
            or self.frame_checkpoint.load_factor != self.load_factor
        ):
            raise ValueError("nested frame checkpoint progression does not match")
        computed = self.compute_state_hash()
        if self.state_hash:
            normalized_hash = _sha256_hash(self.state_hash, name="state_hash")
            if normalized_hash != computed:
                raise ValueError("checkpoint state_hash does not match canonical bytes")
            object.__setattr__(self, "state_hash", normalized_hash)
        else:
            object.__setattr__(self, "state_hash", computed)
        if self.parent_state_hash == self.state_hash:
            raise ValueError("checkpoint cannot be its own parent")

    @property
    def global_displacements(self) -> tuple[float, ...]:
        return self.frame_checkpoint.global_displacements

    @property
    def element_states(self) -> tuple[Any, ...]:
        return self.frame_checkpoint.element_states

    def canonical_bytes(self) -> bytes:
        parent = "" if self.parent_state_hash is None else self.parent_state_hash
        frame_bytes = self.frame_checkpoint.canonical_bytes()
        chunks = [
            _CHECKPOINT_HASH_DOMAIN,
            _pack_text(self.role),
            _pack_text(self.case_id),
            _pack_text(self.problem_contract_hash),
            struct.pack("<QQd", self.epoch, self.step_index, self.load_factor),
            _pack_text(parent),
            struct.pack("<Q", len(frame_bytes)),
            frame_bytes,
            struct.pack("<Q", len(self.link_states)),
        ]
        for state in self.link_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    def compute_state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": (
                STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION
            ),
            "role": self.role,
            "case_id": self.case_id,
            "problem_contract_hash": self.problem_contract_hash,
            "epoch": self.epoch,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "parent_state_hash": self.parent_state_hash,
            "frame_checkpoint": self.frame_checkpoint.to_dict(),
            "link_states": [state.to_dict() for state in self.link_states],
            "state_hash": self.state_hash,
        }


def validate_stateful_corotational_fiber_frame2d_link_checkpoint(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
    checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint,
) -> None:
    if type(checkpoint) is not StatefulCorotationalFiberFrame2DLinkCheckpoint:
        raise ValueError("checkpoint type is invalid")
    if checkpoint.case_id != problem.case_id:
        raise ValueError("checkpoint case_id does not match problem")
    if checkpoint.problem_contract_hash != problem.contract_hash:
        raise ValueError("checkpoint problem contract does not match")
    if checkpoint.compute_state_hash() != checkpoint.state_hash:
        raise ValueError("checkpoint state hash validation failed")
    if len(checkpoint.link_states) != len(problem.links):
        raise ValueError("checkpoint link-state count does not match problem")
    validate_stateful_corotational_fiber_frame2d_checkpoint(
        problem.frame_problem,
        checkpoint.frame_checkpoint,
    )
    displacements = np.asarray(checkpoint.global_displacements, dtype=np.float64)
    for link, state in zip(problem.links, checkpoint.link_states, strict=True):
        dof_i, dof_j = link.global_dofs()
        deformation = float(displacements[dof_j] - displacements[dof_i])
        repeated = link.material.integrate(deformation, state)
        if repeated.state.canonical_bytes() != state.canonical_bytes():
            raise ValueError(
                "committed link state is not stable at checkpoint deformation"
            )
    if checkpoint.epoch == 0:
        if checkpoint.load_factor != 0.0:
            raise ValueError("epoch-zero checkpoint must have zero load factor")
        for link, state in zip(problem.links, checkpoint.link_states, strict=True):
            if (
                state.canonical_bytes()
                != link.material.initial_state().canonical_bytes()
            ):
                raise ValueError("epoch-zero link state must be initial")


def initial_stateful_corotational_fiber_frame2d_link_checkpoint(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
) -> StatefulCorotationalFiberFrame2DLinkCheckpoint:
    checkpoint = StatefulCorotationalFiberFrame2DLinkCheckpoint(
        case_id=problem.case_id,
        problem_contract_hash=problem.contract_hash,
        epoch=0,
        step_index=0,
        load_factor=0.0,
        parent_state_hash=None,
        frame_checkpoint=initial_stateful_corotational_fiber_frame2d_checkpoint(
            problem.frame_problem
        ),
        link_states=tuple(link.material.initial_state() for link in problem.links),
    )
    validate_stateful_corotational_fiber_frame2d_link_checkpoint(problem, checkpoint)
    return checkpoint


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkAssemblyRow:
    link_id: str
    global_dofs: tuple[int, int]
    deformation_m: float
    internal_load_global_kn: np.ndarray
    tangent_global_kn_per_m: np.ndarray
    response: BilinearLinkResponse

    def __post_init__(self) -> None:
        normalized_id = str(self.link_id).strip()
        if not normalized_id:
            raise ValueError("link_id must be non-empty")
        object.__setattr__(self, "link_id", normalized_id)
        if (
            not isinstance(self.global_dofs, tuple)
            or len(self.global_dofs) != 2
            or self.global_dofs[0] == self.global_dofs[1]
            or any(type(dof) is not int or dof < 0 for dof in self.global_dofs)
        ):
            raise ValueError("global_dofs must contain two distinct non-negative DOFs")
        object.__setattr__(
            self,
            "deformation_m",
            _finite(self.deformation_m, name="deformation_m"),
        )
        if type(self.response) is not BilinearLinkResponse:
            raise ValueError("response type is invalid")
        if self.deformation_m != self.response.deformation_m:
            raise ValueError("link deformation does not match response")
        object.__setattr__(
            self,
            "internal_load_global_kn",
            _readonly(
                self.internal_load_global_kn,
                shape=(2,),
                name="internal_load_global_kn",
            ),
        )
        object.__setattr__(
            self,
            "tangent_global_kn_per_m",
            _readonly(
                self.tangent_global_kn_per_m,
                shape=(2, 2),
                name="tangent_global_kn_per_m",
            ),
        )
        expected_force = np.array(
            [-self.response.force_kn, self.response.force_kn],
            dtype=np.float64,
        )
        expected_tangent = self.response.consistent_tangent_kn_per_m * np.array(
            [[1.0, -1.0], [-1.0, 1.0]],
            dtype=np.float64,
        )
        if not _exact_float64_equal(self.internal_load_global_kn, expected_force):
            raise ValueError("link internal load does not match response")
        if not _exact_float64_equal(self.tangent_global_kn_per_m, expected_tangent):
            raise ValueError("link tangent does not match response")

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "global_dofs": list(self.global_dofs),
            "deformation_m": self.deformation_m,
            "internal_load_global_kn": self.internal_load_global_kn.tolist(),
            "tangent_global_kn_per_m": self.tangent_global_kn_per_m.tolist(),
            "response": self.response.to_dict(),
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkAssembly:
    parent_checkpoint_hash: str
    target_load_factor: float
    free_global_dofs: tuple[int, ...]
    generalized_coordinates_m: np.ndarray
    global_displacements: np.ndarray
    residual_kn: np.ndarray
    jacobian_kn_per_m: np.ndarray
    internal_loads_global: np.ndarray
    external_loads_global: np.ndarray
    reactions_global: np.ndarray
    frame_material_tangent_global: np.ndarray
    link_material_tangent_global: np.ndarray
    material_tangent_global: np.ndarray
    geometric_tangent_global: np.ndarray
    consistent_tangent_global: np.ndarray
    frame_assembly: StatefulCorotationalFiberFrame2DAssembly
    link_assemblies: tuple[StatefulCorotationalFiberFrame2DLinkAssemblyRow, ...]
    trial_link_states: tuple[BilinearLinkState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parent_checkpoint_hash",
            _sha256_hash(
                self.parent_checkpoint_hash,
                name="parent_checkpoint_hash",
            ),
        )
        object.__setattr__(
            self,
            "target_load_factor",
            _finite(self.target_load_factor, name="target_load_factor"),
        )
        if type(self.frame_assembly) is not StatefulCorotationalFiberFrame2DAssembly:
            raise ValueError("frame_assembly type is invalid")
        try:
            global_count = int(np.asarray(self.global_displacements).shape[0])
        except (IndexError, TypeError) as exc:
            raise ValueError("global_displacements must be a finite vector") from exc
        if global_count == 0 or global_count % 3 != 0:
            raise ValueError("global_displacements must contain complete 3-DOF nodes")
        if (
            not isinstance(self.free_global_dofs, tuple)
            or len(set(self.free_global_dofs)) != len(self.free_global_dofs)
            or any(type(dof) is not int or dof < 0 for dof in self.free_global_dofs)
            or self.free_global_dofs != tuple(sorted(self.free_global_dofs))
        ):
            raise ValueError(
                "free_global_dofs must be sorted distinct non-negative integers"
            )
        if self.free_global_dofs and max(self.free_global_dofs) >= global_count:
            raise ValueError("free global DOF is out of range")
        free_count = len(self.free_global_dofs)
        arrays = (
            ("generalized_coordinates_m", (global_count,)),
            ("global_displacements", (global_count,)),
            ("residual_kn", (free_count,)),
            ("jacobian_kn_per_m", (free_count, free_count)),
            ("internal_loads_global", (global_count,)),
            ("external_loads_global", (global_count,)),
            ("reactions_global", (global_count,)),
            ("frame_material_tangent_global", (global_count, global_count)),
            ("link_material_tangent_global", (global_count, global_count)),
            ("material_tangent_global", (global_count, global_count)),
            ("geometric_tangent_global", (global_count, global_count)),
            ("consistent_tangent_global", (global_count, global_count)),
        )
        for name, shape in arrays:
            object.__setattr__(
                self,
                name,
                _readonly(getattr(self, name), shape=shape, name=name),
            )
        if not np.allclose(
            self.material_tangent_global,
            self.frame_material_tangent_global + self.link_material_tangent_global,
            rtol=1.0e-13,
            atol=1.0e-10,
        ):
            raise ValueError("material tangent does not equal frame plus link terms")
        if not np.allclose(
            self.consistent_tangent_global,
            self.material_tangent_global + self.geometric_tangent_global,
            rtol=1.0e-13,
            atol=1.0e-10,
        ):
            raise ValueError("consistent tangent decomposition is invalid")
        if (
            not isinstance(self.link_assemblies, tuple)
            or not self.link_assemblies
            or not all(
                type(row) is StatefulCorotationalFiberFrame2DLinkAssemblyRow
                for row in self.link_assemblies
            )
        ):
            raise ValueError("link_assemblies contains an invalid row")
        if (
            not isinstance(self.trial_link_states, tuple)
            or len(self.trial_link_states) != len(self.link_assemblies)
            or not all(
                type(state) is BilinearLinkState for state in self.trial_link_states
            )
        ):
            raise ValueError("trial_link_states does not match link assemblies")
        for row, state in zip(
            self.link_assemblies,
            self.trial_link_states,
            strict=True,
        ):
            if row.response.state.canonical_bytes() != state.canonical_bytes():
                raise ValueError("trial link state does not match response")

    @property
    def member_assemblies(self) -> tuple[Any, ...]:
        return self.frame_assembly.member_assemblies

    @property
    def trial_element_states(self) -> tuple[Any, ...]:
        return self.frame_assembly.trial_element_states

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION,
            "residual_formula": RESIDUAL_FORMULA,
            "parent_checkpoint_hash": self.parent_checkpoint_hash,
            "target_load_factor": self.target_load_factor,
            "free_global_dofs": list(self.free_global_dofs),
            "generalized_coordinates_m": self.generalized_coordinates_m.tolist(),
            "global_displacements": self.global_displacements.tolist(),
            "residual_kn": self.residual_kn.tolist(),
            "jacobian_kn_per_m": self.jacobian_kn_per_m.tolist(),
            "internal_loads_global": self.internal_loads_global.tolist(),
            "external_loads_global": self.external_loads_global.tolist(),
            "reactions_global": self.reactions_global.tolist(),
            "frame_material_tangent_global": (
                self.frame_material_tangent_global.tolist()
            ),
            "link_material_tangent_global": self.link_material_tangent_global.tolist(),
            "material_tangent_global": self.material_tangent_global.tolist(),
            "geometric_tangent_global": self.geometric_tangent_global.tolist(),
            "consistent_tangent_global": self.consistent_tangent_global.tolist(),
            "frame_assembly": self.frame_assembly.to_dict(),
            "link_assemblies": [row.to_dict() for row in self.link_assemblies],
            "trial_link_state_hashes": [
                state.state_hash for state in self.trial_link_states
            ],
        }


def assemble_stateful_corotational_fiber_frame2d_links(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
) -> StatefulCorotationalFiberFrame2DLinkAssembly:
    """Assemble frame members and link terms from one immutable parent."""

    validate_stateful_corotational_fiber_frame2d_link_checkpoint(
        problem,
        accepted_checkpoint,
    )
    load_factor = _finite(target_load_factor, name="target_load_factor")
    frame = assemble_stateful_corotational_fiber_frame2d(
        problem.frame_problem,
        accepted_checkpoint.frame_checkpoint,
        target_load_factor=load_factor,
        trial_free_coordinates_m=trial_free_coordinates_m,
    )
    internal = np.array(frame.internal_loads_global, dtype=np.float64, copy=True)
    frame_material = np.array(
        frame.material_tangent_global,
        dtype=np.float64,
        copy=True,
    )
    link_material = np.zeros_like(frame_material)
    link_rows: list[StatefulCorotationalFiberFrame2DLinkAssemblyRow] = []
    trial_link_states: list[BilinearLinkState] = []
    for link, parent in zip(
        problem.links,
        accepted_checkpoint.link_states,
        strict=True,
    ):
        dofs = link.global_dofs()
        deformation = float(
            frame.global_displacements[dofs[1]] - frame.global_displacements[dofs[0]]
        )
        response = link.material.integrate(deformation, parent)
        local_force = np.array(
            [-response.force_kn, response.force_kn], dtype=np.float64
        )
        local_tangent = response.consistent_tangent_kn_per_m * np.array(
            [[1.0, -1.0], [-1.0, 1.0]],
            dtype=np.float64,
        )
        internal[list(dofs)] += local_force
        link_material[np.ix_(dofs, dofs)] += local_tangent
        link_rows.append(
            StatefulCorotationalFiberFrame2DLinkAssemblyRow(
                link_id=link.link_id,
                global_dofs=dofs,
                deformation_m=deformation,
                internal_load_global_kn=local_force,
                tangent_global_kn_per_m=local_tangent,
                response=response,
            )
        )
        trial_link_states.append(response.state)

    material = frame_material + link_material
    geometric = np.array(frame.geometric_tangent_global, dtype=np.float64, copy=True)
    consistent = material + geometric
    external = np.array(frame.external_loads_global, dtype=np.float64, copy=True)
    physical_residual = internal - external
    free_dofs = problem.free_global_dofs
    scale = problem.physical_coordinate_scale
    free_scale = scale[list(free_dofs)]
    residual = free_scale * physical_residual[list(free_dofs)]
    jacobian = (
        free_scale[:, None]
        * consistent[np.ix_(free_dofs, free_dofs)]
        * free_scale[None, :]
    )
    reactions = np.zeros(problem.global_dof_count, dtype=np.float64)
    reactions[list(problem.fixed_global_dofs)] = physical_residual[
        list(problem.fixed_global_dofs)
    ]
    return StatefulCorotationalFiberFrame2DLinkAssembly(
        parent_checkpoint_hash=accepted_checkpoint.state_hash,
        target_load_factor=load_factor,
        free_global_dofs=free_dofs,
        generalized_coordinates_m=frame.generalized_coordinates_m,
        global_displacements=frame.global_displacements,
        residual_kn=residual,
        jacobian_kn_per_m=jacobian,
        internal_loads_global=internal,
        external_loads_global=external,
        reactions_global=reactions,
        frame_material_tangent_global=frame_material,
        link_material_tangent_global=link_material,
        material_tangent_global=material,
        geometric_tangent_global=geometric,
        consistent_tangent_global=consistent,
        frame_assembly=frame,
        link_assemblies=tuple(link_rows),
        trial_link_states=tuple(trial_link_states),
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkLoadStepAdapter:
    problem: StatefulCorotationalFiberFrame2DLinkProblem
    accepted_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint
    target_load_factor: float

    @property
    def case_id(self) -> str:
        return f"{self.problem.case_id}@load={self.target_load_factor:.12g}"

    def reference_force_scale(self) -> float:
        return self.problem.reference_force_scale()

    def initial_free_displacements_m(self) -> np.ndarray:
        scale = self.problem.physical_coordinate_scale
        global_displacements = np.asarray(
            self.accepted_checkpoint.global_displacements,
            dtype=np.float64,
        )
        generalized = global_displacements / scale
        return generalized[list(self.problem.free_global_dofs)].copy()

    def assemble(
        self,
        free_displacements_m: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        assembly = assemble_stateful_corotational_fiber_frame2d_links(
            self.problem,
            self.accepted_checkpoint,
            target_load_factor=self.target_load_factor,
            trial_free_coordinates_m=free_displacements_m,
        )
        return assembly.residual_kn, assembly.jacobian_kn_per_m


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkLoadStepResult:
    status: str
    committed: bool
    parent_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint
    accepted_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint
    trial_solution: NewtonRaphsonVectorSolution
    trial_assembly: StatefulCorotationalFiberFrame2DLinkAssembly
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "committed": self.committed,
            "parent_checkpoint": self.parent_checkpoint.to_dict(),
            "accepted_checkpoint": self.accepted_checkpoint.to_dict(),
            "trial_solution": {
                "status": self.trial_solution.status,
                "metrics": self.trial_solution.metrics,
                "convergence_history": self.trial_solution.convergence_history,
                "line_search_history": self.trial_solution.line_search_history,
                "unsupported_features": self.trial_solution.unsupported_features,
            },
            "trial_assembly": self.trial_assembly.to_dict(),
            "metrics": dict(self.metrics),
        }


def _assembly_parent_binding(
    assembly: StatefulCorotationalFiberFrame2DLinkAssembly,
    checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint,
) -> bool:
    return bool(
        assembly.parent_checkpoint_hash == checkpoint.state_hash
        and assembly.frame_assembly.parent_checkpoint_hash
        == checkpoint.frame_checkpoint.state_hash
        and all(
            row.response.parent_state_hash == parent.state_hash
            for row, parent in zip(
                assembly.member_assemblies,
                checkpoint.element_states,
                strict=True,
            )
        )
        and all(
            row.response.committed_state_hash == parent.state_hash
            for row, parent in zip(
                assembly.link_assemblies,
                checkpoint.link_states,
                strict=True,
            )
        )
    )


def solve_stateful_corotational_fiber_frame2d_link_load_step(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint,
    *,
    target_load_factor: float,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulCorotationalFiberFrame2DLinkLoadStepResult:
    """Solve one load target and atomically commit frame and link states."""

    validate_stateful_corotational_fiber_frame2d_link_checkpoint(
        problem,
        accepted_checkpoint,
    )
    parent_bytes = accepted_checkpoint.canonical_bytes()
    load_factor = _finite(target_load_factor, name="target_load_factor")
    adapter = StatefulCorotationalFiberFrame2DLinkLoadStepAdapter(
        problem=problem,
        accepted_checkpoint=accepted_checkpoint,
        target_load_factor=load_factor,
    )
    solution = newton_raphson_vector(
        adapter,
        config=config or NewtonRaphsonConfig(),
    )
    trial_assembly = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        accepted_checkpoint,
        target_load_factor=load_factor,
        trial_free_coordinates_m=solution.free_displacements_m,
    )
    no_solve_reaction_only = bool(
        solution.metrics.get("terminal_disposition")
        == NO_SOLVE_REACTION_ONLY_DISPOSITION
        and solution.metrics.get("solver_executed") is False
        and solution.metrics.get("active_equation_count") == 0
        and solution.metrics.get("assembly_contract_valid") is True
        and solution.metrics.get("convergence_claim") is False
    )
    iterative_solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and solution.metrics.get("active_equation_count")
        == len(problem.free_global_dofs)
        and solution.metrics.get("residual_gate_passed") is True
        and solution.metrics.get("increment_gate_passed") is True
        and solution.metrics.get("regularization_used") is False
        and solution.metrics.get("fallback_used") is False
    )
    parent_binding = _assembly_parent_binding(trial_assembly, accepted_checkpoint)
    solver_assembly_binding = bool(
        _exact_float64_equal(
            solution.free_displacements_m,
            trial_assembly.generalized_coordinates_m[list(problem.free_global_dofs)],
        )
        and _exact_float64_equal(
            solution.metrics.get("residual_kn", ()),
            trial_assembly.residual_kn,
        )
    )
    parent_immutable = bool(
        accepted_checkpoint.canonical_bytes() == parent_bytes
        and accepted_checkpoint.compute_state_hash() == accepted_checkpoint.state_hash
    )
    solver_contract = bool(
        solution.status == "ready"
        and solution.metrics.get("contract_pass") is True
        and (no_solve_reaction_only or iterative_solver_contract)
        and parent_binding
        and solver_assembly_binding
        and parent_immutable
    )
    if solver_contract:
        next_frame_checkpoint = StatefulCorotationalFiberFrame2DCheckpoint(
            case_id=problem.frame_problem.case_id,
            problem_contract_hash=problem.frame_problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=load_factor,
            parent_state_hash=accepted_checkpoint.frame_checkpoint.state_hash,
            global_displacements=tuple(
                float(value) for value in trial_assembly.global_displacements
            ),
            element_states=trial_assembly.trial_element_states,
        )
        next_checkpoint = StatefulCorotationalFiberFrame2DLinkCheckpoint(
            case_id=problem.case_id,
            problem_contract_hash=problem.contract_hash,
            epoch=accepted_checkpoint.epoch + 1,
            step_index=accepted_checkpoint.step_index + 1,
            load_factor=load_factor,
            parent_state_hash=accepted_checkpoint.state_hash,
            frame_checkpoint=next_frame_checkpoint,
            link_states=trial_assembly.trial_link_states,
        )
        validate_stateful_corotational_fiber_frame2d_link_checkpoint(
            problem,
            next_checkpoint,
        )
        committed = True
        rollback_exact: bool | None = None
    else:
        next_checkpoint = accepted_checkpoint
        committed = False
        rollback_exact = bool(
            next_checkpoint is accepted_checkpoint
            and next_checkpoint.state_hash == accepted_checkpoint.state_hash
            and next_checkpoint.canonical_bytes() == parent_bytes
        )
    return StatefulCorotationalFiberFrame2DLinkLoadStepResult(
        status="ready" if committed else "blocked",
        committed=committed,
        parent_checkpoint=accepted_checkpoint,
        accepted_checkpoint=next_checkpoint,
        trial_solution=solution,
        trial_assembly=trial_assembly,
        metrics={
            "residual_formula": RESIDUAL_FORMULA,
            "residual_formula_hash": RESIDUAL_FORMULA_HASH,
            "tangent_definition": "frame_material_plus_link_material_plus_geometric",
            "target_load_factor": load_factor,
            "parent_checkpoint_hash": accepted_checkpoint.state_hash,
            "parent_epoch": accepted_checkpoint.epoch,
            "accepted_checkpoint_hash_after": next_checkpoint.state_hash,
            "accepted_epoch_after": next_checkpoint.epoch,
            "trial_parent_checkpoint_hash": trial_assembly.parent_checkpoint_hash,
            "frame_and_link_parent_binding_passed": parent_binding,
            "solver_assembly_coordinate_residual_binding_passed": (
                solver_assembly_binding
            ),
            "parent_checkpoint_immutable": parent_immutable,
            "solver_contract_pass": solver_contract,
            "iterative_solver_contract_pass": iterative_solver_contract,
            "no_solve_contract_pass": no_solve_reaction_only,
            "terminal_disposition": solution.metrics.get(
                "terminal_disposition",
                SOLVE_FREE_EQUATIONS_DISPOSITION,
            ),
            "terminal_reason": solution.metrics.get("terminal_reason"),
            "residual_gate_passed": solution.metrics.get("residual_gate_passed"),
            "increment_gate_passed": solution.metrics.get("increment_gate_passed"),
            "regularization_used": bool(solution.metrics.get("regularization_used")),
            "fallback_used": bool(solution.metrics.get("fallback_used")),
            "committed": committed,
            "rollback_exact": rollback_exact,
            "yielded_link_count": sum(
                int(row.response.yielded) for row in trial_assembly.link_assemblies
            ),
            "yielded_member_count": sum(
                int(row.response.yielded_integration_point_count > 0)
                for row in trial_assembly.member_assemblies
            ),
            "damaged_member_count": sum(
                int(row.response.damaged_integration_point_count > 0)
                for row in trial_assembly.member_assemblies
            ),
        },
    )


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkLoadPathResult:
    status: str
    initial_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint
    final_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint
    steps: tuple[StatefulCorotationalFiberFrame2DLinkLoadStepResult, ...] = field(
        default_factory=tuple
    )

    @property
    def contract_pass(self) -> bool:
        return bool(self.steps and all(step.committed for step in self.steps))

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract_pass": self.contract_pass,
            "initial_checkpoint": self.initial_checkpoint.to_dict(),
            "final_checkpoint": self.final_checkpoint.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
        }


def run_stateful_corotational_fiber_frame2d_link_load_path(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
    load_factors: Iterable[float],
    *,
    initial_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint | None = None,
    config: NewtonRaphsonConfig | None = None,
) -> StatefulCorotationalFiberFrame2DLinkLoadPathResult:
    factors = tuple(_finite(value, name="load_factor") for value in load_factors)
    if not factors:
        raise ValueError("load_factors must be non-empty")
    first = initial_checkpoint or (
        initial_stateful_corotational_fiber_frame2d_link_checkpoint(problem)
    )
    validate_stateful_corotational_fiber_frame2d_link_checkpoint(problem, first)
    accepted = first
    rows: list[StatefulCorotationalFiberFrame2DLinkLoadStepResult] = []
    for factor in factors:
        step = solve_stateful_corotational_fiber_frame2d_link_load_step(
            problem,
            accepted,
            target_load_factor=factor,
            config=config,
        )
        rows.append(step)
        if not step.committed:
            return StatefulCorotationalFiberFrame2DLinkLoadPathResult(
                status="blocked",
                initial_checkpoint=first,
                final_checkpoint=accepted,
                steps=tuple(rows),
            )
        accepted = step.accepted_checkpoint
    return StatefulCorotationalFiberFrame2DLinkLoadPathResult(
        status="ready",
        initial_checkpoint=first,
        final_checkpoint=accepted,
        steps=tuple(rows),
    )


def finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check(
    problem: StatefulCorotationalFiberFrame2DLinkProblem,
    accepted_checkpoint: StatefulCorotationalFiberFrame2DLinkCheckpoint,
    *,
    target_load_factor: float,
    trial_free_coordinates_m: Any,
    epsilon_m: float = 1.0e-8,
    relative_tolerance: float = 1.0e-7,
) -> dict[str, Any]:
    """Check the full frame-plus-link Jacobian from one accepted parent."""

    epsilon = _finite(epsilon_m, name="epsilon_m")
    tolerance = _finite(relative_tolerance, name="relative_tolerance")
    if epsilon <= 0.0:
        raise ValueError("epsilon_m must be positive")
    if tolerance <= 0.0:
        raise ValueError("relative_tolerance must be positive")
    free = np.asarray(trial_free_coordinates_m, dtype=np.float64)
    equation_count = len(problem.free_global_dofs)
    if free.shape != (equation_count,) or not np.all(np.isfinite(free)):
        raise ValueError("trial_free_coordinates_m has invalid shape or values")
    parent_bytes = accepted_checkpoint.canonical_bytes()
    base = assemble_stateful_corotational_fiber_frame2d_links(
        problem,
        accepted_checkpoint,
        target_load_factor=target_load_factor,
        trial_free_coordinates_m=free,
    )
    finite_difference = np.empty_like(base.jacobian_kn_per_m)
    same_parent = _assembly_parent_binding(base, accepted_checkpoint)
    for column in range(equation_count):
        perturbation = np.zeros_like(free)
        perturbation[column] = epsilon
        forward = assemble_stateful_corotational_fiber_frame2d_links(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free + perturbation,
        )
        backward = assemble_stateful_corotational_fiber_frame2d_links(
            problem,
            accepted_checkpoint,
            target_load_factor=target_load_factor,
            trial_free_coordinates_m=free - perturbation,
        )
        finite_difference[:, column] = (forward.residual_kn - backward.residual_kn) / (
            2.0 * epsilon
        )
        same_parent = bool(
            same_parent
            and _assembly_parent_binding(forward, accepted_checkpoint)
            and _assembly_parent_binding(backward, accepted_checkpoint)
        )
    same_parent = bool(
        same_parent and accepted_checkpoint.canonical_bytes() == parent_bytes
    )
    error = finite_difference - base.jacobian_kn_per_m
    absolute_error = float(np.linalg.norm(error, ord=np.inf))
    scale = max(
        float(np.linalg.norm(finite_difference, ord=np.inf)),
        float(np.linalg.norm(base.jacobian_kn_per_m, ord=np.inf)),
        1.0,
    )
    relative_error = absolute_error / scale
    symmetry_error = float(
        np.linalg.norm(base.jacobian_kn_per_m - base.jacobian_kn_per_m.T, ord=np.inf)
    )
    material_split_error = float(
        np.linalg.norm(
            base.material_tangent_global
            - base.frame_material_tangent_global
            - base.link_material_tangent_global,
            ord=np.inf,
        )
    )
    total_split_error = float(
        np.linalg.norm(
            base.consistent_tangent_global
            - base.material_tangent_global
            - base.geometric_tangent_global,
            ord=np.inf,
        )
    )
    frame_material_norm = float(
        np.linalg.norm(base.frame_material_tangent_global, ord=np.inf)
    )
    link_material_norm = float(
        np.linalg.norm(base.link_material_tangent_global, ord=np.inf)
    )
    geometric_norm = float(np.linalg.norm(base.geometric_tangent_global, ord=np.inf))
    return {
        "parent_checkpoint_hash": accepted_checkpoint.state_hash,
        "parent_epoch": accepted_checkpoint.epoch,
        "same_committed_parent_checkpoint": same_parent,
        "equation_count": equation_count,
        "finite_difference_epsilon_m": epsilon,
        "analytic_jacobian_kn_per_m": base.jacobian_kn_per_m.tolist(),
        "finite_difference_jacobian_kn_per_m": finite_difference.tolist(),
        "absolute_inf_error_kn_per_m": absolute_error,
        "relative_inf_error": relative_error,
        "relative_tolerance": tolerance,
        "tangent_symmetry_error_kn_per_m": symmetry_error,
        "frame_link_material_split_error_kn_per_m": material_split_error,
        "material_geometric_split_error_kn_per_m": total_split_error,
        "frame_material_tangent_inf_norm_kn_per_m": frame_material_norm,
        "link_material_tangent_inf_norm_kn_per_m": link_material_norm,
        "geometric_tangent_inf_norm_kn_per_m": geometric_norm,
        "all_tangent_terms_active": bool(
            frame_material_norm > 0.0
            and link_material_norm > 0.0
            and geometric_norm > 0.0
        ),
        "yielded_link_count": sum(
            int(row.response.yielded) for row in base.link_assemblies
        ),
        "yielded_member_count": sum(
            int(row.response.yielded_integration_point_count > 0)
            for row in base.member_assemblies
        ),
        "damaged_member_count": sum(
            int(row.response.damaged_integration_point_count > 0)
            for row in base.member_assemblies
        ),
        "pass": bool(
            relative_error <= tolerance
            and symmetry_error <= 1.0e-9
            and material_split_error <= 1.0e-8
            and total_split_error <= 1.0e-8
            and same_parent
        ),
    }


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DLink",
    "StatefulCorotationalFiberFrame2DLinkAssembly",
    "StatefulCorotationalFiberFrame2DLinkAssemblyRow",
    "StatefulCorotationalFiberFrame2DLinkCheckpoint",
    "StatefulCorotationalFiberFrame2DLinkLoadPathResult",
    "StatefulCorotationalFiberFrame2DLinkLoadStepAdapter",
    "StatefulCorotationalFiberFrame2DLinkLoadStepResult",
    "StatefulCorotationalFiberFrame2DLinkProblem",
    "assemble_stateful_corotational_fiber_frame2d_links",
    "finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check",
    "initial_stateful_corotational_fiber_frame2d_link_checkpoint",
    "run_stateful_corotational_fiber_frame2d_link_load_path",
    "solve_stateful_corotational_fiber_frame2d_link_load_step",
    "validate_stateful_corotational_fiber_frame2d_link_checkpoint",
]
