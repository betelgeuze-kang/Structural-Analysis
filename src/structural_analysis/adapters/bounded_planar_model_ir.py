"""Typed non-core ModelIR v2 adapter for the bounded planar frame alpha profile."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from collections.abc import Mapping
from typing import Any, NoReturn

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model.schema import CanonicalModel
from structural_analysis.model_ir.loader import parse_model_ir_v2
from structural_analysis.model_ir.types import ModelIRDocument
from structural_analysis.units.schema import CoordinateSystem, UnitSystem


BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILE = "bounded_planar_frame_alpha"
PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE = "planar_frame_verified_alpha.v1"
BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILES = (
    BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILE,
    PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE,
)
BOUNDED_PLANAR_MODEL_IR_ADAPTER_SCHEMA_VERSION = "bounded-planar-model-ir-adapter.v1"
BOUNDED_PLANAR_MODEL_IR_ADAPTER_PROFILE = (
    "model_ir_v2_to_corotational_connected_frame2d.v1"
)
BOUNDED_PLANAR_MODEL_IR_DOF_COMPONENTS = ("UX", "UY", "RZ")
BOUNDED_PLANAR_MODEL_IR_INACTIVE_DOF_COMPONENTS = ("UZ", "RX", "RY")
_COMPONENT_ORDER = ("UX", "UY", "UZ", "RX", "RY", "RZ")
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_ADAPTER_MANIFEST_KEYS = {
    "schema_version",
    "adapter_profile",
    "adapter_hash",
    "model_ir_content_hash",
    "model_ir_semantic_hash",
    "model_ir_provenance_hash",
    "load_pattern_id",
    "canonical_model_checksum",
    "node_ids",
    "member_ids",
    "active_dof_components",
    "inactive_dof_components",
    "unit_conversion_hash",
    "entity_mapping_hash",
    "claim_boundary",
}


class BoundedPlanarModelIRAdapterError(ValueError):
    """Fail-closed adapter error with a stable code and JSON-pointer path."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class BoundedPlanarModelIRAdapter:
    schema_version: str
    adapter_profile: str
    adapter_hash: str
    model_ir_content_hash: str
    model_ir_semantic_hash: str
    model_ir_provenance_hash: str
    load_pattern_id: str
    canonical_model_checksum: str
    node_ids: tuple[str, ...]
    member_ids: tuple[str, ...]
    active_dof_components: tuple[str, ...]
    inactive_dof_components: tuple[str, ...]
    unit_conversion_hash: str
    entity_mapping_hash: str
    _canonical_model: CanonicalModel = field(repr=False, compare=False)

    @property
    def canonical_model(self) -> CanonicalModel:
        """Return a detached snapshot so callers cannot mutate retained evidence."""

        return self._canonical_model.detached_analysis_snapshot()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_profile": self.adapter_profile,
            "adapter_hash": self.adapter_hash,
            "model_ir_content_hash": self.model_ir_content_hash,
            "model_ir_semantic_hash": self.model_ir_semantic_hash,
            "model_ir_provenance_hash": self.model_ir_provenance_hash,
            "load_pattern_id": self.load_pattern_id,
            "canonical_model_checksum": self.canonical_model_checksum,
            "node_ids": list(self.node_ids),
            "member_ids": list(self.member_ids),
            "active_dof_components": list(self.active_dof_components),
            "inactive_dof_components": list(self.inactive_dof_components),
            "unit_conversion_hash": self.unit_conversion_hash,
            "entity_mapping_hash": self.entity_mapping_hash,
            "claim_boundary": (
                "Exact bounded-profile input projection only. The adapter creates "
                "no convergence, numerical-result, engineering-design, external-V&V, "
                "release, or commercial authority."
            ),
        }


