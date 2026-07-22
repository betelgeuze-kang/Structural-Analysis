"""Stateful scalar links coupled to a corotational 2D fiber frame.

The existing frame checkpoint remains unchanged.  This bounded coupling layer
nests that checkpoint with one immutable state per scalar force-deformation
link and commits both state families atomically. Translational and rotational
links keep distinct force-deformation and moment-rotation unit contracts.
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
from structural_analysis.materials.bilinear_rotational_link import (
    BilinearCombinedHardeningRotationalLink,
    BilinearRotationalLinkResponse,
    BilinearRotationalLinkState,
)
from structural_analysis.materials.compression_only_gap_link import (
    GAP_LINK_ACTIVE_SET_ALGORITHM,
    GAP_LINK_CLOSURE_CONVENTION,
    CompressionOnlyGapLink,
    CompressionOnlyGapLinkResponse,
    CompressionOnlyGapLinkState,
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
    "stateful-corotational-fiber-frame2d-link-coupling.v7"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-corotational-fiber-frame2d-link-checkpoint.v7"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY = (
    "deformation_link=global_or_fixed_reference_B_link@u_global|"
    "current_length-reference_length|relative_nodal_rotation;"
    "f_internal=f_frame+sum(scatter_link(B_link.T*generalized_force));"
    "K_material=K_frame_material+sum(scatter_link(B_link.T*k*B_link));"
    "K_geometric=K_frame_geometric+sum(scatter_link(force*hessian_length));"
    "K_consistent=K_material+K_geometric;"
    "gap_active_set=global_x_or_fixed_reference_or_updated_current_axis_"
    "compression_only_open_at_exact_closure"
)
STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY = (
    "This coupling supports one or more scalar translational force-deformation "
    "links between planar frame nodes on global axes or a fixed reference "
    "local-axial direction, plus an internal updated-axial link whose force "
    "direction and geometric tangent follow the current chord. It also supports "
    "a distinct scalar relative-rz moment-rotation link between planar nodes and "
    "one frictionless compression-only elastic gap on the global-x relative "
    "DOF, a fixed reference local-axis normal, or an internal current-chord "
    "normal with its consistent geometric tangent. It does not provide general "
    "follower external loads, arbitrary follower contact surfaces, coupled "
    "multi-axis contact, friction, impact, general "
    "foundation uplift validation, damping, rate effects, degradation or "
    "pinching, shells, three-dimensional frames, production sparse execution, "
    "ROCm/HIP parity, full-building equilibrium, G1 closure, or commercial-"
    "readiness evidence."
)
_CHECKPOINT_HASH_DOMAIN = (
    b"structural-analysis/stateful-corotational-fiber-frame2d-link-checkpoint/v7\0"
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
    """One scalar translational link between two planar frame nodes."""

    link_id: str
    node_i: int
    node_j: int
    component: Literal["ux", "uy", "local_axial", "updated_axial"]
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
        if self.component not in ("ux", "uy", "local_axial", "updated_axial"):
            raise ValueError(
                "link component must be 'ux', 'uy', 'local_axial', or 'updated_axial'"
            )
        if type(self.material) is not BilinearCombinedHardeningLink:
            raise ValueError("link material must be a BilinearCombinedHardeningLink")

    @property
    def component_offset(self) -> int:
        if self.component in ("local_axial", "updated_axial"):
            raise ValueError("axial links do not have one component offset")
        return 0 if self.component == "ux" else 1

    def global_dofs(self) -> tuple[int, ...]:
        if self.component in ("local_axial", "updated_axial"):
            return (
                3 * self.node_i,
                3 * self.node_i + 1,
                3 * self.node_j,
                3 * self.node_j + 1,
            )
        offset = self.component_offset
        return 3 * self.node_i + offset, 3 * self.node_j + offset

    def _node_coordinates(self, node_coordinates_m: Any) -> np.ndarray:
        try:
            coordinates = np.asarray(node_coordinates_m, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("node coordinates must be a finite (n, 2) array") from exc
        if (
            coordinates.ndim != 2
            or coordinates.shape[1:] != (2,)
            or max(self.node_i, self.node_j) >= coordinates.shape[0]
            or not np.all(np.isfinite(coordinates))
        ):
            raise ValueError("node coordinates must be a finite (n, 2) array")
        return coordinates

    def _global_displacements(self, global_displacements: Any) -> np.ndarray:
        dofs = self.global_dofs()
        try:
            displacements = np.asarray(global_displacements, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("global displacements must be a finite vector") from exc
        if (
            displacements.ndim != 1
            or max(dofs) >= displacements.shape[0]
            or not np.all(np.isfinite(displacements))
        ):
            raise ValueError("global displacements must be a finite vector")
        return displacements

    def reference_length_m(self, node_coordinates_m: Any) -> float:
        """Return the strictly positive undeformed endpoint distance."""

        coordinates = self._node_coordinates(node_coordinates_m)
        delta = coordinates[self.node_j] - coordinates[self.node_i]
        length = float(np.linalg.norm(delta))
        if not math.isfinite(length) or length <= 0.0:
            raise ValueError("axial link reference length must be positive")
        return length

    def reference_direction_cosines(
        self,
        node_coordinates_m: Any,
    ) -> tuple[float, float]:
        """Return the fixed reference direction used by this scalar link."""

        if self.component == "ux":
            return 1.0, 0.0
        if self.component == "uy":
            return 0.0, 1.0
        coordinates = self._node_coordinates(node_coordinates_m)
        delta = coordinates[self.node_j] - coordinates[self.node_i]
        length = self.reference_length_m(coordinates)
        return float(delta[0] / length), float(delta[1] / length)

    def current_length_and_direction(
        self,
        node_coordinates_m: Any,
        global_displacements: Any,
    ) -> tuple[float, float, float]:
        """Return current endpoint length and direction for an updated link."""

        if self.component != "updated_axial":
            raise ValueError("current geometry is only defined for updated_axial links")
        coordinates = self._node_coordinates(node_coordinates_m)
        displacements = self._global_displacements(global_displacements)
        dofs = self.global_dofs()
        relative_displacement = np.array(
            (
                displacements[dofs[2]] - displacements[dofs[0]],
                displacements[dofs[3]] - displacements[dofs[1]],
            ),
            dtype=np.float64,
        )
        current_delta = (
            coordinates[self.node_j] - coordinates[self.node_i] + relative_displacement
        )
        length = float(np.linalg.norm(current_delta))
        if not math.isfinite(length) or length <= 0.0:
            raise ValueError("updated_axial link current length must be positive")
        return (
            length,
            float(current_delta[0] / length),
            float(current_delta[1] / length),
        )

    def kinematic_vector(
        self,
        node_coordinates_m: Any,
        global_displacements: Any | None = None,
    ) -> np.ndarray:
        """Return the scalar-deformation gradient on the active global DOFs."""

        if self.component == "ux":
            values = (-1.0, 1.0)
        elif self.component == "uy":
            values = (-1.0, 1.0)
        elif self.component == "updated_axial":
            if global_displacements is None:
                raise ValueError(
                    "updated_axial kinematic vector requires global displacements"
                )
            _, nx, ny = self.current_length_and_direction(
                node_coordinates_m,
                global_displacements,
            )
            values = (-nx, -ny, nx, ny)
        else:
            nx, ny = self.reference_direction_cosines(node_coordinates_m)
            values = (-nx, -ny, nx, ny)
        return _readonly(
            values,
            shape=(len(values),),
            name="link kinematic vector",
        )

    def deformation_m(
        self,
        global_displacements: Any,
        node_coordinates_m: Any,
    ) -> float:
        dofs = self.global_dofs()
        displacements = self._global_displacements(global_displacements)
        if self.component == "updated_axial":
            current_length, _, _ = self.current_length_and_direction(
                node_coordinates_m,
                displacements,
            )
            return current_length - self.reference_length_m(node_coordinates_m)
        return float(
            self.kinematic_vector(node_coordinates_m) @ displacements[list(dofs)]
        )

    def deformation_hessian_per_m(
        self,
        node_coordinates_m: Any,
        global_displacements: Any,
    ) -> np.ndarray:
        """Return the current-length Hessian on the link's active DOFs."""

        dof_count = len(self.global_dofs())
        if self.component != "updated_axial":
            return _readonly(
                np.zeros((dof_count, dof_count), dtype=np.float64),
                shape=(dof_count, dof_count),
                name="link deformation hessian",
            )
        length, nx, ny = self.current_length_and_direction(
            node_coordinates_m,
            global_displacements,
        )
        direction = np.array((nx, ny), dtype=np.float64)
        transverse_projector = (
            np.eye(2, dtype=np.float64) - np.outer(direction, direction)
        ) / length
        hessian = np.block(
            [
                [transverse_projector, -transverse_projector],
                [-transverse_projector, transverse_projector],
            ]
        )
        return _readonly(
            hessian,
            shape=(4, 4),
            name="link deformation hessian",
        )

    def contract_payload(
        self,
        node_coordinates_m: Any | None = None,
    ) -> dict[str, Any]:
        material = self.material
        payload: dict[str, Any] = {
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
        if self.component in ("local_axial", "updated_axial"):
            if node_coordinates_m is None:
                raise ValueError("axial link contract requires node coordinates")
            payload["reference_direction_cosines"] = list(
                self.reference_direction_cosines(node_coordinates_m)
            )
            payload["kinematic_vector"] = self.kinematic_vector(
                node_coordinates_m,
                (
                    np.zeros(3 * len(self._node_coordinates(node_coordinates_m)))
                    if self.component == "updated_axial"
                    else None
                ),
            ).tolist()
            payload["reference_length_m"] = self.reference_length_m(node_coordinates_m)
        if self.component == "updated_axial":
            payload["axis_update"] = "current_endpoint_chord"
            payload["deformation_measure"] = "current_length-reference_length"
            payload["geometric_tangent"] = "force*current_length_hessian"
        return payload


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DCompressionOnlyGapLink:
    """One frictionless compression-only gap on a scalar planar normal."""

    link_id: str
    node_i: int
    node_j: int
    material: CompressionOnlyGapLink
    component: Literal["ux", "local_axial", "updated_axial"] = "ux"

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
            raise ValueError("gap-link node indices must be distinct and non-negative")
        if self.component not in ("ux", "local_axial", "updated_axial"):
            raise ValueError(
                "compression-only gap component must be 'ux', 'local_axial', "
                "or 'updated_axial'"
            )
        if type(self.material) is not CompressionOnlyGapLink:
            raise ValueError("gap-link material must be a CompressionOnlyGapLink")

    def global_dofs(self) -> tuple[int, ...]:
        if self.component == "ux":
            return 3 * self.node_i, 3 * self.node_j
        return (
            3 * self.node_i,
            3 * self.node_i + 1,
            3 * self.node_j,
            3 * self.node_j + 1,
        )

    def _node_coordinates(self, node_coordinates_m: Any) -> np.ndarray:
        try:
            coordinates = np.asarray(node_coordinates_m, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("node coordinates must be a finite (n, 2) array") from exc
        if (
            coordinates.ndim != 2
            or coordinates.shape[1:] != (2,)
            or max(self.node_i, self.node_j) >= coordinates.shape[0]
            or not np.all(np.isfinite(coordinates))
        ):
            raise ValueError("node coordinates must be a finite (n, 2) array")
        return coordinates

    def reference_length_m(self, node_coordinates_m: Any) -> float:
        """Return the strictly positive undeformed endpoint distance."""

        coordinates = self._node_coordinates(node_coordinates_m)
        length = float(
            np.linalg.norm(coordinates[self.node_j] - coordinates[self.node_i])
        )
        if not math.isfinite(length) or length <= 0.0:
            raise ValueError("gap-link reference length must be positive")
        return length

    def reference_direction_cosines(
        self,
        node_coordinates_m: Any,
    ) -> tuple[float, float]:
        """Return the fixed reference normal directed from node i to node j."""

        if self.component == "ux":
            return 1.0, 0.0
        coordinates = self._node_coordinates(node_coordinates_m)
        delta = coordinates[self.node_j] - coordinates[self.node_i]
        length = self.reference_length_m(coordinates)
        return float(delta[0] / length), float(delta[1] / length)

    def _global_displacements(self, global_displacements: Any) -> np.ndarray:
        dofs = self.global_dofs()
        try:
            displacements = np.asarray(global_displacements, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("global displacements must be a finite vector") from exc
        if (
            displacements.ndim != 1
            or max(dofs) >= displacements.shape[0]
            or not np.all(np.isfinite(displacements))
        ):
            raise ValueError("global displacements must be a finite vector")
        return displacements

    def current_length_and_direction(
        self,
        node_coordinates_m: Any,
        global_displacements: Any,
    ) -> tuple[float, float, float]:
        """Return current endpoint length and normal for an updated gap."""

        if self.component != "updated_axial":
            raise ValueError("current geometry is only defined for updated_axial gaps")
        coordinates = self._node_coordinates(node_coordinates_m)
        displacements = self._global_displacements(global_displacements)
        dofs = self.global_dofs()
        relative_displacement = np.array(
            (
                displacements[dofs[2]] - displacements[dofs[0]],
                displacements[dofs[3]] - displacements[dofs[1]],
            ),
            dtype=np.float64,
        )
        current_delta = (
            coordinates[self.node_j] - coordinates[self.node_i] + relative_displacement
        )
        length = float(np.linalg.norm(current_delta))
        if not math.isfinite(length) or length <= 0.0:
            raise ValueError("updated_axial gap current length must be positive")
        return (
            length,
            float(current_delta[0] / length),
            float(current_delta[1] / length),
        )

    def kinematic_vector(
        self,
        node_coordinates_m: Any | None = None,
        global_displacements: Any | None = None,
    ) -> np.ndarray:
        if self.component == "ux":
            values = (-1.0, 1.0)
        elif self.component == "updated_axial":
            if node_coordinates_m is None or global_displacements is None:
                raise ValueError(
                    "updated_axial compression-only gap requires node coordinates "
                    "and global displacements"
                )
            _, nx, ny = self.current_length_and_direction(
                node_coordinates_m,
                global_displacements,
            )
            values = (-nx, -ny, nx, ny)
        else:
            if node_coordinates_m is None:
                raise ValueError(
                    "local-axis compression-only gap requires node coordinates"
                )
            nx, ny = self.reference_direction_cosines(node_coordinates_m)
            values = (-nx, -ny, nx, ny)
        return _readonly(
            values,
            shape=(len(values),),
            name="compression-only gap kinematic vector",
        )

    def deformation_m(
        self,
        global_displacements: Any,
        node_coordinates_m: Any | None = None,
    ) -> float:
        dofs = self.global_dofs()
        displacements = self._global_displacements(global_displacements)
        if self.component == "updated_axial":
            if node_coordinates_m is None:
                raise ValueError(
                    "updated_axial compression-only gap requires node coordinates"
                )
            current_length, _, _ = self.current_length_and_direction(
                node_coordinates_m,
                displacements,
            )
            return current_length - self.reference_length_m(node_coordinates_m)
        return float(
            self.kinematic_vector(node_coordinates_m) @ displacements[list(dofs)]
        )

    def deformation_hessian_per_m(
        self,
        node_coordinates_m: Any,
        global_displacements: Any,
    ) -> np.ndarray:
        dof_count = len(self.global_dofs())
        if self.component == "updated_axial":
            length, nx, ny = self.current_length_and_direction(
                node_coordinates_m,
                global_displacements,
            )
            direction = np.array((nx, ny), dtype=np.float64)
            transverse_projector = (
                np.eye(2, dtype=np.float64) - np.outer(direction, direction)
            ) / length
            hessian = np.block(
                [
                    [transverse_projector, -transverse_projector],
                    [-transverse_projector, transverse_projector],
                ]
            )
            return _readonly(
                hessian,
                shape=(4, 4),
                name="compression-only gap deformation hessian",
            )
        return _readonly(
            np.zeros((dof_count, dof_count), dtype=np.float64),
            shape=(dof_count, dof_count),
            name="compression-only gap deformation hessian",
        )

    def contract_payload(
        self,
        node_coordinates_m: Any | None = None,
    ) -> dict[str, Any]:
        material = self.material
        if self.component in ("local_axial", "updated_axial"):
            if node_coordinates_m is None:
                raise ValueError("axial gap contract requires node coordinates")
            coordinates = self._node_coordinates(node_coordinates_m)
        else:
            coordinates = None
        kinematic = self.kinematic_vector(
            node_coordinates_m,
            (
                np.zeros(3 * len(coordinates), dtype=np.float64)
                if self.component == "updated_axial" and coordinates is not None
                else None
            ),
        )
        if self.component == "ux":
            contact_normal = "global_x_node_i_to_node_j"
            deformation_measure = "ux_j-ux_i"
        elif self.component == "local_axial":
            contact_normal = "fixed_reference_local_axis_node_i_to_node_j"
            deformation_measure = "reference_normal_dot_u_j_minus_u_i"
        else:
            contact_normal = "updated_current_chord_node_i_to_node_j"
            deformation_measure = "current_length-reference_length"
        payload: dict[str, Any] = {
            "link_id": self.link_id,
            "node_i": self.node_i,
            "node_j": self.node_j,
            "component": self.component,
            "contact_normal": contact_normal,
            "kinematic_vector": kinematic.tolist(),
            "deformation_measure": deformation_measure,
            "active_set_algorithm": GAP_LINK_ACTIVE_SET_ALGORITHM,
            "closure_convention": GAP_LINK_CLOSURE_CONVENTION,
            "material": {
                "material_id": material.material_id,
                "contact_stiffness_kn_per_m": (material.contact_stiffness_kn_per_m),
                "initial_gap_m": material.initial_gap_m,
            },
        }
        if self.component in ("local_axial", "updated_axial"):
            assert node_coordinates_m is not None
            payload["reference_direction_cosines"] = list(
                self.reference_direction_cosines(node_coordinates_m)
            )
            payload["reference_length_m"] = self.reference_length_m(node_coordinates_m)
            if self.component == "local_axial":
                payload["axis_update"] = "none_fixed_reference_normal"
                payload["geometric_tangent"] = "zero_fixed_reference_normal"
            else:
                payload["axis_update"] = "current_endpoint_chord"
                payload["geometric_tangent"] = "force*current_length_hessian"
        return payload


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DRotationalLink:
    """One scalar relative-rz link with an explicit moment-rotation material."""

    link_id: str
    node_i: int
    node_j: int
    material: BilinearCombinedHardeningRotationalLink
    component: Literal["rz"] = "rz"

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
        if self.component != "rz":
            raise ValueError("rotational link component must be 'rz'")
        if type(self.material) is not BilinearCombinedHardeningRotationalLink:
            raise ValueError(
                "rotational link material must be a "
                "BilinearCombinedHardeningRotationalLink"
            )

    def global_dofs(self) -> tuple[int, int]:
        return 3 * self.node_i + 2, 3 * self.node_j + 2

    def kinematic_vector(self) -> np.ndarray:
        return _readonly(
            (-1.0, 1.0),
            shape=(2,),
            name="rotational link kinematic vector",
        )

    def rotation_rad(self, global_displacements: Any) -> float:
        dofs = self.global_dofs()
        try:
            displacements = np.asarray(global_displacements, dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise ValueError("global displacements must be a finite vector") from exc
        if (
            displacements.ndim != 1
            or max(dofs) >= displacements.shape[0]
            or not np.all(np.isfinite(displacements))
        ):
            raise ValueError("global displacements must be a finite vector")
        return float(self.kinematic_vector() @ displacements[list(dofs)])

    def contract_payload(
        self,
        node_coordinates_m: Any | None = None,
    ) -> dict[str, Any]:
        del node_coordinates_m
        material = self.material
        return {
            "link_id": self.link_id,
            "node_i": self.node_i,
            "node_j": self.node_j,
            "component": self.component,
            "kinematic_vector": self.kinematic_vector().tolist(),
            "deformation_measure": "theta_j-theta_i",
            "generalized_force": "equal_and_opposite_nodal_moment",
            "material": {
                "material_id": material.material_id,
                "initial_stiffness_kn_m_per_rad": (
                    material.initial_stiffness_kn_m_per_rad
                ),
                "yield_moment_kn_m": material.yield_moment_kn_m,
                "isotropic_hardening_kn_m_per_rad": (
                    material.isotropic_hardening_kn_m_per_rad
                ),
                "kinematic_hardening_kn_m_per_rad": (
                    material.kinematic_hardening_kn_m_per_rad
                ),
                "yield_tolerance_kn_m": material.yield_tolerance_kn_m,
            },
        }


StatefulCorotationalFiberFrame2DScalarLink = (
    StatefulCorotationalFiberFrame2DLink
    | StatefulCorotationalFiberFrame2DCompressionOnlyGapLink
    | StatefulCorotationalFiberFrame2DRotationalLink
)
ScalarLinkState = (
    BilinearLinkState | BilinearRotationalLinkState | CompressionOnlyGapLinkState
)


def _link_state_matches_definition(
    link: StatefulCorotationalFiberFrame2DScalarLink,
    state: ScalarLinkState,
) -> bool:
    if type(link) is StatefulCorotationalFiberFrame2DRotationalLink:
        return type(state) is BilinearRotationalLinkState
    if type(link) is StatefulCorotationalFiberFrame2DCompressionOnlyGapLink:
        return type(state) is CompressionOnlyGapLinkState
    return type(state) is BilinearLinkState


def _link_generalized_deformation(
    link: StatefulCorotationalFiberFrame2DScalarLink,
    global_displacements: Any,
    node_coordinates_m: Any,
) -> float:
    if type(link) is StatefulCorotationalFiberFrame2DRotationalLink:
        return link.rotation_rad(global_displacements)
    return link.deformation_m(global_displacements, node_coordinates_m)


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DLinkProblem:
    """A pre-existing corotational frame plus scalar link definitions."""

    case_id: str
    frame_problem: StatefulCorotationalFiberFrame2DProblem
    links: tuple[StatefulCorotationalFiberFrame2DScalarLink, ...]

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
                type(link)
                in (
                    StatefulCorotationalFiberFrame2DLink,
                    StatefulCorotationalFiberFrame2DCompressionOnlyGapLink,
                    StatefulCorotationalFiberFrame2DRotationalLink,
                )
                for link in self.links
            )
        ):
            raise ValueError("links must be a non-empty tuple of link definitions")
        node_count = len(self.frame_problem.node_coordinates_m)
        fixed = set(self.frame_problem.fixed_global_dofs)
        zero_displacements = np.zeros(self.global_dof_count, dtype=np.float64)
        link_ids: set[str] = set()
        kinematic_rows: list[np.ndarray] = []
        for link in self.links:
            if link.link_id in link_ids:
                raise ValueError("link_id values must be unique")
            link_ids.add(link.link_id)
            if link.node_i >= node_count or link.node_j >= node_count:
                raise ValueError("link node index is out of range")
            dofs = link.global_dofs()
            if type(link) is StatefulCorotationalFiberFrame2DRotationalLink:
                kinematic = link.kinematic_vector()
            else:
                kinematic = link.kinematic_vector(
                    self.frame_problem.node_coordinates_m,
                    zero_displacements if link.component == "updated_axial" else None,
                )
            global_kinematic = np.zeros(self.global_dof_count, dtype=np.float64)
            global_kinematic[list(dofs)] = kinematic
            if any(
                np.array_equal(global_kinematic, existing)
                or np.array_equal(global_kinematic, -existing)
                for existing in kinematic_rows
            ):
                raise ValueError("duplicate link endpoint/component pair")
            kinematic_rows.append(global_kinematic)
            active_dofs = tuple(
                dof
                for dof, coefficient in zip(dofs, kinematic, strict=True)
                if coefficient != 0.0
            )
            if all(dof in fixed for dof in active_dofs):
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
                "links": [
                    link.contract_payload(self.frame_problem.node_coordinates_m)
                    for link in self.links
                ],
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
    link_states: tuple[ScalarLinkState, ...]
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
            or not all(
                type(state)
                in (
                    BilinearLinkState,
                    BilinearRotationalLinkState,
                    CompressionOnlyGapLinkState,
                )
                for state in self.link_states
            )
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
    for link, state in zip(problem.links, checkpoint.link_states, strict=True):
        if not _link_state_matches_definition(link, state):
            raise ValueError("checkpoint link state type does not match definition")
        deformation = _link_generalized_deformation(
            link,
            checkpoint.global_displacements,
            problem.frame_problem.node_coordinates_m,
        )
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
    component: Literal["ux", "uy", "local_axial", "updated_axial"]
    global_dofs: tuple[int, ...]
    kinematic_vector: np.ndarray
    deformation_hessian_per_m: np.ndarray
    deformation_m: float
    internal_load_global_kn: np.ndarray
    material_tangent_global_kn_per_m: np.ndarray
    geometric_tangent_global_kn_per_m: np.ndarray
    tangent_global_kn_per_m: np.ndarray
    response: BilinearLinkResponse | CompressionOnlyGapLinkResponse

    def __post_init__(self) -> None:
        normalized_id = str(self.link_id).strip()
        if not normalized_id:
            raise ValueError("link_id must be non-empty")
        object.__setattr__(self, "link_id", normalized_id)
        if self.component not in ("ux", "uy", "local_axial", "updated_axial"):
            raise ValueError("link component is invalid")
        if (
            not isinstance(self.global_dofs, tuple)
            or len(self.global_dofs) not in (2, 4)
            or len(set(self.global_dofs)) != len(self.global_dofs)
            or any(type(dof) is not int or dof < 0 for dof in self.global_dofs)
        ):
            raise ValueError(
                "global_dofs must contain two or four distinct non-negative DOFs"
            )
        dof_count = len(self.global_dofs)
        if (self.component in ("ux", "uy")) != (dof_count == 2):
            raise ValueError("link component and global DOF count do not match")
        object.__setattr__(
            self,
            "kinematic_vector",
            _readonly(
                self.kinematic_vector,
                shape=(dof_count,),
                name="kinematic_vector",
            ),
        )
        if dof_count == 2:
            if not _exact_float64_equal(self.kinematic_vector, (-1.0, 1.0)):
                raise ValueError("two-DOF link kinematic vector is invalid")
        elif not _exact_float64_equal(
            self.kinematic_vector[:2],
            -self.kinematic_vector[2:],
        ) or not math.isclose(
            float(np.linalg.norm(self.kinematic_vector[2:])),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        ):
            raise ValueError("four-DOF link kinematic vector is invalid")
        object.__setattr__(
            self,
            "deformation_hessian_per_m",
            _readonly(
                self.deformation_hessian_per_m,
                shape=(dof_count, dof_count),
                name="deformation_hessian_per_m",
            ),
        )
        hessian_norm = float(np.linalg.norm(self.deformation_hessian_per_m, ord=np.inf))
        if self.component == "updated_axial":
            translation_x = np.array((1.0, 0.0, 1.0, 0.0), dtype=np.float64)
            translation_y = np.array((0.0, 1.0, 0.0, 1.0), dtype=np.float64)
            if (
                hessian_norm <= 0.0
                or not np.allclose(
                    self.deformation_hessian_per_m,
                    self.deformation_hessian_per_m.T,
                    rtol=0.0,
                    atol=1.0e-15,
                )
                or not np.allclose(
                    self.deformation_hessian_per_m @ translation_x,
                    0.0,
                    rtol=0.0,
                    atol=1.0e-15,
                )
                or not np.allclose(
                    self.deformation_hessian_per_m @ translation_y,
                    0.0,
                    rtol=0.0,
                    atol=1.0e-15,
                )
            ):
                raise ValueError("updated_axial deformation hessian is invalid")
        elif hessian_norm != 0.0:
            raise ValueError("fixed-axis link deformation hessian must be zero")
        object.__setattr__(
            self,
            "deformation_m",
            _finite(self.deformation_m, name="deformation_m"),
        )
        if type(self.response) not in (
            BilinearLinkResponse,
            CompressionOnlyGapLinkResponse,
        ):
            raise ValueError("response type is invalid")
        if self.deformation_m != self.response.deformation_m:
            raise ValueError("link deformation does not match response")
        object.__setattr__(
            self,
            "internal_load_global_kn",
            _readonly(
                self.internal_load_global_kn,
                shape=(dof_count,),
                name="internal_load_global_kn",
            ),
        )
        object.__setattr__(
            self,
            "material_tangent_global_kn_per_m",
            _readonly(
                self.material_tangent_global_kn_per_m,
                shape=(dof_count, dof_count),
                name="material_tangent_global_kn_per_m",
            ),
        )
        object.__setattr__(
            self,
            "geometric_tangent_global_kn_per_m",
            _readonly(
                self.geometric_tangent_global_kn_per_m,
                shape=(dof_count, dof_count),
                name="geometric_tangent_global_kn_per_m",
            ),
        )
        object.__setattr__(
            self,
            "tangent_global_kn_per_m",
            _readonly(
                self.tangent_global_kn_per_m,
                shape=(dof_count, dof_count),
                name="tangent_global_kn_per_m",
            ),
        )
        expected_force = self.response.force_kn * self.kinematic_vector
        expected_material_tangent = (
            self.response.consistent_tangent_kn_per_m
            * np.outer(
                self.kinematic_vector,
                self.kinematic_vector,
            )
        )
        expected_geometric_tangent = (
            self.response.force_kn * self.deformation_hessian_per_m
        )
        expected_tangent = expected_material_tangent + expected_geometric_tangent
        if not _exact_float64_equal(self.internal_load_global_kn, expected_force):
            raise ValueError("link internal load does not match response")
        if not _exact_float64_equal(
            self.material_tangent_global_kn_per_m,
            expected_material_tangent,
        ):
            raise ValueError("link material tangent does not match response")
        if not _exact_float64_equal(
            self.geometric_tangent_global_kn_per_m,
            expected_geometric_tangent,
        ):
            raise ValueError("link geometric tangent does not match response")
        if not _exact_float64_equal(self.tangent_global_kn_per_m, expected_tangent):
            raise ValueError("link tangent does not match response")

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "component": self.component,
            "global_dofs": list(self.global_dofs),
            "kinematic_vector": self.kinematic_vector.tolist(),
            "deformation_hessian_per_m": self.deformation_hessian_per_m.tolist(),
            "deformation_m": self.deformation_m,
            "internal_load_global_kn": self.internal_load_global_kn.tolist(),
            "material_tangent_global_kn_per_m": (
                self.material_tangent_global_kn_per_m.tolist()
            ),
            "geometric_tangent_global_kn_per_m": (
                self.geometric_tangent_global_kn_per_m.tolist()
            ),
            "tangent_global_kn_per_m": self.tangent_global_kn_per_m.tolist(),
            "response": self.response.to_dict(),
        }


@dataclass(frozen=True)
class StatefulCorotationalFiberFrame2DRotationalLinkAssemblyRow:
    """One assembled moment-rotation row on two physical nodal rz DOFs."""

    link_id: str
    component: Literal["rz"]
    global_dofs: tuple[int, int]
    kinematic_vector: np.ndarray
    rotation_rad: float
    internal_moments_global_kn_m: np.ndarray
    material_tangent_global_kn_m_per_rad: np.ndarray
    tangent_global_kn_m_per_rad: np.ndarray
    response: BilinearRotationalLinkResponse

    def __post_init__(self) -> None:
        normalized_id = str(self.link_id).strip()
        if not normalized_id:
            raise ValueError("link_id must be non-empty")
        object.__setattr__(self, "link_id", normalized_id)
        if self.component != "rz":
            raise ValueError("rotational link component must be 'rz'")
        if (
            not isinstance(self.global_dofs, tuple)
            or len(self.global_dofs) != 2
            or len(set(self.global_dofs)) != 2
            or any(type(dof) is not int or dof < 0 for dof in self.global_dofs)
            or any(dof % 3 != 2 for dof in self.global_dofs)
        ):
            raise ValueError(
                "rotational link global_dofs must be two distinct nodal rz DOFs"
            )
        object.__setattr__(
            self,
            "kinematic_vector",
            _readonly(
                self.kinematic_vector,
                shape=(2,),
                name="kinematic_vector",
            ),
        )
        if not _exact_float64_equal(self.kinematic_vector, (-1.0, 1.0)):
            raise ValueError("rotational link kinematic vector is invalid")
        object.__setattr__(
            self,
            "rotation_rad",
            _finite(self.rotation_rad, name="rotation_rad"),
        )
        if type(self.response) is not BilinearRotationalLinkResponse:
            raise ValueError("rotational link response type is invalid")
        if self.rotation_rad != self.response.rotation_rad:
            raise ValueError("rotational link rotation does not match response")
        for name in (
            "internal_moments_global_kn_m",
            "material_tangent_global_kn_m_per_rad",
            "tangent_global_kn_m_per_rad",
        ):
            shape = (2,) if name == "internal_moments_global_kn_m" else (2, 2)
            object.__setattr__(
                self,
                name,
                _readonly(getattr(self, name), shape=shape, name=name),
            )
        expected_moments = self.response.moment_kn_m * self.kinematic_vector
        expected_tangent = self.response.consistent_tangent_kn_m_per_rad * np.outer(
            self.kinematic_vector, self.kinematic_vector
        )
        if not _exact_float64_equal(
            self.internal_moments_global_kn_m,
            expected_moments,
        ):
            raise ValueError("rotational link moments do not match response")
        if not _exact_float64_equal(
            self.material_tangent_global_kn_m_per_rad,
            expected_tangent,
        ):
            raise ValueError("rotational link material tangent does not match response")
        if not _exact_float64_equal(
            self.tangent_global_kn_m_per_rad,
            expected_tangent,
        ):
            raise ValueError("rotational link tangent does not match response")

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "component": self.component,
            "global_dofs": list(self.global_dofs),
            "kinematic_vector": self.kinematic_vector.tolist(),
            "rotation_rad": self.rotation_rad,
            "internal_moments_global_kn_m": (
                self.internal_moments_global_kn_m.tolist()
            ),
            "material_tangent_global_kn_m_per_rad": (
                self.material_tangent_global_kn_m_per_rad.tolist()
            ),
            "tangent_global_kn_m_per_rad": (self.tangent_global_kn_m_per_rad.tolist()),
            "response": self.response.to_dict(),
        }


