"""Source-bound ModelIR v2 adapter for bounded multi-member Frame3D load control."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, NoReturn

from structural_analysis.assembly.corotational_frame3d_global import (
    CorotationalFrame3DMember,
    CorotationalFrame3DModel,
)
from structural_analysis.elements.frame3d import FRAME_DOF_LABELS, FrameProps
from structural_analysis.elements.timoshenko_frame3d import TimoshenkoFrame3DSection
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir.loader import parse_model_ir_v2
from structural_analysis.model_ir.types import ModelIRDocument


BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_CAPABILITY_PROFILE = "engine_v2_phase0_linear_3d"
BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION = (
    "bounded-frame3d-load-control-model-ir-adapter.v1"
)
BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_PROFILE = (
    "model_ir_v2_to_multimember_corotational_frame3d_load_control.v1"
)
BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_CLAIM_BOUNDARY = (
    "This adapter compiles one selected zero-self-weight ModelIR v2 load pattern "
    "into the bounded dense elastic corotational Frame3D load-control model. It "
    "requires 3-16 nodes, 2-32 connected unreleased zero-offset frame members, "
    "zero prescribed support values, bounded exact-binary64 coordinates, "
    "properties and loads, and a nonzero load on a free equation. It creates no "
    "stateful-material, external-V&V, "
    "design, public-product, release, or commercial authority."
)
_MAX_ABS_COORDINATE_M = 1.0e9
_MODULUS_PA_RANGE = (1.0e-3, 1.0e18)
_AREA_M2_RANGE = (1.0e-18, 1.0e12)
_INERTIA_M4_RANGE = (1.0e-36, 1.0e36)
_MAX_ABS_LOAD_SI = 1.0e18
_MAX_ABS_ROLL_RAD = 1.0e6


class BoundedFrame3DLoadControlModelIRAdapterError(ValueError):
    """Stable fail-closed ModelIR projection error."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code}@{path}: {detail}")


@dataclass(frozen=True)
class BoundedFrame3DLoadControlModelIRAdapter:
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
    restrained_global_dofs: tuple[int, ...]
    unit_conversion_hash: str
    entity_mapping_hash: str
    _model: CorotationalFrame3DModel = field(repr=False, compare=False)

    @property
    def model(self) -> CorotationalFrame3DModel:
        return self._model

    def to_dict(self) -> dict[str, Any]:
        return _adapter_payload(self, include_adapter_hash=True)


def adapt_bounded_frame3d_load_control_model_ir_v2(
    document: ModelIRDocument,
    *,
    load_pattern_id: str,
) -> BoundedFrame3DLoadControlModelIRAdapter:
    """Compile the exact bounded multi-member load-control projection."""

    adapter = _build_adapter(document, load_pattern_id=load_pattern_id)
    return validate_bounded_frame3d_load_control_model_ir_adapter(
        adapter,
        document=document,
    )