def adapt_bounded_planar_model_ir_v2(
    document: ModelIRDocument,
) -> BoundedPlanarModelIRAdapter:
    """Project a validated bounded-planar ModelIR document to CanonicalModel.

    The source document remains the authority owner.  Every supported nonlinear
    field is explicit in ModelIR v2; this function performs only deterministic SI
    unit conversion and the declared six-DOF-to-planar component projection.
    """

    if type(document) is not ModelIRDocument:
        _fail(
            "bounded_planar_model_ir_document_type_invalid",
            "/",
            "Expected an exact ModelIRDocument.",
        )
    payload = document.to_dict()
    reparsed = parse_model_ir_v2(payload, require_analysis_ready=True)
    for name in ("content_hash", "semantic_hash", "provenance_hash"):
        if getattr(document, name) != getattr(reparsed, name):
            _fail(
                "bounded_planar_model_ir_document_hash_mismatch",
                f"/{name}",
                "Retained ModelIR document hash does not match canonical content.",
            )
    if reparsed.capability_profile not in BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILES:
        _fail(
            "bounded_planar_model_ir_profile_unsupported",
            "/capability_profile",
            "ModelIR document is not a supported bounded planar frame profile.",
        )
    if len(payload["load_patterns"]) != 1:  # pragma: no cover - schema invariant
        _fail(
            "bounded_planar_model_ir_load_pattern_count_invalid",
            "/load_patterns",
            "Exactly one bounded nonlinear load pattern is required.",
        )
    pattern = payload["load_patterns"][0]
    node_ids = tuple(str(row["id"]) for row in payload["nodes"])
    member_ids = tuple(str(row["id"]) for row in payload["elements"])

    materials = [_canonical_material(row) for row in payload["materials"]]
    sections = [_canonical_section(row) for row in payload["sections"]]
    elements = [_canonical_element(row) for row in payload["elements"]]
    supports = _canonical_supports(payload["constraints"], node_ids=node_ids)
    loads = [_canonical_load(row) for row in pattern["nodal_loads"]]
    canonical = CanonicalModel(
        schema_version="structural-analysis-canonical-model.v1",
        source_path=str(payload["provenance"]["source_ref"]),
        source_format="model_ir_v2",
        input_checksum=reparsed.content_hash,
        units=UnitSystem(length="m", force="kN"),
        coordinate_system=CoordinateSystem(
            axis_order=("X", "Y", "Z"),
            up_axis="Z",
        ),
        nodes=[
            {
                "id": str(row["id"]),
                "coordinates": [float(value) for value in row["coordinates_m"]],
            }
            for row in payload["nodes"]
        ],
        elements=elements,
        materials=materials,
        sections=sections,
        loads=loads,
        supports=supports,
        unsupported_features=[],
        warnings=[],
        metadata={"case_id": str(payload["model_id"])},
    )
    unit_conversion_hash = canonical_hash(
        {
            "length": "m_to_m_exact",
            "force": "N_to_kN_divide_1000",
            "moment": "N_m_to_kN_m_divide_1000",
            "stress": "Pa_to_MPa_divide_1000000",
            "distributed_load": "N_per_m_to_kN_per_m_divide_1000",
            "rotation": "rad_to_rad_exact",
        }
    )
    entity_mapping_hash = canonical_hash(
        {
            "node_ids": list(node_ids),
            "member_ids": list(member_ids),
            "material_ids": [str(row["id"]) for row in payload["materials"]],
            "section_ids": [str(row["id"]) for row in payload["sections"]],
            "constraint_ids": [str(row["id"]) for row in payload["constraints"]],
            "load_pattern_id": str(pattern["id"]),
            "nodal_load_ids": [str(row["id"]) for row in pattern["nodal_loads"]],
            "source_dof_components": list(payload["dof_components"]),
            "active_dof_components": list(BOUNDED_PLANAR_MODEL_IR_DOF_COMPONENTS),
            "inactive_dof_components": list(
                BOUNDED_PLANAR_MODEL_IR_INACTIVE_DOF_COMPONENTS
            ),
        }
    )
    provisional = BoundedPlanarModelIRAdapter(
        schema_version=BOUNDED_PLANAR_MODEL_IR_ADAPTER_SCHEMA_VERSION,
        adapter_profile=BOUNDED_PLANAR_MODEL_IR_ADAPTER_PROFILE,
        adapter_hash="sha256:" + "0" * 64,
        model_ir_content_hash=reparsed.content_hash,
        model_ir_semantic_hash=reparsed.semantic_hash,
        model_ir_provenance_hash=reparsed.provenance_hash,
        load_pattern_id=str(pattern["id"]),
        canonical_model_checksum=canonical.canonical_model_checksum,
        node_ids=node_ids,
        member_ids=member_ids,
        active_dof_components=BOUNDED_PLANAR_MODEL_IR_DOF_COMPONENTS,
        inactive_dof_components=BOUNDED_PLANAR_MODEL_IR_INACTIVE_DOF_COMPONENTS,
        unit_conversion_hash=unit_conversion_hash,
        entity_mapping_hash=entity_mapping_hash,
        _canonical_model=canonical.detached_analysis_snapshot(),
    )
    adapter = BoundedPlanarModelIRAdapter(
        **{
            **provisional.__dict__,
            "adapter_hash": canonical_hash(
                _adapter_payload(provisional, include_adapter_hash=False)
            ),
        }
    )
    return validate_bounded_planar_model_ir_adapter(adapter, document=document)


