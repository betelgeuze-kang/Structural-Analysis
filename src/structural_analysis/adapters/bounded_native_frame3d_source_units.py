"""Fail-closed N-mm-MPa source normalization for one bounded native Frame3D member.

The ModelIR contract stores physical values in SI and records source units only as
provenance.  This adapter owns the preceding conversion for the deliberately small
single-member Frame3D source profile used by executable verification.  It accepts
raw engineering-unit values, creates a source-hash-bound ModelIR document, and
retains a deterministic manifest connecting both representations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import math
from typing import Any, Mapping, NoReturn

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir import ModelIRDocument, parse_model_ir_v2


BOUNDED_NATIVE_FRAME3D_SOURCE_SCHEMA_VERSION = (
    "bounded-native-frame3d-n-mm-mpa-source.v1"
)
BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_PROFILE = (
    "bounded_native_frame3d_n_mm_mpa_to_model_ir_v2.v1"
)
BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_CLAIM_BOUNDARY = (
    "Exact bounded N-mm-MPa source-to-ModelIR SI normalization for one linear "
    "Frame3D member; no external validation, design, medium-scale, or release "
    "authority is created."
)

_FORCE_COMPONENTS = ("FX", "FY", "FZ")
_MOMENT_COMPONENTS = ("MX", "MY", "MZ")
_TRANSLATION_DOFS = ("UX", "UY", "UZ")
_ROTATION_DOFS = ("RX", "RY", "RZ")
_MODEL_DOF_COMPONENTS = (*_TRANSLATION_DOFS, *_ROTATION_DOFS)
_LENGTH_TO_M = 1.0e-3
_STRESS_TO_PA = 1.0e6
_AREA_TO_M2 = 1.0e-6
_INERTIA_TO_M4 = 1.0e-12
_DENSITY_TO_KG_M3 = 1.0e9
_MOMENT_TO_N_M = 1.0e-3


class BoundedNativeFrame3DSourceNormalizationError(ValueError):
    """Stable failure for an invalid bounded engineering-unit source."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class BoundedNativeFrame3DSourceNormalization:
    """Immutable raw-source to normalized-ModelIR binding."""

    source_schema_version: str
    adapter_profile: str
    raw_source_sha256: str
    normalized_model_content_hash: str
    normalized_model_semantic_hash: str
    normalized_model_provenance_hash: str
    normalization_sha256: str
    _document: ModelIRDocument = field(repr=False, compare=False)

    @property
    def document(self) -> ModelIRDocument:
        return self._document

    def to_manifest(self) -> dict[str, Any]:
        return _manifest(self, include_hash=True)


def normalize_bounded_native_frame3d_n_mm_mpa_source_v1(
    raw_source: Mapping[str, Any],
) -> BoundedNativeFrame3DSourceNormalization:
    """Normalize one strict raw N-mm-MPa source into canonical SI ModelIR."""

    normalized = _build_normalization(raw_source)
    return validate_bounded_native_frame3d_source_normalization(
        normalized,
        raw_source=raw_source,
    )


