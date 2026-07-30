"""Source-bound ModelIR v2 adapter for bounded Frame3D direct control."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, NoReturn

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
)
from structural_analysis.assembly.corotational_frame3d_graph import (
    CorotationalFrame3DGraphModel,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (
    StatefulCorotationalFrame3DSparseModel,
)
from structural_analysis.elements.frame3d import FRAME_DOF_LABELS, FrameProps
from structural_analysis.elements.timoshenko_frame3d import (
    TimoshenkoFrame3DSection,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)
from structural_analysis.model_ir.loader import parse_model_ir_v2
from structural_analysis.model_ir.types import ModelIRDocument


BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_CAPABILITY_PROFILE = (
    "bounded_frame3d_direct_displacement_control"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION = (
    "bounded-frame3d-direct-control-model-ir-adapter.v1"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_PROFILE = (
    "model_ir_v2_to_stateful_corotational_frame3d_direct_control.v1"
)
BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_CLAIM_BOUNDARY = (
    "This adapter performs exact SI-to-m/kN/MPa conversion for the bounded "
    "ModelIR v2 Frame3D direct-control profile. It accepts connected zero-offset, "
    "unreleased Timoshenko members with explicit bilinear steel, shear modulus, "
    "zero prescribed supports, and one free-equation reference-load pattern. Every "
    "numeric source projected into the solver must be losslessly representable as "
    "binary64 before unit conversion. It "
    "creates no convergence, design, external-V&V, Level 2, or release authority."
)


class BoundedFrame3DDirectControlModelIRAdapterError(ValueError):
    """Stable fail-closed ModelIR projection error."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class BoundedFrame3DDirectControlModelIRAdapter:
    schema_version: str
    adapter_profile: str
    adapter_hash: str
    model_ir_content_hash: str
    model_ir_semantic_hash: str
    model_ir_provenance_hash: str
    load_pattern_id: str
    model_hash: str
    node_ids: tuple[str, ...]
    member_ids: tuple[str, ...]
    material_ids: tuple[str, ...]
    section_ids: tuple[str, ...]
    unit_conversion_hash: str
    entity_mapping_hash: str
    _model: StatefulCorotationalFrame3DSparseModel = field(
        repr=False,
        compare=False,
    )

    @property
    def model(self) -> StatefulCorotationalFrame3DSparseModel:
        return self._model

    def global_dof(self, node_id: str, component: str) -> int:
        if node_id not in self.node_ids:
            _fail(
                "bounded_frame3d_control_node_unknown",
                "/control/node_id",
                f"Unknown control node {node_id!r}.",
            )
        if component not in FRAME_DOF_LABELS:
            _fail(
                "bounded_frame3d_control_component_invalid",
                "/control/dof",
                f"Control DOF must be one of {list(FRAME_DOF_LABELS)}.",
            )
        return 6 * self.node_ids.index(node_id) + FRAME_DOF_LABELS.index(component)

    def to_dict(self) -> dict[str, Any]:
        return _adapter_payload(self, include_adapter_hash=True)


def adapt_bounded_frame3d_direct_control_model_ir_v2(
    document: ModelIRDocument,
) -> BoundedFrame3DDirectControlModelIRAdapter:
    """Compile the exact bounded ModelIR profile into the sparse Frame3D model."""

    adapter = _build_bounded_frame3d_direct_control_model_ir_v2(document)
    return validate_bounded_frame3d_direct_control_model_ir_adapter(
        adapter,
        document=document,
    )


