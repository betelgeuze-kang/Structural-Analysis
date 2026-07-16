"""Strict 3D Euler-Bernoulli frame element shared by canonical and MGT paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from structural_analysis.materials.elastic import ElasticIsotropicMaterial

FRAME_DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
FRAME_END_FORCE_LABELS = (
    "FX_I", "FY_I", "FZ_I", "MX_I", "MY_I", "MZ_I",
    "FX_J", "FY_J", "FZ_J", "MX_J", "MY_J", "MZ_J",
)


@dataclass(frozen=True)
class FrameProps:
    """Unit-consistent frame properties shared by canonical and legacy MGT callers."""

    area_m2: float
    e_n_per_m2: float
    g_n_per_m2: float
    iy_m4: float
    iz_m4: float
    j_m4: float

    def __post_init__(self) -> None:
        values = {
            "area": self.area_m2,
            "elastic_modulus": self.e_n_per_m2,
            "shear_modulus": self.g_n_per_m2,
            "Iy": self.iy_m4,
            "Iz": self.iz_m4,
            "J": self.j_m4,
        }
        invalid = [name for name, value in values.items() if not np.isfinite(value) or value <= 0.0]
        if invalid:
            raise ValueError(f"Frame properties must be explicit and positive: {', '.join(invalid)}")

    @property
    def e_kn_per_m2(self) -> float:
        """Canonical m/kN alias; the numeric unit follows the caller's unit system."""
        return self.e_n_per_m2

    @property
    def g_kn_per_m2(self) -> float:
        return self.g_n_per_m2


@dataclass(frozen=True)
class Frame3DProperties:
    element_id: str
    node_ids: tuple[str, str]
    start_coordinates: tuple[float, float, float]
    end_coordinates: tuple[float, float, float]
    props: FrameProps
    local_axis_angle_deg: float = 0.0
    offset_i_global_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    offset_j_global_m: tuple[float, float, float] = (0.0, 0.0, 0.0)

    @property
    def end_points(self) -> tuple[np.ndarray, np.ndarray]:
        start = np.asarray(self.start_coordinates, dtype=float) + np.asarray(
            self.offset_i_global_m, dtype=float
        )
        end = np.asarray(self.end_coordinates, dtype=float) + np.asarray(
            self.offset_j_global_m, dtype=float
        )
        return start, end

    @property
    def length_m(self) -> float:
        start, end = self.end_points
        return float(np.linalg.norm(end - start))


def frame3d_properties_from_canonical(
    *,
    element: Mapping[str, Any],
    node_ids: tuple[str, str],
    start_coordinates: tuple[float, float, float],
    end_coordinates: tuple[float, float, float],
    material: Mapping[str, Any],
    section: Mapping[str, Any],
) -> Frame3DProperties:
    """Convert explicit canonical properties without inventing engineering data."""

    element_id = str(element.get("id", "")).strip()
    elastic = ElasticIsotropicMaterial.from_mapping(material)
    area = _required_positive(section, ("area", "A_m2"), "area", element_id)
    iy = _required_positive(section, ("iy", "Iy_m4"), "Iy", element_id)
    iz = _required_positive(section, ("iz", "Iz_m4"), "Iz", element_id)
    torsion = _required_positive(
        section,
        ("torsional_constant", "j", "J_m4"),
        "torsional constant J",
        element_id,
    )
    angle = _optional_float(element, ("local_axis_angle_deg", "angle_deg"), default=0.0)
    offset_i = _vector3(element.get("offset_i_global_m", element.get("offset_i")), "offset_i")
    offset_j = _vector3(element.get("offset_j_global_m", element.get("offset_j")), "offset_j")
    properties = Frame3DProperties(
        element_id=element_id,
        node_ids=node_ids,
        start_coordinates=start_coordinates,
        end_coordinates=end_coordinates,
        props=FrameProps(
            area_m2=area,
            e_n_per_m2=elastic.elastic_modulus,
            g_n_per_m2=elastic.shear_modulus,
            iy_m4=iy,
            iz_m4=iz,
            j_m4=torsion,
        ),
        local_axis_angle_deg=angle,
        offset_i_global_m=offset_i,
        offset_j_global_m=offset_j,
    )
    if properties.length_m <= 1.0e-12:
        raise ValueError(f"Element {element_id} has zero length after rigid offsets.")
    return properties


def local_frame_stiffness(props: FrameProps, length_m: float) -> np.ndarray:
    """Return the symmetric 12x12 local Euler-Bernoulli stiffness matrix."""

    length = float(length_m)
    if not np.isfinite(length) or length <= 0.0:
        raise ValueError("Frame element length must be positive.")
    k = np.zeros((12, 12), dtype=float)
    ea_l = props.e_n_per_m2 * props.area_m2 / length
    gj_l = props.g_n_per_m2 * props.j_m4 / length
    eiy = props.e_n_per_m2 * props.iy_m4
    eiz = props.e_n_per_m2 * props.iz_m4
    _add_symmetric_pair(k, 0, 6, ea_l)
    _add_symmetric_pair(k, 3, 9, gj_l)

    l2 = length * length
    l3 = l2 * length
    sub_z = np.array(
        [
            [12.0 * eiz / l3, 6.0 * eiz / l2, -12.0 * eiz / l3, 6.0 * eiz / l2],
            [6.0 * eiz / l2, 4.0 * eiz / length, -6.0 * eiz / l2, 2.0 * eiz / length],
            [-12.0 * eiz / l3, -6.0 * eiz / l2, 12.0 * eiz / l3, -6.0 * eiz / l2],
            [6.0 * eiz / l2, 2.0 * eiz / length, -6.0 * eiz / l2, 4.0 * eiz / length],
        ],
        dtype=float,
    )
    _scatter_submatrix(k, (1, 5, 7, 11), sub_z)
    sub_y = np.array(
        [
            [12.0 * eiy / l3, -6.0 * eiy / l2, -12.0 * eiy / l3, -6.0 * eiy / l2],
            [-6.0 * eiy / l2, 4.0 * eiy / length, 6.0 * eiy / l2, 2.0 * eiy / length],
            [-12.0 * eiy / l3, 6.0 * eiy / l2, 12.0 * eiy / l3, 6.0 * eiy / l2],
            [-6.0 * eiy / l2, 2.0 * eiy / length, 6.0 * eiy / l2, 4.0 * eiy / length],
        ],
        dtype=float,
    )
    _scatter_submatrix(k, (2, 4, 8, 10), sub_y)
    return 0.5 * (k + k.T)