def validate_bounded_native_frame3d_source_normalization(
    normalization: BoundedNativeFrame3DSourceNormalization,
    *,
    raw_source: Mapping[str, Any] | None = None,
) -> BoundedNativeFrame3DSourceNormalization:
    """Revalidate retained hashes and, when supplied, replay the raw conversion."""

    if type(normalization) is not BoundedNativeFrame3DSourceNormalization:
        _fail(
            "bounded_native_frame3d_normalization_type_invalid",
            "/",
            "Expected an exact bounded native Frame3D normalization binding.",
        )
    document = normalization.document
    if type(document) is not ModelIRDocument:
        _fail(
            "bounded_native_frame3d_normalized_document_invalid",
            "/normalized_model",
            "Retained normalized model must be an exact ModelIRDocument.",
        )
    if (
        normalization.source_schema_version
        != BOUNDED_NATIVE_FRAME3D_SOURCE_SCHEMA_VERSION
        or normalization.adapter_profile
        != BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_PROFILE
    ):
        _fail(
            "bounded_native_frame3d_normalization_contract_invalid",
            "/adapter_profile",
            "Unsupported source normalization contract.",
        )
    if (
        normalization.normalized_model_content_hash != document.content_hash
        or normalization.normalized_model_semantic_hash != document.semantic_hash
        or normalization.normalized_model_provenance_hash != document.provenance_hash
    ):
        _fail(
            "bounded_native_frame3d_normalized_model_hash_mismatch",
            "/normalized_model_content_hash",
            "Retained ModelIR hashes do not match the normalized document.",
        )
    payload = document.to_dict()
    provenance = payload["provenance"]
    if (
        provenance["source_sha256"] != normalization.raw_source_sha256
        or provenance["normalizer_id"]
        != BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_PROFILE
        or provenance["normalizer_version"] != "1"
        or provenance["source_units"]
        != {
            "length": "mm",
            "force": "N",
            "mass": "kg",
            "time": "s",
            "rotation": "rad",
        }
        or provenance["unit_scales_to_si"]
        != {
            "length_to_m": _LENGTH_TO_M,
            "force_to_n": 1.0,
            "mass_to_kg": 1.0,
            "time_to_s": 1.0,
            "rotation_to_rad": 1.0,
        }
    ):
        _fail(
            "bounded_native_frame3d_raw_source_binding_mismatch",
            "/normalized_model/provenance",
            "Normalized ModelIR provenance is not bound to the raw source profile.",
        )
    if normalization.normalization_sha256 != canonical_hash(
        _manifest(normalization, include_hash=False)
    ):
        _fail(
            "bounded_native_frame3d_normalization_hash_mismatch",
            "/normalization_sha256",
            "Normalization manifest hash does not match its binding fields.",
        )
    if raw_source is not None:
        expected = _build_normalization(raw_source)
        if (
            _manifest(normalization, include_hash=True)
            != _manifest(expected, include_hash=True)
            or normalization.document.canonical_json != expected.document.canonical_json
        ):
            _fail(
                "bounded_native_frame3d_normalization_replay_mismatch",
                "/normalized_model",
                "Retained normalization does not exactly replay from the raw source.",
            )
    return normalization


def _build_normalization(
    raw_source: Mapping[str, Any],
) -> BoundedNativeFrame3DSourceNormalization:
    root = _object(
        raw_source,
        "/",
        {
            "schema_version",
            "source_ref",
            "model_id",
            "capability_profile",
            "node_i",
            "node_j",
            "material",
            "section",
            "element",
            "constraint",
            "load_pattern",
        },
    )
    if root["schema_version"] != BOUNDED_NATIVE_FRAME3D_SOURCE_SCHEMA_VERSION:
        _fail(
            "bounded_native_frame3d_source_schema_unsupported",
            "/schema_version",
            "Unsupported bounded native Frame3D source schema.",
        )
    source_ref = _text(root["source_ref"], "/source_ref")
    model_id = _text(root["model_id"], "/model_id")
    if root["capability_profile"] != "engine_v2_phase0_linear_3d":
        _fail(
            "bounded_native_frame3d_source_profile_unsupported",
            "/capability_profile",
            "Only the native linear Frame3D ModelIR profile is supported.",
        )

    node_rows = [
        _node(root["node_i"], "/node_i", 0),
        _node(root["node_j"], "/node_j", 1),
    ]
    material = _material(root["material"])
    section = _section(root["section"])
    element = _element(root["element"])
    constraint = _constraint(root["constraint"])
    load_pattern = _load_pattern(root["load_pattern"])

    raw_source_sha256 = canonical_hash(dict(root))
    payload = {
        "schema_version": "structural-analysis-model-ir.v2",
        "model_id": model_id,
        "capability_profile": "engine_v2_phase0_linear_3d",
        "provenance": {
            "source_format": "generated",
            "source_ref": source_ref,
            "source_sha256": raw_source_sha256,
            "normalizer_id": BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_PROFILE,
            "normalizer_version": "1",
            "source_units": {
                "length": "mm",
                "force": "N",
                "mass": "kg",
                "time": "s",
                "rotation": "rad",
            },
            "unit_scales_to_si": {
                "length_to_m": _LENGTH_TO_M,
                "force_to_n": 1.0,
                "mass_to_kg": 1.0,
                "time_to_s": 1.0,
                "rotation_to_rad": 1.0,
            },
            "extensions": {},
        },
        "units": {
            "length": "m",
            "force": "N",
            "mass": "kg",
            "time": "s",
            "rotation": "rad",
        },
        "coordinate_system": {
            "frame_id": "global",
            "axis_order": ["X", "Y", "Z"],
            "up_axis": "Z",
            "handedness": "right",
            "origin_m": [0.0, 0.0, 0.0],
        },
        "dof_components": list(_MODEL_DOF_COMPONENTS),
        "nodes": node_rows,
        "materials": [material],
        "sections": [section],
        "elements": [element],
        "constraints": [constraint],
        "load_patterns": [load_pattern],
        "load_combinations": [],
        "time_functions": [],
        "construction_stages": [],
        "roundtrip_map": [],
        "unsupported_features": [],
        "extensions": {},
    }
    document = parse_model_ir_v2(payload, require_analysis_ready=True)
    provisional = BoundedNativeFrame3DSourceNormalization(
        source_schema_version=BOUNDED_NATIVE_FRAME3D_SOURCE_SCHEMA_VERSION,
        adapter_profile=BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_PROFILE,
        raw_source_sha256=raw_source_sha256,
        normalized_model_content_hash=document.content_hash,
        normalized_model_semantic_hash=document.semantic_hash,
        normalized_model_provenance_hash=document.provenance_hash,
        normalization_sha256="sha256:" + "0" * 64,
        _document=document,
    )
    return BoundedNativeFrame3DSourceNormalization(
        **{
            **provisional.__dict__,
            "normalization_sha256": canonical_hash(
                _manifest(provisional, include_hash=False)
            ),
        }
    )