def _build_bounded_frame3d_direct_control_model_ir_v2(
    document: ModelIRDocument,
) -> BoundedFrame3DDirectControlModelIRAdapter:
    """Build an adapter without recursively validating its source projection."""

    if type(document) is not ModelIRDocument:
        _fail(
            "bounded_frame3d_model_ir_document_type_invalid",
            "/",
            "Expected an exact ModelIRDocument.",
        )
    payload = document.to_dict()
    reparsed = parse_model_ir_v2(payload, require_analysis_ready=True)
    for name in ("content_hash", "semantic_hash", "provenance_hash"):
        if getattr(document, name) != getattr(reparsed, name):
            _fail(
                "bounded_frame3d_model_ir_document_hash_mismatch",
                f"/{name}",
                "Retained ModelIR hash does not match canonical content.",
            )
    if (
        reparsed.capability_profile
        != BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_CAPABILITY_PROFILE
    ):
        _fail(
            "bounded_frame3d_model_ir_profile_unsupported",
            "/capability_profile",
            "ModelIR is not the bounded Frame3D direct-control profile.",
        )
    _validate_exact_binary64_projection_sources(payload)

    node_ids = tuple(str(row["id"]) for row in payload["nodes"])
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    material_rows = {
        str(row["id"]): row for row in payload["materials"]
    }
    section_rows = {str(row["id"]): row for row in payload["sections"]}
    material_objects = {
        material_id: _material_from_row(row)
        for material_id, row in material_rows.items()
    }

    members: list[CorotationalFrame3DMember] = []
    member_materials: list[BilinearCombinedHardeningSteel] = []
    for index, row in enumerate(payload["elements"]):
        material_id = str(row["material_id"])
        section_id = str(row["section_id"])
        try:
            material = material_objects[material_id]
            section_row = section_rows[section_id]
        except KeyError as error:  # pragma: no cover - ModelIR reference invariant
            _fail(
                "bounded_frame3d_model_ir_reference_missing",
                f"/elements/{index}",
                f"Missing referenced entity {error.args[0]!r}.",
            )
        section = _section_from_rows(section_row, material_rows[material_id])
        node_i, node_j = (str(value) for value in row["node_ids"])
        members.append(
            CorotationalFrame3DMember(
                member_id=str(row["id"]),
                node_i=node_index[node_i],
                node_j=node_index[node_j],
                section=section,
                local_axis_roll_deg=math.degrees(
                    float(row["local_axis_rotation_rad"])
                ),
            )
        )
        member_materials.append(material)

    restrained_dofs = tuple(
        sorted(
            {
                6 * node_index[str(row["node_id"])]
                + FRAME_DOF_LABELS.index(str(component))
                for row in payload["constraints"]
                for component in row["dofs"]
            }
        )
    )
    reference_load = [0.0] * (6 * len(node_ids))
    load_pattern = payload["load_patterns"][0]
    load_components = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    for row in load_pattern["nodal_loads"]:
        base = 6 * node_index[str(row["node_id"])]
        for component_index, component in enumerate(load_components):
            reference_load[base + component_index] += (
                float(row["components_si"][component]) / 1000.0
            )

    try:
        elastic_model = CorotationalFrame3DGraphModel(
            node_coordinates_m=tuple(
                tuple(float(value) for value in row["coordinates_m"])
                for row in payload["nodes"]
            ),
            members=tuple(members),
            restrained_dofs=restrained_dofs,
            reference_load_kn=tuple(reference_load),
            model_id=str(payload["model_id"]),
        )
        model = StatefulCorotationalFrame3DSparseModel(
            elastic_model,
            tuple(member_materials),
        )
    except (TypeError, ValueError) as error:
        _fail(
            "bounded_frame3d_model_compilation_failed",
            "/",
            str(error),
        )

    unit_conversion_hash = canonical_hash(
        {
            "coordinates": "m_to_m_exact",
            "force": "N_to_kN_divide_1000",
            "moment": "N_m_to_kN_m_divide_1000",
            "stress": "Pa_to_MPa_divide_1000000",
            "elastic_and_shear_modulus": "Pa_to_kN_per_m2_divide_1000",
            "rotation": "rad_to_deg_for_member_roll_only",
        }
    )
    entity_mapping_hash = canonical_hash(
        {
            "node_index": node_index,
            "member_ids": [str(row["id"]) for row in payload["elements"]],
            "member_material_ids": [
                str(row["material_id"]) for row in payload["elements"]
            ],
            "member_section_ids": [
                str(row["section_id"]) for row in payload["elements"]
            ],
            "restrained_global_dofs": list(restrained_dofs),
            "load_pattern_id": str(load_pattern["id"]),
        }
    )
    provisional = BoundedFrame3DDirectControlModelIRAdapter(
        schema_version=(
            BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION
        ),
        adapter_profile=BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_PROFILE,
        adapter_hash="sha256:" + "0" * 64,
        model_ir_content_hash=reparsed.content_hash,
        model_ir_semantic_hash=reparsed.semantic_hash,
        model_ir_provenance_hash=reparsed.provenance_hash,
        load_pattern_id=str(load_pattern["id"]),
        model_hash=model.model_hash,
        node_ids=node_ids,
        member_ids=tuple(str(row["id"]) for row in payload["elements"]),
        material_ids=tuple(str(row["id"]) for row in payload["materials"]),
        section_ids=tuple(str(row["id"]) for row in payload["sections"]),
        unit_conversion_hash=unit_conversion_hash,
        entity_mapping_hash=entity_mapping_hash,
        _model=model,
    )
    adapter = BoundedFrame3DDirectControlModelIRAdapter(
        **{
            **provisional.__dict__,
            "adapter_hash": canonical_hash(
                _adapter_payload(provisional, include_adapter_hash=False)
            ),
        }
    )
    return adapter