def _build_adapter(
    document: ModelIRDocument,
    *,
    load_pattern_id: str,
) -> BoundedFrame3DLoadControlModelIRAdapter:
    if type(document) is not ModelIRDocument:
        _fail(
            "bounded_frame3d_load_model_ir_document_type_invalid",
            "/",
            "Expected an exact ModelIRDocument.",
        )
    if not isinstance(load_pattern_id, str) or not load_pattern_id:
        _fail(
            "bounded_frame3d_load_pattern_id_invalid",
            "/load_pattern_id",
            "load_pattern_id must be a non-empty stable identifier.",
        )
    payload = document.to_dict()
    reparsed = parse_model_ir_v2(payload, require_analysis_ready=True)
    for name in ("content_hash", "semantic_hash", "provenance_hash"):
        if getattr(document, name) != getattr(reparsed, name):
            _fail(
                "bounded_frame3d_load_model_ir_document_hash_mismatch",
                f"/{name}",
                "Retained ModelIR hash does not match canonical content.",
            )
    if (
        reparsed.capability_profile
        != BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_CAPABILITY_PROFILE
    ):
        _fail(
            "bounded_frame3d_load_model_ir_profile_unsupported",
            "/capability_profile",
            "Expected the bounded linear 3D ModelIR capability profile.",
        )
    _validate_exact_binary64_projection_sources(payload)
    _validate_bounded_numeric_domains(payload)

    node_rows = payload["nodes"]
    element_rows = payload["elements"]
    if not 3 <= len(node_rows) <= 16:
        _fail(
            "bounded_frame3d_load_node_count_out_of_range",
            "/nodes",
            "Multi-member load control requires 3-16 nodes.",
        )
    if not 2 <= len(element_rows) <= 32:
        _fail(
            "bounded_frame3d_load_member_count_out_of_range",
            "/elements",
            "Multi-member load control requires 2-32 members.",
        )

    node_ids = tuple(str(row["id"]) for row in node_rows)
    node_index = {node_id: index for index, node_id in enumerate(node_ids)}
    material_rows = {str(row["id"]): row for row in payload["materials"]}
    section_rows = {str(row["id"]): row for row in payload["sections"]}
    referenced_materials: set[str] = set()
    referenced_sections: set[str] = set()
    members: list[CorotationalFrame3DMember] = []
    for index, row in enumerate(element_rows):
        base = f"/elements/{index}"
        if row["type"] != "frame_3d" or row["formulation"] != "euler_bernoulli_3d":
            _fail(
                "bounded_frame3d_load_member_formulation_unsupported",
                base,
                "Only unreleased frame_3d/euler_bernoulli_3d members are supported.",
            )
        if any(
            float(value) != 0.0
            for end in ("i_global_m", "j_global_m")
            for value in row["offsets"][end]
        ):
            _fail(
                "bounded_frame3d_load_member_offset_unsupported",
                f"{base}/offsets",
                "Rigid offsets are outside the bounded load-control profile.",
            )
        if row["releases"]["i"] or row["releases"]["j"]:
            _fail(
                "bounded_frame3d_load_member_release_unsupported",
                f"{base}/releases",
                "Member releases are outside the bounded load-control profile.",
            )
        material_id = str(row["material_id"])
        section_id = str(row["section_id"])
        try:
            material = material_rows[material_id]
            section = section_rows[section_id]
        except KeyError as error:  # pragma: no cover - ModelIR reference invariant
            _fail(
                "bounded_frame3d_load_reference_missing",
                base,
                f"Missing referenced entity {error.args[0]!r}.",
            )
        if material["law_id"] != "linear_elastic_isotropic":
            _fail(
                "bounded_frame3d_load_material_law_unsupported",
                f"/materials/{material['index']}/law_id",
                "Every member must use linear elastic isotropic material.",
            )
        if section["family_id"] != "frame_3d":
            _fail(
                "bounded_frame3d_load_section_family_unsupported",
                f"/sections/{section['index']}/family_id",
                "Every member must use a frame_3d section.",
            )
        node_i, node_j = (str(value) for value in row["node_ids"])
        try:
            member = CorotationalFrame3DMember(
                member_id=str(row["id"]),
                node_i=node_index[node_i],
                node_j=node_index[node_j],
                section=_section(section, material),
                local_axis_roll_deg=math.degrees(float(row["local_axis_rotation_rad"])),
            )
        except KeyError as error:  # pragma: no cover - ModelIR reference invariant
            _fail(
                "bounded_frame3d_load_reference_missing",
                f"{base}/node_ids",
                f"Missing referenced node {error.args[0]!r}.",
            )
        except (TypeError, ValueError) as error:
            _fail(
                "bounded_frame3d_load_member_compilation_failed",
                base,
                str(error),
            )
        members.append(member)
        referenced_materials.add(material_id)
        referenced_sections.add(section_id)
    if referenced_materials != set(material_rows):
        _fail(
            "bounded_frame3d_load_material_reference_set_invalid",
            "/materials",
            "Every and only declared material must be referenced.",
        )
    if referenced_sections != set(section_rows):
        _fail(
            "bounded_frame3d_load_section_reference_set_invalid",
            "/sections",
            "Every and only declared section must be referenced.",
        )

    restrained: set[int] = set()
    for constraint_index, row in enumerate(payload["constraints"]):
        base = f"/constraints/{constraint_index}"
        node_id = str(row["node_id"])
        for component in row["dofs"]:
            value = float(row["prescribed_values_si"].get(component, 0.0))
            if value != 0.0:
                _fail(
                    "bounded_frame3d_load_prescribed_support_unsupported",
                    f"{base}/prescribed_values_si/{component}",
                    "Only zero-valued restraints are supported.",
                )
            restrained.add(
                6 * node_index[node_id] + FRAME_DOF_LABELS.index(str(component))
            )
    restrained_dofs = tuple(sorted(restrained))

    matching_patterns = [
        row for row in payload["load_patterns"] if row["id"] == load_pattern_id
    ]
    if len(matching_patterns) != 1:
        _fail(
            "bounded_frame3d_load_pattern_not_unique",
            "/load_pattern_id",
            "The selected load pattern must exist exactly once.",
        )
    pattern = matching_patterns[0]
    if pattern["analysis_type"] not in ("linear_static", "nonlinear_static"):
        _fail(
            "bounded_frame3d_load_analysis_type_unsupported",
            f"/load_patterns/{pattern['index']}/analysis_type",
            "The selected pattern must be static.",
        )
    if any(float(value) != 0.0 for value in pattern["self_weight"]):
        _fail(
            "bounded_frame3d_load_self_weight_unsupported",
            f"/load_patterns/{pattern['index']}/self_weight",
            "Self weight is not consumed by this bounded adapter.",
        )
    reference_load = [0.0] * (6 * len(node_ids))
    components = ("FX", "FY", "FZ", "MX", "MY", "MZ")
    for load_index, row in enumerate(pattern["nodal_loads"]):
        dof_base = 6 * node_index[str(row["node_id"])]
        for component_index, component in enumerate(components):
            value_kn = float(row["components_si"][component]) / 1000.0
            dof = dof_base + component_index
            if value_kn != 0.0 and dof in restrained:
                _fail(
                    "bounded_frame3d_load_on_restrained_dof_unsupported",
                    (
                        f"/load_patterns/{pattern['index']}/nodal_loads/"
                        f"{load_index}/components_si/{component}"
                    ),
                    "Reference load must act on a free equation.",
                )
            reference_load[dof] += value_kn
    if not any(
        value != 0.0
        for index, value in enumerate(reference_load)
        if index not in restrained
    ):
        _fail(
            "bounded_frame3d_load_free_reference_load_missing",
            f"/load_patterns/{pattern['index']}/nodal_loads",
            "A nonzero reference load on a free equation is required.",
        )

    try:
        model = CorotationalFrame3DModel(
            node_coordinates_m=tuple(
                (
                    float(row["coordinates_m"][0]),
                    float(row["coordinates_m"][1]),
                    float(row["coordinates_m"][2]),
                )
                for row in node_rows
            ),
            members=tuple(members),
            restrained_dofs=restrained_dofs,
            reference_load_kn=tuple(reference_load),
            model_id=f"{document.model_id}.{load_pattern_id}.bounded-load-control",
        )
    except (TypeError, ValueError) as error:
        _fail("bounded_frame3d_load_model_compilation_failed", "/", str(error))

    unit_conversion_hash = canonical_hash(
        {
            "coordinates": "m_to_m_exact",
            "force": "N_to_kN_divide_1000",
            "moment": "N_m_to_kN_m_divide_1000",
            "elastic_modulus": "Pa_to_kN_per_m2_divide_1000",
            "shear_modulus": "derived_from_E_and_poisson_then_divide_1000",
            "rotation": "rad_to_deg_for_member_roll_only",
        }
    )
    entity_mapping_hash = canonical_hash(
        {
            "node_index": node_index,
            "member_ids": [member.member_id for member in members],
            "member_material_ids": [str(row["material_id"]) for row in element_rows],
            "member_section_ids": [str(row["section_id"]) for row in element_rows],
            "restrained_global_dofs": list(restrained_dofs),
            "load_pattern_id": load_pattern_id,
        }
    )
    provisional = BoundedFrame3DLoadControlModelIRAdapter(
        schema_version=BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION,
        adapter_profile=BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_PROFILE,
        adapter_hash="sha256:" + "0" * 64,
        model_ir_content_hash=reparsed.content_hash,
        model_ir_semantic_hash=reparsed.semantic_hash,
        model_ir_provenance_hash=reparsed.provenance_hash,
        load_pattern_id=load_pattern_id,
        model_hash=model.model_hash,
        node_ids=node_ids,
        member_ids=tuple(member.member_id for member in members),
        material_ids=tuple(material_rows),
        section_ids=tuple(section_rows),
        restrained_global_dofs=restrained_dofs,
        unit_conversion_hash=unit_conversion_hash,
        entity_mapping_hash=entity_mapping_hash,
        _model=model,
    )
    return BoundedFrame3DLoadControlModelIRAdapter(
        **{
            **provisional.__dict__,
            "adapter_hash": canonical_hash(
                _adapter_payload(provisional, include_adapter_hash=False)
            ),
        }
    )