def _node(value: Any, path: str, index: int) -> dict[str, Any]:
    row = _object(value, path, {"id", "coordinates_mm"})
    stable_id = _text(row["id"], f"{path}/id")
    return {
        "id": stable_id,
        "index": index,
        "coordinates_m": [
            _scaled_number(component, f"{path}/coordinates_mm/{index}", "0.001")
            for index, component in enumerate(
                _raw_vector(row["coordinates_mm"], f"{path}/coordinates_mm")
            )
        ],
        "source_id": f"{path.removeprefix('/')}:{stable_id}",
        "extensions": {},
    }


def _material(value: Any) -> dict[str, Any]:
    path = "/material"
    row = _object(
        value,
        path,
        {"id", "elastic_modulus_mpa", "poisson_ratio", "density_kg_mm3"},
    )
    stable_id = _text(row["id"], f"{path}/id")
    return {
        "id": stable_id,
        "index": 0,
        "law_id": "linear_elastic_isotropic",
        "parameter_set_version": "1",
        "parameters": {
            "elastic_modulus_pa": _scaled_number(
                row["elastic_modulus_mpa"],
                f"{path}/elastic_modulus_mpa",
                "1000000",
                positive=True,
            ),
            "poisson_ratio": _number(row["poisson_ratio"], f"{path}/poisson_ratio"),
            "density_kg_m3": _scaled_number(
                row["density_kg_mm3"],
                f"{path}/density_kg_mm3",
                "1000000000",
                positive=True,
            ),
        },
        "state_schema": {
            "stateful": False,
            "state_update_epoch": "none",
            "supports_trial_commit_rollback": True,
        },
        "source_id": f"material:{stable_id}",
        "extensions": {},
    }


def _section(value: Any) -> dict[str, Any]:
    path = "/section"
    row = _object(
        value,
        path,
        {
            "id",
            "area_mm2",
            "iy_mm4",
            "iz_mm4",
            "torsional_constant_mm4",
            "shear_area_y_mm2",
            "shear_area_z_mm2",
        },
    )
    stable_id = _text(row["id"], f"{path}/id")
    return {
        "id": stable_id,
        "index": 0,
        "family_id": "frame_3d",
        "parameter_set_version": "1",
        "parameters": {
            "area_m2": _scaled_number(
                row["area_mm2"], f"{path}/area_mm2", "0.000001", positive=True
            ),
            "iy_m4": _scaled_number(
                row["iy_mm4"], f"{path}/iy_mm4", "0.000000000001", positive=True
            ),
            "iz_m4": _scaled_number(
                row["iz_mm4"], f"{path}/iz_mm4", "0.000000000001", positive=True
            ),
            "torsional_constant_m4": _scaled_number(
                row["torsional_constant_mm4"],
                f"{path}/torsional_constant_mm4",
                "0.000000000001",
                positive=True,
            ),
            "shear_area_y_m2": _scaled_number(
                row["shear_area_y_mm2"],
                f"{path}/shear_area_y_mm2",
                "0.000001",
                positive=True,
            ),
            "shear_area_z_m2": _scaled_number(
                row["shear_area_z_mm2"],
                f"{path}/shear_area_z_mm2",
                "0.000001",
                positive=True,
            ),
        },
        "source_id": f"section:{stable_id}",
        "extensions": {},
    }