def validate_bounded_frame3d_direct_control_model_ir_adapter(
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    *,
    document: ModelIRDocument | None = None,
) -> BoundedFrame3DDirectControlModelIRAdapter:
    if type(adapter) is not BoundedFrame3DDirectControlModelIRAdapter:
        _fail(
            "bounded_frame3d_model_ir_adapter_type_invalid",
            "/",
            "Expected an exact bounded Frame3D adapter.",
        )
    if (
        adapter.schema_version
        != BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION
        or adapter.adapter_profile
        != BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_PROFILE
    ):
        _fail(
            "bounded_frame3d_model_ir_adapter_contract_invalid",
            "/schema_version",
            "Unsupported bounded Frame3D adapter contract.",
        )
    if adapter.model_hash != adapter.model.model_hash:
        _fail(
            "bounded_frame3d_model_ir_model_hash_mismatch",
            "/model_hash",
            "Adapter model hash does not match the compiled model.",
        )
    expected_hash = canonical_hash(
        _adapter_payload(adapter, include_adapter_hash=False)
    )
    if adapter.adapter_hash != expected_hash:
        _fail(
            "bounded_frame3d_model_ir_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash does not match its source-bound manifest.",
        )
    if document is not None:
        if type(document) is not ModelIRDocument:
            _fail(
                "bounded_frame3d_model_ir_document_type_invalid",
                "/",
                "Expected an exact ModelIRDocument.",
            )
        if (
            adapter.model_ir_content_hash != document.content_hash
            or adapter.model_ir_semantic_hash != document.semantic_hash
            or adapter.model_ir_provenance_hash != document.provenance_hash
        ):
            _fail(
                "bounded_frame3d_model_ir_source_binding_mismatch",
                "/model_ir_content_hash",
                "Adapter is not bound to the supplied ModelIR document.",
            )
        expected = _build_bounded_frame3d_direct_control_model_ir_v2(document)
        if (
            _adapter_payload(adapter, include_adapter_hash=False)
            != _adapter_payload(expected, include_adapter_hash=False)
            or adapter.model.to_manifest() != expected.model.to_manifest()
        ):
            _fail(
                "bounded_frame3d_model_ir_compiled_projection_mismatch",
                "/model_hash",
                "Compiled model and adapter projection do not match the supplied ModelIR document.",
            )
    return adapter


def _material_from_row(row: dict[str, Any]) -> BilinearCombinedHardeningSteel:
    parameters = row["parameters"]
    return BilinearCombinedHardeningSteel(
        elastic_modulus_mpa=float(parameters["elastic_modulus_pa"]) / 1.0e6,
        yield_stress_mpa=float(parameters["yield_stress_pa"]) / 1.0e6,
        isotropic_hardening_modulus_mpa=(
            float(parameters["isotropic_hardening_modulus_pa"]) / 1.0e6
        ),
        kinematic_hardening_modulus_mpa=(
            float(parameters["kinematic_hardening_modulus_pa"]) / 1.0e6
        ),
        yield_tolerance_mpa=float(parameters["yield_tolerance_pa"]) / 1.0e6,
        material_id=str(row["id"]),
    )


def _section_from_rows(
    section_row: dict[str, Any],
    material_row: dict[str, Any],
) -> TimoshenkoFrame3DSection:
    section = section_row["parameters"]
    material = material_row["parameters"]
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=float(section["area_m2"]),
            e_n_per_m2=float(material["elastic_modulus_pa"]) / 1000.0,
            g_n_per_m2=float(material["shear_modulus_pa"]) / 1000.0,
            iy_m4=float(section["iy_m4"]),
            iz_m4=float(section["iz_m4"]),
            j_m4=float(section["torsional_constant_m4"]),
        ),
        effective_shear_area_y_m2=float(section["shear_area_y_m2"]),
        effective_shear_area_z_m2=float(section["shear_area_z_m2"]),
    )