def validate_bounded_frame3d_load_control_model_ir_adapter(
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
    *,
    document: ModelIRDocument | None = None,
) -> BoundedFrame3DLoadControlModelIRAdapter:
    if type(adapter) is not BoundedFrame3DLoadControlModelIRAdapter:
        _fail(
            "bounded_frame3d_load_adapter_type_invalid",
            "/",
            "Expected an exact bounded load-control adapter.",
        )
    if (
        adapter.schema_version
        != BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION
        or adapter.adapter_profile
        != BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_PROFILE
        or adapter.model_hash != adapter.model.model_hash
    ):
        _fail(
            "bounded_frame3d_load_adapter_contract_invalid",
            "/schema_version",
            "Adapter contract or compiled model binding is invalid.",
        )
    if adapter.adapter_hash != canonical_hash(
        _adapter_payload(adapter, include_adapter_hash=False)
    ):
        _fail(
            "bounded_frame3d_load_adapter_hash_mismatch",
            "/adapter_hash",
            "Adapter hash does not match its source-bound manifest.",
        )
    if document is not None:
        expected = _build_adapter(document, load_pattern_id=adapter.load_pattern_id)
        if (
            _adapter_payload(adapter, include_adapter_hash=False)
            != _adapter_payload(expected, include_adapter_hash=False)
            or adapter.model.to_manifest() != expected.model.to_manifest()
        ):
            _fail(
                "bounded_frame3d_load_adapter_projection_mismatch",
                "/model_hash",
                "Adapter projection does not match the supplied ModelIR document.",
            )
    return adapter