def frame_rotation_matrix(
    start: np.ndarray,
    end: np.ndarray,
    *,
    roll_deg: float = 0.0,
) -> np.ndarray:
    x_axis = np.asarray(end, dtype=float) - np.asarray(start, dtype=float)
    norm = float(np.linalg.norm(x_axis))
    if norm <= 1.0e-12:
        raise ValueError("Frame element has zero chord length.")
    x_axis /= norm
    reference = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(x_axis, reference))) > 0.95:
        reference = np.array([0.0, 1.0, 0.0], dtype=float)
    y_axis = np.cross(reference, x_axis)
    y_axis /= float(np.linalg.norm(y_axis))
    z_axis = np.cross(x_axis, y_axis)
    z_axis /= float(np.linalg.norm(z_axis))
    if abs(float(roll_deg)) > 1.0e-14:
        angle = np.deg2rad(float(roll_deg))
        y_base = y_axis.copy()
        z_base = z_axis.copy()
        y_axis = np.cos(angle) * y_base + np.sin(angle) * z_base
        z_axis = -np.sin(angle) * y_base + np.cos(angle) * z_base
    return np.vstack([x_axis, y_axis, z_axis])


def frame_transform(rotation: np.ndarray) -> np.ndarray:
    transform = np.zeros((12, 12), dtype=float)
    for offset in (0, 3, 6, 9):
        transform[offset : offset + 3, offset : offset + 3] = rotation
    return transform


def transform_stiffness(k_local: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    """Transform a local 12x12 matrix into the global nodal frame."""
    transform = frame_transform(rotation)
    return transform.T @ np.asarray(k_local, dtype=float) @ transform


def rigid_end_offset_transform(
    offset_i: tuple[float, float, float] | np.ndarray,
    offset_j: tuple[float, float, float] | np.ndarray,
) -> np.ndarray:
    transform = np.eye(12, dtype=float)
    transform[0:3, 3:6] = -_skew(np.asarray(offset_i, dtype=float))
    transform[6:9, 9:12] = -_skew(np.asarray(offset_j, dtype=float))
    return transform


def frame3d_global_stiffness(properties: Frame3DProperties) -> np.ndarray:
    start, end = properties.end_points
    rotation = frame_rotation_matrix(start, end, roll_deg=properties.local_axis_angle_deg)
    transform = frame_transform(rotation)
    rigid = rigid_end_offset_transform(
        properties.offset_i_global_m, properties.offset_j_global_m
    )
    local = local_frame_stiffness(properties.props, properties.length_m)
    return rigid.T @ transform.T @ local @ transform @ rigid


def frame3d_local_end_forces(
    properties: Frame3DProperties,
    global_nodal_displacements: np.ndarray,
) -> np.ndarray:
    displacement = np.asarray(global_nodal_displacements, dtype=float)
    if displacement.shape != (12,):
        raise ValueError("Frame displacement vector must contain 12 values.")
    start, end = properties.end_points
    rotation = frame_rotation_matrix(start, end, roll_deg=properties.local_axis_angle_deg)
    transform = frame_transform(rotation)
    rigid = rigid_end_offset_transform(
        properties.offset_i_global_m, properties.offset_j_global_m
    )
    local_displacement = transform @ rigid @ displacement
    return local_frame_stiffness(properties.props, properties.length_m) @ local_displacement


def _add_symmetric_pair(matrix: np.ndarray, first: int, second: int, value: float) -> None:
    matrix[first, first] += value
    matrix[first, second] -= value
    matrix[second, first] -= value
    matrix[second, second] += value


def _scatter_submatrix(matrix: np.ndarray, indices: tuple[int, ...], values: np.ndarray) -> None:
    for row, global_row in enumerate(indices):
        for column, global_column in enumerate(indices):
            matrix[global_row, global_column] += float(values[row, column])


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = [float(value) for value in vector]
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]], dtype=float)


def _required_positive(
    payload: Mapping[str, Any],
    keys: tuple[str, ...],
    label: str,
    element_id: str,
) -> float:
    value = _optional_float(payload, keys, default=None)
    if value is None or not np.isfinite(value) or value <= 0.0:
        raise ValueError(
            f"Element {element_id} requires explicit positive section {label}; "
            "production fallback is disabled."
        )
    return value


def _optional_float(
    payload: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    default: float | None,
) -> float | None:
    for key in keys:
        if key not in payload or payload.get(key) is None:
            continue
        try:
            return float(payload[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
    return default


def _vector3(value: Any, label: str) -> tuple[float, float, float]:
    if value is None:
        return (0.0, 0.0, 0.0)
    if isinstance(value, Mapping):
        raw = [value.get("x", 0.0), value.get("y", 0.0), value.get("z", 0.0)]
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        raw = list(value)
    else:
        raise ValueError(f"{label} must be a three-component vector.")
    try:
        return tuple(float(component) for component in raw)  # type: ignore[return-value]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain numeric values.") from exc