def _adapter_payload(
    adapter: BoundedFrame3DDirectControlModelIRAdapter,
    *,
    include_adapter_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": adapter.schema_version,
        "adapter_profile": adapter.adapter_profile,
        "model_ir_content_hash": adapter.model_ir_content_hash,
        "model_ir_semantic_hash": adapter.model_ir_semantic_hash,
        "model_ir_provenance_hash": adapter.model_ir_provenance_hash,
        "load_pattern_id": adapter.load_pattern_id,
        "model_hash": adapter.model_hash,
        "node_ids": list(adapter.node_ids),
        "member_ids": list(adapter.member_ids),
        "material_ids": list(adapter.material_ids),
        "section_ids": list(adapter.section_ids),
        "unit_conversion_hash": adapter.unit_conversion_hash,
        "entity_mapping_hash": adapter.entity_mapping_hash,
        "claim_boundary": BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_CLAIM_BOUNDARY,
    }
    if include_adapter_hash:
        payload["adapter_hash"] = adapter.adapter_hash
    return payload


def _validate_exact_binary64_projection_sources(payload: dict[str, Any]) -> None:
    """Validate only numbers projected into the bounded solver model."""

    for node_index, row in enumerate(payload["nodes"]):
        for component_index, value in enumerate(row["coordinates_m"]):
            _require_exact_binary64(
                value,
                f"/nodes/{node_index}/coordinates_m/{component_index}",
            )
    for element_index, row in enumerate(payload["elements"]):
        _require_exact_binary64(
            row["local_axis_rotation_rad"],
            f"/elements/{element_index}/local_axis_rotation_rad",
        )
    material_fields = (
        "elastic_modulus_pa",
        "shear_modulus_pa",
        "yield_stress_pa",
        "isotropic_hardening_modulus_pa",
        "kinematic_hardening_modulus_pa",
        "yield_tolerance_pa",
    )
    for material_index, row in enumerate(payload["materials"]):
        parameters = row["parameters"]
        for field_name in material_fields:
            if field_name in parameters:
                _require_exact_binary64(
                    parameters[field_name],
                    f"/materials/{material_index}/parameters/{field_name}",
                )
    section_fields = (
        "area_m2",
        "iy_m4",
        "iz_m4",
        "torsional_constant_m4",
        "shear_area_y_m2",
        "shear_area_z_m2",
    )
    for section_index, row in enumerate(payload["sections"]):
        parameters = row["parameters"]
        for field_name in section_fields:
            if field_name in parameters:
                _require_exact_binary64(
                    parameters[field_name],
                    f"/sections/{section_index}/parameters/{field_name}",
                )
    for load_index, row in enumerate(
        payload["load_patterns"][0]["nodal_loads"]
    ):
        for component, value in row["components_si"].items():
            _require_exact_binary64(
                value,
                f"/load_patterns/0/nodal_loads/{load_index}/components_si/{component}",
            )


def _require_exact_binary64(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "bounded_frame3d_model_ir_numeric_source_not_binary64",
            path,
            "Numeric source must be exactly representable as binary64.",
        )
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError):
        converted = math.inf
    if (
        not math.isfinite(converted)
        or (type(value) is int and int(converted) != value)
    ):
        _fail(
            "bounded_frame3d_model_ir_numeric_source_not_binary64",
            path,
            "Numeric source must be exactly representable as binary64.",
        )
    return 0.0 if converted == 0.0 else converted


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedFrame3DDirectControlModelIRAdapterError(code, path, detail)


__all__ = [
    "BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_PROFILE",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_CAPABILITY_PROFILE",
    "BOUNDED_FRAME3D_DIRECT_CONTROL_MODEL_IR_CLAIM_BOUNDARY",
    "BoundedFrame3DDirectControlModelIRAdapter",
    "BoundedFrame3DDirectControlModelIRAdapterError",
    "adapt_bounded_frame3d_direct_control_model_ir_v2",
    "validate_bounded_frame3d_direct_control_model_ir_adapter",
]