def validate_bounded_planar_model_ir_adapter(
    adapter: BoundedPlanarModelIRAdapter,
    *,
    document: ModelIRDocument | None = None,
) -> BoundedPlanarModelIRAdapter:
    if type(adapter) is not BoundedPlanarModelIRAdapter:
        _fail(
            "bounded_planar_model_ir_adapter_type_invalid",
            "/",
            "Expected a BoundedPlanarModelIRAdapter.",
        )
    if adapter.schema_version != BOUNDED_PLANAR_MODEL_IR_ADAPTER_SCHEMA_VERSION:
        _fail(
            "bounded_planar_model_ir_adapter_schema_invalid",
            "/schema_version",
            "Unsupported bounded planar adapter schema.",
        )
    if adapter.adapter_profile != BOUNDED_PLANAR_MODEL_IR_ADAPTER_PROFILE:
        _fail(
            "bounded_planar_model_ir_adapter_profile_invalid",
            "/adapter_profile",
            "Unsupported bounded planar adapter profile.",
        )
    validate_bounded_planar_model_ir_adapter_manifest(adapter.to_dict())
    if (
        adapter.canonical_model_checksum
        != adapter._canonical_model.canonical_model_checksum
    ):
        _fail(
            "bounded_planar_model_ir_canonical_hash_mismatch",
            "/canonical_model_checksum",
            "Canonical model content changed after adaptation.",
        )
    expected_hash = canonical_hash(
        _adapter_payload(adapter, include_adapter_hash=False)
    )
    if adapter.adapter_hash != expected_hash:
        _fail(
            "bounded_planar_model_ir_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash does not match canonical receipt content.",
        )
    if document is not None:
        if type(document) is not ModelIRDocument:
            _fail(
                "bounded_planar_model_ir_document_type_invalid",
                "/document",
                "Expected an exact ModelIRDocument.",
            )
        if (
            adapter.model_ir_content_hash != document.content_hash
            or adapter.model_ir_semantic_hash != document.semantic_hash
            or adapter.model_ir_provenance_hash != document.provenance_hash
        ):
            _fail(
                "bounded_planar_model_ir_source_binding_mismatch",
                "/model_ir_content_hash",
                "Adapter belongs to another ModelIR document.",
            )
    return adapter