def _section(
    section_row: dict[str, Any], material_row: dict[str, Any]
) -> TimoshenkoFrame3DSection:
    section = section_row["parameters"]
    material = material_row["parameters"]
    elastic_modulus_pa = float(material["elastic_modulus_pa"])
    poisson_ratio = float(material["poisson_ratio"])
    return TimoshenkoFrame3DSection(
        FrameProps(
            area_m2=float(section["area_m2"]),
            e_n_per_m2=elastic_modulus_pa / 1000.0,
            g_n_per_m2=(elastic_modulus_pa / (2.0 * (1.0 + poisson_ratio)) / 1000.0),
            iy_m4=float(section["iy_m4"]),
            iz_m4=float(section["iz_m4"]),
            j_m4=float(section["torsional_constant_m4"]),
        ),
        effective_shear_area_y_m2=float(section["shear_area_y_m2"]),
        effective_shear_area_z_m2=float(section["shear_area_z_m2"]),
    )


def _adapter_payload(
    adapter: BoundedFrame3DLoadControlModelIRAdapter,
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
        "restrained_global_dofs": list(adapter.restrained_global_dofs),
        "unit_conversion_hash": adapter.unit_conversion_hash,
        "entity_mapping_hash": adapter.entity_mapping_hash,
        "claim_boundary": BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_CLAIM_BOUNDARY,
    }
    if include_adapter_hash:
        payload["adapter_hash"] = adapter.adapter_hash
    return payload