StatefulCorotationalFiberFrame2DScalarLinkAssemblyRow = (
    StatefulCorotationalFiberFrame2DLinkAssemblyRow
    | StatefulCorotationalFiberFrame2DRotationalLinkAssemblyRow
)


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
    frame_geometric_tangent_global: np.ndarray
    link_geometric_tangent_global: np.ndarray
    geometric_tangent_global: np.ndarray
    consistent_tangent_global: np.ndarray
    frame_assembly: StatefulCorotationalFiberFrame2DAssembly
    link_assemblies: tuple[StatefulCorotationalFiberFrame2DScalarLinkAssemblyRow, ...]
    trial_link_states: tuple[ScalarLinkState, ...]

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
            ("frame_geometric_tangent_global", (global_count, global_count)),
            ("link_geometric_tangent_global", (global_count, global_count)),
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
            self.geometric_tangent_global,
            self.frame_geometric_tangent_global + self.link_geometric_tangent_global,
            rtol=1.0e-13,
            atol=1.0e-10,
        ):
            raise ValueError("geometric tangent does not equal frame plus link terms")
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
                type(row)
                in (
                    StatefulCorotationalFiberFrame2DLinkAssemblyRow,
                    StatefulCorotationalFiberFrame2DRotationalLinkAssemblyRow,
                )
                for row in self.link_assemblies
            )
        ):
            raise ValueError("link_assemblies contains an invalid row")
        if (
            not isinstance(self.trial_link_states, tuple)
            or len(self.trial_link_states) != len(self.link_assemblies)
            or not all(
                type(state)
                in (
                    BilinearLinkState,
                    BilinearRotationalLinkState,
                    CompressionOnlyGapLinkState,
                )
                for state in self.trial_link_states
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
            "frame_geometric_tangent_global": (
                self.frame_geometric_tangent_global.tolist()
            ),
            "link_geometric_tangent_global": (
                self.link_geometric_tangent_global.tolist()
            ),
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
    frame_geometric = np.array(
        frame.geometric_tangent_global,
        dtype=np.float64,
        copy=True,
    )
    link_geometric = np.zeros_like(frame_geometric)
    link_rows: list[StatefulCorotationalFiberFrame2DScalarLinkAssemblyRow] = []
    trial_link_states: list[ScalarLinkState] = []
    for link, parent in zip(
        problem.links,
        accepted_checkpoint.link_states,
        strict=True,
    ):
        dofs = link.global_dofs()
        if type(link) is StatefulCorotationalFiberFrame2DRotationalLink:
            if type(parent) is not BilinearRotationalLinkState:
                raise ValueError("rotational link parent state type is invalid")
            kinematic = link.kinematic_vector()
            rotation = link.rotation_rad(frame.global_displacements)
            response = link.material.integrate(rotation, parent)
            local_internal = response.moment_kn_m * kinematic
            local_material_tangent = (
                response.consistent_tangent_kn_m_per_rad
                * np.outer(kinematic, kinematic)
            )
            local_geometric_tangent = np.zeros((2, 2), dtype=np.float64)
            local_tangent = local_material_tangent
            link_rows.append(
                StatefulCorotationalFiberFrame2DRotationalLinkAssemblyRow(
                    link_id=link.link_id,
                    component=link.component,
                    global_dofs=dofs,
                    kinematic_vector=kinematic,
                    rotation_rad=rotation,
                    internal_moments_global_kn_m=local_internal,
                    material_tangent_global_kn_m_per_rad=(local_material_tangent),
                    tangent_global_kn_m_per_rad=local_tangent,
                    response=response,
                )
            )
        else:
            if (
                type(link) is StatefulCorotationalFiberFrame2DCompressionOnlyGapLink
                and type(parent) is not CompressionOnlyGapLinkState
            ):
                raise ValueError("gap-link parent state type is invalid")
            if (
                type(link) is StatefulCorotationalFiberFrame2DLink
                and type(parent) is not BilinearLinkState
            ):
                raise ValueError("bilinear-link parent state type is invalid")
            kinematic = link.kinematic_vector(
                problem.frame_problem.node_coordinates_m,
                (
                    frame.global_displacements
                    if link.component == "updated_axial"
                    else None
                ),
            )
            deformation = link.deformation_m(
                frame.global_displacements,
                problem.frame_problem.node_coordinates_m,
            )
            deformation_hessian = link.deformation_hessian_per_m(
                problem.frame_problem.node_coordinates_m,
                frame.global_displacements,
            )
            response = link.material.integrate(deformation, parent)
            local_internal = response.force_kn * kinematic
            local_material_tangent = response.consistent_tangent_kn_per_m * np.outer(
                kinematic, kinematic
            )
            local_geometric_tangent = response.force_kn * deformation_hessian
            local_tangent = local_material_tangent + local_geometric_tangent
            link_rows.append(
                StatefulCorotationalFiberFrame2DLinkAssemblyRow(
                    link_id=link.link_id,
                    component=link.component,
                    global_dofs=dofs,
                    kinematic_vector=kinematic,
                    deformation_hessian_per_m=deformation_hessian,
                    deformation_m=deformation,
                    internal_load_global_kn=local_internal,
                    material_tangent_global_kn_per_m=local_material_tangent,
                    geometric_tangent_global_kn_per_m=local_geometric_tangent,
                    tangent_global_kn_per_m=local_tangent,
                    response=response,
                )
            )
        internal[list(dofs)] += local_internal
        link_material[np.ix_(dofs, dofs)] += local_material_tangent
        link_geometric[np.ix_(dofs, dofs)] += local_geometric_tangent
        trial_link_states.append(response.state)

    material = frame_material + link_material
    geometric = frame_geometric + link_geometric
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
        frame_geometric_tangent_global=frame_geometric,
        link_geometric_tangent_global=link_geometric,
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
    geometric_split_error = float(
        np.linalg.norm(
            base.geometric_tangent_global
            - base.frame_geometric_tangent_global
            - base.link_geometric_tangent_global,
            ord=np.inf,
        )
    )
    frame_material_norm = float(
        np.linalg.norm(base.frame_material_tangent_global, ord=np.inf)
    )
    link_material_norm = float(
        np.linalg.norm(base.link_material_tangent_global, ord=np.inf)
    )
    frame_geometric_norm = float(
        np.linalg.norm(base.frame_geometric_tangent_global, ord=np.inf)
    )
    link_geometric_norm = float(
        np.linalg.norm(base.link_geometric_tangent_global, ord=np.inf)
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
        "frame_link_geometric_split_error_kn_per_m": geometric_split_error,
        "material_geometric_split_error_kn_per_m": total_split_error,
        "frame_material_tangent_inf_norm_kn_per_m": frame_material_norm,
        "link_material_tangent_inf_norm_kn_per_m": link_material_norm,
        "frame_geometric_tangent_inf_norm_kn_per_m": frame_geometric_norm,
        "link_geometric_tangent_inf_norm_kn_per_m": link_geometric_norm,
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
            and geometric_split_error <= 1.0e-8
            and total_split_error <= 1.0e-8
            and same_parent
        ),
    }


__all__ = [
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_ASSEMBLY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CHECKPOINT_SCHEMA_VERSION",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_CLAIM_BOUNDARY",
    "STATEFUL_COROTATIONAL_FIBER_FRAME2D_LINK_SCHEMA_VERSION",
    "StatefulCorotationalFiberFrame2DCompressionOnlyGapLink",
    "StatefulCorotationalFiberFrame2DLink",
    "StatefulCorotationalFiberFrame2DLinkAssembly",
    "StatefulCorotationalFiberFrame2DLinkAssemblyRow",
    "StatefulCorotationalFiberFrame2DLinkCheckpoint",
    "StatefulCorotationalFiberFrame2DLinkLoadPathResult",
    "StatefulCorotationalFiberFrame2DLinkLoadStepAdapter",
    "StatefulCorotationalFiberFrame2DLinkLoadStepResult",
    "StatefulCorotationalFiberFrame2DLinkProblem",
    "StatefulCorotationalFiberFrame2DRotationalLink",
    "StatefulCorotationalFiberFrame2DRotationalLinkAssemblyRow",
    "assemble_stateful_corotational_fiber_frame2d_links",
    "finite_difference_stateful_corotational_fiber_frame2d_link_tangent_check",
    "initial_stateful_corotational_fiber_frame2d_link_checkpoint",
    "run_stateful_corotational_fiber_frame2d_link_load_path",
    "solve_stateful_corotational_fiber_frame2d_link_load_step",
    "validate_stateful_corotational_fiber_frame2d_link_checkpoint",
]