def _element(value: Any) -> dict[str, Any]:
    path = "/element"
    row = _object(
        value,
        path,
        {
            "id",
            "node_ids",
            "material_id",
            "section_id",
            "formulation",
            "local_axis_rotation_rad",
            "offset_i_mm",
            "offset_j_mm",
            "releases_i",
            "releases_j",
        },
    )
    node_ids = _string_array(row["node_ids"], f"{path}/node_ids", length=2)
    releases_i = _dof_array(row["releases_i"], f"{path}/releases_i")
    releases_j = _dof_array(row["releases_j"], f"{path}/releases_j")
    formulation = row["formulation"]
    if formulation not in {"euler_bernoulli_3d", "linear_timoshenko_frame3d"}:
        _fail(
            "bounded_native_frame3d_source_formulation_unsupported",
            f"{path}/formulation",
            "Unsupported linear Frame3D formulation.",
        )
    stable_id = _text(row["id"], f"{path}/id")
    return {
        "id": stable_id,
        "index": 0,
        "type": "frame_3d",
        "formulation": formulation,
        "node_ids": node_ids,
        "material_id": _text(row["material_id"], f"{path}/material_id"),
        "section_id": _text(row["section_id"], f"{path}/section_id"),
        "local_axis_rotation_rad": _number(
            row["local_axis_rotation_rad"], f"{path}/local_axis_rotation_rad"
        ),
        "offsets": {
            "i_global_m": [
                _scaled_number(component, f"{path}/offset_i_mm/{index}", "0.001")
                for index, component in enumerate(
                    _raw_vector(row["offset_i_mm"], f"{path}/offset_i_mm")
                )
            ],
            "j_global_m": [
                _scaled_number(component, f"{path}/offset_j_mm/{index}", "0.001")
                for index, component in enumerate(
                    _raw_vector(row["offset_j_mm"], f"{path}/offset_j_mm")
                )
            ],
        },
        "releases": {"i": releases_i, "j": releases_j},
        "source_id": f"element:{stable_id}",
        "extensions": {},
    }


def _constraint(value: Any) -> dict[str, Any]:
    path = "/constraint"
    row = _object(
        value,
        path,
        {
            "id",
            "node_id",
            "dofs",
            "prescribed_translations_mm",
            "prescribed_rotations_rad",
        },
    )
    dofs = _dof_array(row["dofs"], f"{path}/dofs")
    translations = _component_object(
        row["prescribed_translations_mm"],
        f"{path}/prescribed_translations_mm",
        _TRANSLATION_DOFS,
    )
    rotations = _component_object(
        row["prescribed_rotations_rad"],
        f"{path}/prescribed_rotations_rad",
        _ROTATION_DOFS,
    )
    prescribed = {
        dof: (
            _scaled_number(
                translations[dof],
                f"{path}/prescribed_translations_mm/{dof}",
                "0.001",
            )
            if dof in translations
            else rotations[dof]
        )
        for dof in dofs
    }
    stable_id = _text(row["id"], f"{path}/id")
    return {
        "id": stable_id,
        "index": 0,
        "type": "fixed_dofs",
        "node_id": _text(row["node_id"], f"{path}/node_id"),
        "dofs": dofs,
        "prescribed_values_si": prescribed,
        "source_id": f"constraint:{stable_id}",
        "extensions": {},
    }


def _load_pattern(value: Any) -> dict[str, Any]:
    path = "/load_pattern"
    row = _object(value, path, {"id", "self_weight", "nodal_load"})
    load = _object(
        row["nodal_load"],
        f"{path}/nodal_load",
        {"id", "node_id", "force_n", "moment_n_mm"},
    )
    forces = _component_object(
        load["force_n"], f"{path}/nodal_load/force_n", _FORCE_COMPONENTS
    )
    moments = _component_object(
        load["moment_n_mm"],
        f"{path}/nodal_load/moment_n_mm",
        _MOMENT_COMPONENTS,
    )
    load_id = _text(load["id"], f"{path}/nodal_load/id")
    pattern_id = _text(row["id"], f"{path}/id")
    return {
        "id": pattern_id,
        "index": 0,
        "analysis_type": "linear_static",
        "self_weight": _vector(row["self_weight"], f"{path}/self_weight"),
        "nodal_loads": [
            {
                "id": load_id,
                "index": 0,
                "node_id": _text(load["node_id"], f"{path}/nodal_load/node_id"),
                "components_si": {
                    **forces,
                    **{
                        component: _scaled_number(
                            moments[component],
                            f"{path}/nodal_load/moment_n_mm/{component}",
                            "0.001",
                        )
                        for component in _MOMENT_COMPONENTS
                    },
                },
                "source_id": f"nodal_load:{load_id}",
                "extensions": {},
            }
        ],
        "uniform_member_loads": [],
        "source_id": f"load_pattern:{pattern_id}",
        "extensions": {},
    }