def _validate_exact_binary64_projection_sources(payload: dict[str, Any]) -> None:
    paths_and_values: list[tuple[str, Any]] = []
    for node_index, row in enumerate(payload["nodes"]):
        paths_and_values.extend(
            (
                f"/nodes/{node_index}/coordinates_m/{component_index}",
                value,
            )
            for component_index, value in enumerate(row["coordinates_m"])
        )
    for material_index, row in enumerate(payload["materials"]):
        for name in ("elastic_modulus_pa", "poisson_ratio"):
            paths_and_values.append(
                (
                    f"/materials/{material_index}/parameters/{name}",
                    row["parameters"][name],
                )
            )
    for section_index, row in enumerate(payload["sections"]):
        for name in (
            "area_m2",
            "iy_m4",
            "iz_m4",
            "torsional_constant_m4",
            "shear_area_y_m2",
            "shear_area_z_m2",
        ):
            paths_and_values.append(
                (
                    f"/sections/{section_index}/parameters/{name}",
                    row["parameters"][name],
                )
            )
    for element_index, row in enumerate(payload["elements"]):
        paths_and_values.append(
            (
                f"/elements/{element_index}/local_axis_rotation_rad",
                row["local_axis_rotation_rad"],
            )
        )
        for end in ("i_global_m", "j_global_m"):
            paths_and_values.extend(
                (f"/elements/{element_index}/offsets/{end}/{index}", value)
                for index, value in enumerate(row["offsets"][end])
            )
    for constraint_index, row in enumerate(payload["constraints"]):
        paths_and_values.extend(
            (
                f"/constraints/{constraint_index}/prescribed_values_si/{component}",
                value,
            )
            for component, value in row["prescribed_values_si"].items()
        )
    for pattern_index, pattern in enumerate(payload["load_patterns"]):
        paths_and_values.extend(
            (f"/load_patterns/{pattern_index}/self_weight/{index}", value)
            for index, value in enumerate(pattern["self_weight"])
        )
        for load_index, row in enumerate(pattern["nodal_loads"]):
            paths_and_values.extend(
                (
                    f"/load_patterns/{pattern_index}/nodal_loads/{load_index}/"
                    f"components_si/{component}",
                    value,
                )
                for component, value in row["components_si"].items()
            )
    for path, value in paths_and_values:
        _require_exact_binary64(value, path)