def validate_bounded_planar_model_ir_adapter_manifest(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a detached adapter receipt and its canonical self-hash."""

    if not isinstance(payload, Mapping) or set(payload) != _ADAPTER_MANIFEST_KEYS:
        _fail(
            "bounded_planar_model_ir_adapter_manifest_fields_invalid",
            "/",
            "Detached adapter receipt has missing or unknown fields.",
        )
    normalized = json.loads(json.dumps(dict(payload), allow_nan=False))
    if normalized["schema_version"] != BOUNDED_PLANAR_MODEL_IR_ADAPTER_SCHEMA_VERSION:
        _fail(
            "bounded_planar_model_ir_adapter_schema_invalid",
            "/schema_version",
            "Unsupported bounded planar adapter schema.",
        )
    if normalized["adapter_profile"] != BOUNDED_PLANAR_MODEL_IR_ADAPTER_PROFILE:
        _fail(
            "bounded_planar_model_ir_adapter_profile_invalid",
            "/adapter_profile",
            "Unsupported bounded planar adapter profile.",
        )
    for key in (
        "adapter_hash",
        "model_ir_content_hash",
        "model_ir_semantic_hash",
        "model_ir_provenance_hash",
        "canonical_model_checksum",
        "unit_conversion_hash",
        "entity_mapping_hash",
    ):
        if not isinstance(normalized[key], str) or not _HASH_PATTERN.fullmatch(
            normalized[key]
        ):
            _fail(
                "bounded_planar_model_ir_adapter_hash_field_invalid",
                f"/{key}",
                "Expected a lowercase sha256 hash.",
            )
    if not isinstance(
        normalized["load_pattern_id"], str
    ) or not _STABLE_ID_PATTERN.fullmatch(normalized["load_pattern_id"]):
        _fail(
            "bounded_planar_model_ir_load_pattern_id_invalid",
            "/load_pattern_id",
            "Expected a stable load-pattern ID.",
        )
    for key in ("node_ids", "member_ids"):
        values = normalized[key]
        if (
            not isinstance(values, list)
            or not values
            or len(values) != len(set(values))
            or any(
                not isinstance(value, str) or not _STABLE_ID_PATTERN.fullmatch(value)
                for value in values
            )
        ):
            _fail(
                "bounded_planar_model_ir_entity_ids_invalid",
                f"/{key}",
                "Entity IDs must be non-empty, unique, stable-ID lists.",
            )
    if normalized["active_dof_components"] != list(
        BOUNDED_PLANAR_MODEL_IR_DOF_COMPONENTS
    ) or normalized["inactive_dof_components"] != list(
        BOUNDED_PLANAR_MODEL_IR_INACTIVE_DOF_COMPONENTS
    ):
        _fail(
            "bounded_planar_model_ir_dof_projection_invalid",
            "/active_dof_components",
            "Adapter DOF projection differs from the bounded profile.",
        )
    if (
        not isinstance(normalized["claim_boundary"], str)
        or not normalized["claim_boundary"].strip()
    ):
        _fail(
            "bounded_planar_model_ir_claim_boundary_invalid",
            "/claim_boundary",
            "Adapter claim boundary must be non-empty.",
        )
    body = dict(normalized)
    claimed = body.pop("adapter_hash")
    if claimed != canonical_hash(body):
        _fail(
            "bounded_planar_model_ir_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash does not match canonical receipt content.",
        )
    return normalized


def _canonical_material(row: dict[str, Any]) -> dict[str, Any]:
    parameters = row["parameters"]
    if row["law_id"] == "bilinear_combined_hardening_steel":
        return {
            "id": str(row["id"]),
            "type": "bilinear_combined_hardening_steel",
            "elastic_modulus_mpa": float(parameters["elastic_modulus_pa"]) / 1.0e6,
            "yield_stress_mpa": float(parameters["yield_stress_pa"]) / 1.0e6,
            "isotropic_hardening_modulus_mpa": (
                float(parameters["isotropic_hardening_modulus_pa"]) / 1.0e6
            ),
            "kinematic_hardening_modulus_mpa": (
                float(parameters["kinematic_hardening_modulus_pa"]) / 1.0e6
            ),
            "yield_tolerance_mpa": float(parameters["yield_tolerance_pa"]) / 1.0e6,
        }
    return {
        "id": str(row["id"]),
        "type": "asymmetric_concrete_damage",
        "elastic_modulus_mpa": float(parameters["elastic_modulus_pa"]) / 1.0e6,
        "tensile_strength_mpa": float(parameters["tensile_strength_pa"]) / 1.0e6,
        "compressive_strength_mpa": float(parameters["compressive_strength_pa"])
        / 1.0e6,
        "tensile_softening_rate": float(parameters["tensile_softening_rate"]),
        "compressive_softening_rate": float(parameters["compressive_softening_rate"]),
        "history_tolerance": float(parameters["history_tolerance"]),
    }


def _canonical_section(row: dict[str, Any]) -> dict[str, Any]:
    parameters = row["parameters"]
    return {
        "id": str(row["id"]),
        "type": "rectangular_rc_fiber_section",
        "width_m": float(parameters["width_m"]),
        "depth_m": float(parameters["depth_m"]),
        "cover_m": float(parameters["cover_m"]),
        "concrete_layer_count": int(parameters["concrete_layer_count"]),
        "top_bar_count": int(parameters["top_bar_count"]),
        "bottom_bar_count": int(parameters["bottom_bar_count"]),
        "bar_area_m2": float(parameters["bar_area_m2"]),
        "steel_material": str(row["steel_material_id"]),
        "concrete_material": str(row["concrete_material_id"]),
    }


def _canonical_element(row: dict[str, Any]) -> dict[str, Any]:
    offsets = row["offsets"]
    member_load = row["uniform_distributed_load_local"]
    return {
        "id": str(row["id"]),
        "type": "stateful_corotational_rc_fiber_frame2d",
        "nodes": [str(value) for value in row["node_ids"]],
        "section": str(row["section_id"]),
        "integration_order": int(row["integration_order"]),
        "rigid_offsets_global_m": {
            "i": [float(value) for value in offsets["i_global_m"][:2]],
            "j": [float(value) for value in offsets["j_global_m"][:2]],
        },
        "end_releases": {
            "i": [str(value) for value in row["releases"]["i"]],
            "j": [str(value) for value in row["releases"]["j"]],
        },
        "uniform_distributed_load_local": {
            "basis": "initial_member_local",
            "behavior": "dead",
            "qx_kN_per_m": float(member_load["qx_n_per_m"]) / 1.0e3,
            "qy_kN_per_m": float(member_load["qy_n_per_m"]) / 1.0e3,
        },
    }


def _canonical_supports(
    constraints: list[dict[str, Any]],
    *,
    node_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    active = set(BOUNDED_PLANAR_MODEL_IR_DOF_COMPONENTS)
    by_node: dict[str, dict[str, Any]] = {
        node_id: {"dofs": set(), "prescribed_values": {}} for node_id in node_ids
    }
    for row in constraints:
        target = by_node[str(row["node_id"])]
        for component in row["dofs"]:
            if component in active:
                target["dofs"].add(str(component))
        for component, value in row["prescribed_values_si"].items():
            if component in active:
                target["prescribed_values"][str(component)] = float(value)
    supports: list[dict[str, Any]] = []
    for node_id in node_ids:
        target = by_node[node_id]
        dofs = [
            component for component in _COMPONENT_ORDER if component in target["dofs"]
        ]
        if not dofs:
            continue
        support: dict[str, Any] = {"node": node_id, "dofs": dofs}
        if target["prescribed_values"]:
            support["prescribed_values"] = {
                component: target["prescribed_values"][component]
                for component in dofs
                if component in target["prescribed_values"]
            }
        supports.append(support)
    return supports


def _canonical_load(row: dict[str, Any]) -> dict[str, Any]:
    components = row["components_si"]
    return {
        "node": str(row["node_id"]),
        "components": {
            key: float(components[key]) / 1.0e3
            for key in ("FX", "FY", "FZ", "MX", "MY", "MZ")
        },
    }


def _adapter_payload(
    adapter: BoundedPlanarModelIRAdapter,
    *,
    include_adapter_hash: bool,
) -> dict[str, Any]:
    payload = adapter.to_dict()
    if not include_adapter_hash:
        payload.pop("adapter_hash")
    return payload


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedPlanarModelIRAdapterError(code, path, detail)


__all__ = [
    "BOUNDED_PLANAR_MODEL_IR_ADAPTER_PROFILE",
    "BOUNDED_PLANAR_MODEL_IR_ADAPTER_SCHEMA_VERSION",
    "BOUNDED_PLANAR_MODEL_IR_CAPABILITY_PROFILE",
    "BOUNDED_PLANAR_MODEL_IR_DOF_COMPONENTS",
    "BOUNDED_PLANAR_MODEL_IR_INACTIVE_DOF_COMPONENTS",
    "BoundedPlanarModelIRAdapter",
    "BoundedPlanarModelIRAdapterError",
    "adapt_bounded_planar_model_ir_v2",
    "validate_bounded_planar_model_ir_adapter",
    "validate_bounded_planar_model_ir_adapter_manifest",
]