def _manifest(
    normalization: BoundedNativeFrame3DSourceNormalization,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "source_schema_version": normalization.source_schema_version,
        "adapter_profile": normalization.adapter_profile,
        "raw_source_sha256": normalization.raw_source_sha256,
        "normalized_model_content_hash": normalization.normalized_model_content_hash,
        "normalized_model_semantic_hash": normalization.normalized_model_semantic_hash,
        "normalized_model_provenance_hash": normalization.normalized_model_provenance_hash,
        "unit_conversions": {
            "length_mm_to_m": _LENGTH_TO_M,
            "stress_mpa_to_pa": _STRESS_TO_PA,
            "area_mm2_to_m2": _AREA_TO_M2,
            "inertia_mm4_to_m4": _INERTIA_TO_M4,
            "density_kg_mm3_to_kg_m3": _DENSITY_TO_KG_M3,
            "force_n_to_n": 1.0,
            "moment_n_mm_to_n_m": _MOMENT_TO_N_M,
            "rotation_rad_to_rad": 1.0,
        },
        "claim_boundary": BOUNDED_NATIVE_FRAME3D_SOURCE_NORMALIZATION_CLAIM_BOUNDARY,
    }
    if include_hash:
        manifest["normalization_sha256"] = normalization.normalization_sha256
    return manifest


def _object(value: Any, path: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(
            "bounded_native_frame3d_source_object_invalid",
            path,
            "Expected an object.",
        )
    row = dict(value)
    if set(row) != keys:
        _fail(
            "bounded_native_frame3d_source_fields_invalid",
            path,
            f"Expected fields {sorted(keys)}, received {sorted(row)}.",
        )
    return row


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(
            "bounded_native_frame3d_source_text_invalid",
            path,
            "Expected a non-empty string.",
        )
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "bounded_native_frame3d_source_number_invalid",
            path,
            "Expected an exact integer or binary64 number.",
        )
    try:
        result = float(value)
    except OverflowError:
        result = math.inf
    if not math.isfinite(result):
        _fail(
            "bounded_native_frame3d_source_number_invalid",
            path,
            "Expected a finite binary64 number.",
        )
    if type(value) is int and int(result) != value:
        _fail(
            "bounded_native_frame3d_source_integer_binary64_loss",
            path,
            "Integer source value cannot be represented exactly as binary64.",
        )
    return result


def _scaled_number(
    value: Any,
    path: str,
    decimal_factor: str,
    *,
    positive: bool = False,
) -> float:
    source = _number(value, path)
    if positive and source <= 0.0:
        _fail(
            "bounded_native_frame3d_source_positive_number_required",
            path,
            "Expected a positive number.",
        )
    result = float(Decimal(str(value)) * Decimal(decimal_factor))
    if not math.isfinite(result):  # pragma: no cover - finite source and fixed factors
        _fail(
            "bounded_native_frame3d_source_number_invalid",
            path,
            "Normalized number is not finite binary64.",
        )
    return result


def _raw_vector(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list) or len(value) != 3:
        _fail(
            "bounded_native_frame3d_source_vector_invalid",
            path,
            "Expected exactly three numeric components.",
        )
    for index, component in enumerate(value):
        _number(component, f"{path}/{index}")
    return list(value)


def _vector(value: Any, path: str) -> list[float]:
    return [
        _number(component, f"{path}/{index}")
        for index, component in enumerate(_raw_vector(value, path))
    ]


def _string_array(value: Any, path: str, *, length: int | None = None) -> list[str]:
    if not isinstance(value, list) or (length is not None and len(value) != length):
        _fail(
            "bounded_native_frame3d_source_array_invalid",
            path,
            "Expected a string array with the required length.",
        )
    result = [
        _text(component, f"{path}/{index}") for index, component in enumerate(value)
    ]
    if len(result) != len(set(result)):
        _fail(
            "bounded_native_frame3d_source_array_duplicate",
            path,
            "String array entries must be unique.",
        )
    return result


def _dof_array(value: Any, path: str) -> list[str]:
    result = _string_array(value, path)
    if any(component not in _MODEL_DOF_COMPONENTS for component in result):
        _fail(
            "bounded_native_frame3d_source_dof_invalid",
            path,
            "Unsupported structural degree of freedom.",
        )
    return result


def _component_object(
    value: Any,
    path: str,
    components: tuple[str, ...],
) -> dict[str, float]:
    row = _object(value, path, set(components))
    return {
        component: _number(row[component], f"{path}/{component}")
        for component in components
    }


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedNativeFrame3DSourceNormalizationError(code, path, detail)