def _validate_bounded_numeric_domains(payload: dict[str, Any]) -> None:
    """Keep every projected arithmetic source inside the bounded 3D policy."""

    for node_index, row in enumerate(payload["nodes"]):
        for axis, value in enumerate(row["coordinates_m"]):
            if abs(float(value)) > _MAX_ABS_COORDINATE_M:
                _fail(
                    "bounded_frame3d_load_coordinate_magnitude_out_of_range",
                    f"/nodes/{node_index}/coordinates_m/{axis}",
                    "Coordinates must have magnitude at most 1e9 m.",
                )
    for material_index, row in enumerate(payload["materials"]):
        parameters = row["parameters"]
        elastic_modulus_pa = float(parameters["elastic_modulus_pa"])
        lower, upper = _MODULUS_PA_RANGE
        if not lower <= elastic_modulus_pa <= upper:
            _fail(
                "bounded_frame3d_load_material_value_out_of_range",
                f"/materials/{material_index}/parameters/elastic_modulus_pa",
                "Elastic modulus is outside the bounded arithmetic range.",
            )
        poisson_ratio = float(parameters["poisson_ratio"])
        shear_modulus_pa = elastic_modulus_pa / (2.0 * (1.0 + poisson_ratio))
        if not lower <= shear_modulus_pa <= upper:
            _fail(
                "bounded_frame3d_load_material_value_out_of_range",
                f"/materials/{material_index}/parameters/poisson_ratio",
                "Derived shear modulus is outside the bounded arithmetic range.",
            )
    for section_index, row in enumerate(payload["sections"]):
        parameters = row["parameters"]
        for name in ("area_m2", "shear_area_y_m2", "shear_area_z_m2"):
            value = float(parameters[name])
            lower, upper = _AREA_M2_RANGE
            if not lower <= value <= upper:
                _fail(
                    "bounded_frame3d_load_section_value_out_of_range",
                    f"/sections/{section_index}/parameters/{name}",
                    "Frame area term is outside the bounded arithmetic range.",
                )
        for name in ("iy_m4", "iz_m4", "torsional_constant_m4"):
            value = float(parameters[name])
            lower, upper = _INERTIA_M4_RANGE
            if not lower <= value <= upper:
                _fail(
                    "bounded_frame3d_load_section_value_out_of_range",
                    f"/sections/{section_index}/parameters/{name}",
                    "Frame inertia term is outside the bounded arithmetic range.",
                )
    for element_index, row in enumerate(payload["elements"]):
        if abs(float(row["local_axis_rotation_rad"])) > _MAX_ABS_ROLL_RAD:
            _fail(
                "bounded_frame3d_load_roll_magnitude_out_of_range",
                f"/elements/{element_index}/local_axis_rotation_rad",
                "Local-axis roll is outside the bounded arithmetic range.",
            )
    for pattern_index, pattern in enumerate(payload["load_patterns"]):
        for load_index, row in enumerate(pattern["nodal_loads"]):
            for component, value in row["components_si"].items():
                if abs(float(value)) > _MAX_ABS_LOAD_SI:
                    _fail(
                        "bounded_frame3d_load_magnitude_out_of_range",
                        (
                            f"/load_patterns/{pattern_index}/nodal_loads/"
                            f"{load_index}/components_si/{component}"
                        ),
                        "Reference force/moment is outside the bounded arithmetic range.",
                    )


def _require_exact_binary64(value: Any, path: str) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail(
            "bounded_frame3d_load_numeric_source_not_binary64",
            path,
            "Numeric source must be exactly representable as binary64.",
        )
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError):
        converted = math.inf
    if not math.isfinite(converted) or (type(value) is int and int(converted) != value):
        _fail(
            "bounded_frame3d_load_numeric_source_not_binary64",
            path,
            "Numeric source must be exactly representable as binary64.",
        )
    return 0.0 if converted == 0.0 else converted


def _fail(code: str, path: str, detail: str) -> NoReturn:
    raise BoundedFrame3DLoadControlModelIRAdapterError(code, path, detail)


__all__ = [
    "BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_PROFILE",
    "BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_ADAPTER_SCHEMA_VERSION",
    "BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_CAPABILITY_PROFILE",
    "BOUNDED_FRAME3D_LOAD_CONTROL_MODEL_IR_CLAIM_BOUNDARY",
    "BoundedFrame3DLoadControlModelIRAdapter",
    "BoundedFrame3DLoadControlModelIRAdapterError",
    "adapt_bounded_frame3d_load_control_model_ir_v2",
    "validate_bounded_frame3d_load_control_model_ir_adapter",
]
