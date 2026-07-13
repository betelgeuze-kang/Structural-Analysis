"""Canonical reverse projection for the supported Phase 0 MGT subset."""

from __future__ import annotations

from collections.abc import Iterable
import csv
import hashlib
import io
import math
import re
from typing import Any

from structural_analysis.io.midas.v2.grammar import rectangle_saint_venant_j
from structural_analysis.model_ir import (
    ModelIRDocument,
    canonicalize_model_ir_v2,
    parse_model_ir_v2,
)


MGT_PHASE0_SUBSET_CONTRACT = "midas_mgt_phase0_linear_frame.v1"
_SOURCE_ID_RE = re.compile(r"^mgt:(NODE|MATERIAL|SECTION|ELEMENT):(\d+)$")
_FORCE_UNIT_LABELS = {"N": "N", "kN": "KN", "MN": "MN"}
_LENGTH_UNIT_LABELS = {"m": "M", "mm": "MM", "cm": "CM"}


class MGTReverseProjectionError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


def write_canonical_mgt_v2(model: ModelIRDocument | dict[str, Any]) -> str:
    """Write only the strict subset; unsupported ModelIR semantics fail closed."""

    document = _validated_document(model, require_analysis_ready=True)
    if not document.analysis_ready:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_MODEL_NOT_READY",
            "/unsupported_features",
            "Canonical MGT projection requires an analysis-ready ModelIR document.",
        )
    payload = document.to_dict()
    _validate_supported_model_ir_subset(payload)
    provenance = payload["provenance"]
    if provenance["source_format"] != "midas_mgt":
        raise MGTReverseProjectionError(
            "MGT_REVERSE_SOURCE_FORMAT_MISMATCH",
            "/provenance/source_format",
            "The Phase 0 MGT writer requires MIDAS source provenance.",
        )
    subset = provenance.get("extensions", {}).get("midas_mgt:subset_contract")
    if subset != MGT_PHASE0_SUBSET_CONTRACT:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_SUBSET_CONTRACT_MISMATCH",
            "/provenance/extensions",
            "The ModelIR document was not produced by the supported MGT subset.",
        )

    source_units = provenance["source_units"]
    scales = provenance["unit_scales_to_si"]
    force_unit = str(source_units["force"])
    length_unit = str(source_units["length"])
    if force_unit not in _FORCE_UNIT_LABELS or length_unit not in _LENGTH_UNIT_LABELS:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_UNIT_NOT_SUPPORTED",
            "/provenance/source_units",
            "Canonical MGT projection supports N/kN/MN and m/mm/cm only.",
        )
    force_scale = float(scales["force_to_n"])
    length_scale = float(scales["length_to_m"])
    gravity_m_s2 = _required_extension_float(
        provenance, "midas_mgt:gravity_m_s2", "/provenance/extensions"
    )
    gravity_source = gravity_m_s2 / length_scale

    lines = [
        "*VERSION",
        "9.3.0",
        "",
        "*UNIT",
        _csv_row(
            (_FORCE_UNIT_LABELS[force_unit], _LENGTH_UNIT_LABELS[length_unit], "KJ", "C")
        ),
        "",
        "*STRUCTYPE",
        _csv_row(("0", "1", "1", "NO", "YES", _number(gravity_source), "0", "YES", "YES", "NO")),
        "",
        "*NODE",
    ]
    for index, node in enumerate(payload["nodes"]):
        source_id = _numeric_source_id(node, "NODE", f"/nodes/{index}")
        coordinates = [float(value) / length_scale for value in node["coordinates_m"]]
        lines.append(_csv_row([str(source_id), *(_number(value) for value in coordinates)]))

    lines.extend(["", "*MATERIAL"])
    for index, material in enumerate(payload["materials"]):
        path = f"/materials/{index}"
        source_id = _numeric_source_id(material, "MATERIAL", path)
        extensions = material["extensions"]
        source_type = _required_extension_text(extensions, "midas_mgt:source_type", path)
        source_name = _required_extension_text(extensions, "midas_mgt:source_name", path)
        damping = float(extensions.get("midas_mgt:damping_ratio", 0.0))
        thermal = float(extensions.get("midas_mgt:thermal_coefficient", 0.0))
        parameters = material["parameters"]
        elastic_source = (
            float(parameters["elastic_modulus_pa"])
            * length_scale**2
            / force_scale
        )
        density = float(parameters["density_kg_m3"])
        unit_weight_source = (
            density * gravity_m_s2 * length_scale**3 / force_scale
        )
        fields = [
            str(source_id),
            source_type,
            source_name,
            "0",
            "0",
            "",
            "C",
            "NO",
            _number(damping),
            "2",
            _number(elastic_source),
            _number(float(parameters["poisson_ratio"])),
            _number(thermal),
            _number(unit_weight_source),
            "0",
        ]
        lines.append(_csv_row(fields))

    lines.extend(["", "*SECTION"])
    for index, section in enumerate(payload["sections"]):
        path = f"/sections/{index}"
        if section["family_id"] != "frame_3d":
            raise MGTReverseProjectionError(
                "MGT_REVERSE_SECTION_FAMILY_NOT_SUPPORTED",
                path,
                "The Phase 0 MGT subset writes frame_3d sections only.",
            )
        source_id = _numeric_source_id(section, "SECTION", path)
        extensions = section["extensions"]
        source_name = _required_extension_text(extensions, "midas_mgt:source_name", path)
        height_m = _required_extension_float(extensions, "midas_mgt:height_m", path)
        width_m = _required_extension_float(extensions, "midas_mgt:width_m", path)
        _validate_section_derivation(section, height_m=height_m, width_m=width_m, path=path)
        fields = [
            str(source_id),
            "DBUSER",
            source_name,
            "CC",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "YES",
            "NO",
            "SB",
            "2",
            _number(height_m / length_scale),
            _number(width_m / length_scale),
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
        ]
        lines.append(_csv_row(fields))

    lines.extend(["", "*ELEMENT"])
    node_source_ids = {
        str(node["id"]): _numeric_source_id(node, "NODE", f"/nodes/{index}")
        for index, node in enumerate(payload["nodes"])
    }
    material_source_ids = {
        str(row["id"]): _numeric_source_id(row, "MATERIAL", f"/materials/{index}")
        for index, row in enumerate(payload["materials"])
    }
    section_source_ids = {
        str(row["id"]): _numeric_source_id(row, "SECTION", f"/sections/{index}")
        for index, row in enumerate(payload["sections"])
    }
    for index, element in enumerate(payload["elements"]):
        path = f"/elements/{index}"
        if element["type"] != "frame_3d" or element["formulation"] != "euler_bernoulli_3d":
            raise MGTReverseProjectionError(
                "MGT_REVERSE_ELEMENT_NOT_SUPPORTED",
                path,
                "The Phase 0 MGT subset writes Euler-Bernoulli BEAM elements only.",
            )
        if any(element["releases"][end] for end in ("i", "j")) or any(
            float(value) != 0.0
            for end in ("i", "j")
            for value in element["offsets"][f"{end}_global_m"]
        ):
            raise MGTReverseProjectionError(
                "MGT_REVERSE_ELEMENT_FEATURE_NOT_SUPPORTED",
                path,
                "Offsets and releases are outside the Phase 0 MGT subset.",
            )
        source_id = _numeric_source_id(element, "ELEMENT", path)
        node_i, node_j = (node_source_ids[str(value)] for value in element["node_ids"])
        angle_deg = float(element["local_axis_rotation_rad"]) * 180.0 / math.pi
        lines.append(
            _csv_row(
                [
                    str(source_id),
                    "BEAM",
                    str(material_source_ids[str(element["material_id"])]),
                    str(section_source_ids[str(element["section_id"])]),
                    str(node_i),
                    str(node_j),
                    _number(angle_deg),
                    "0",
                ]
            )
        )

    lines.extend(["", "*STLDCASE"])
    for index, pattern in enumerate(payload["load_patterns"]):
        path = f"/load_patterns/{index}"
        extensions = pattern["extensions"]
        name = _required_extension_text(extensions, "midas_mgt:source_name", path)
        load_type = _required_extension_text(extensions, "midas_mgt:load_type", path)
        description = str(extensions.get("midas_mgt:description", ""))
        lines.append(_csv_row((name, load_type, description)))

    lines.extend(["", "*CONSTRAINT"])
    for index, constraint in enumerate(payload["constraints"]):
        path = f"/constraints/{index}"
        node_source_id = node_source_ids[str(constraint["node_id"])]
        dofs = set(str(value) for value in constraint["dofs"])
        mask = "".join("1" if dof in dofs else "0" for dof in payload["dof_components"])
        group = str(constraint["extensions"].get("midas_mgt:group", ""))
        lines.append(_csv_row((str(node_source_id), mask, group)))

    force_components = ("FX", "FY", "FZ")
    moment_components = ("MX", "MY", "MZ")
    for pattern_index, pattern in enumerate(payload["load_patterns"]):
        if any(float(value) != 0.0 for value in pattern["self_weight"]):
            raise MGTReverseProjectionError(
                "MGT_REVERSE_SELF_WEIGHT_NOT_SUPPORTED",
                f"/load_patterns/{pattern_index}/self_weight",
                "The Phase 0 MGT subset writes nodal loads only.",
            )
        source_name = _required_extension_text(
            pattern["extensions"],
            "midas_mgt:source_name",
            f"/load_patterns/{pattern_index}",
        )
        lines.extend(["", "*USE-STLD, " + _csv_row((source_name,)), "*CONLOAD"])
        for load in pattern["nodal_loads"]:
            components = load["components_si"]
            fields = [str(node_source_ids[str(load["node_id"])])]
            fields.extend(
                _number(float(components[key]) / force_scale)
                for key in force_components
            )
            fields.extend(
                _number(float(components[key]) / (force_scale * length_scale))
                for key in moment_components
            )
            group = str(load["extensions"].get("midas_mgt:group", ""))
            structure_type = str(
                load["extensions"].get("midas_mgt:structure_type_name", "")
            )
            fields.extend((group, structure_type))
            lines.append(_csv_row(fields))

    lines.extend(["", "*ENDDATA", ""])
    return "\n".join(lines)


def model_ir_solver_semantic_projection(
    model: ModelIRDocument | dict[str, Any],
) -> dict[str, Any]:
    document = _validated_document(model, require_analysis_ready=False)
    source = document.to_dict()
    keys = (
        "schema_version",
        "capability_profile",
        "units",
        "coordinate_system",
        "dof_components",
        "nodes",
        "materials",
        "sections",
        "elements",
        "constraints",
        "load_patterns",
        "load_combinations",
        "time_functions",
        "construction_stages",
    )
    return _without_source_metadata({key: source[key] for key in keys})


def model_ir_solver_semantic_hash(
    model: ModelIRDocument | dict[str, Any],
) -> str:
    projection = model_ir_solver_semantic_projection(model)
    canonical = canonicalize_model_ir_v2(projection).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _without_source_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_source_metadata(item)
            for key, item in value.items()
            if key not in {"source_id", "extensions"}
        }
    if isinstance(value, list):
        return [_without_source_metadata(item) for item in value]
    return value


def _numeric_source_id(row: dict[str, Any], kind: str, path: str) -> int:
    source_id = str(row.get("source_id", ""))
    match = _SOURCE_ID_RE.fullmatch(source_id)
    if match is None or match.group(1) != kind:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_SOURCE_ID_MISSING",
            f"{path}/source_id",
            f"Expected source ID mgt:{kind}:<positive integer>.",
        )
    value = int(match.group(2))
    if value <= 0 or value > 2_147_483_647:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_SOURCE_ID_INVALID",
            f"{path}/source_id",
            "MGT numeric IDs must be in the positive int32 range.",
        )
    return value


def _required_extension_text(
    extensions: dict[str, Any], key: str, path: str
) -> str:
    value = str(extensions.get(key, "")).strip()
    if not value:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_EXTENSION_MISSING", path, f"Required extension is missing: {key}"
        )
    return value


def _required_extension_float(row: dict[str, Any], key: str, path: str) -> float:
    extensions = row.get("extensions", row)
    try:
        value = float(extensions[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_EXTENSION_MISSING", path, f"Required numeric extension is missing: {key}"
        ) from exc
    if not math.isfinite(value) or value <= 0.0:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_EXTENSION_INVALID", path, f"Required extension must be finite and positive: {key}"
        )
    return value


def _number(value: float) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_NONFINITE_NUMBER", "/", "Canonical MGT cannot contain NaN or Infinity."
        )
    if number == 0.0:
        return "0"
    return format(number, ".17g")


def _csv_row(fields: Iterable[Any]) -> str:
    normalized = [_safe_text(value) for value in fields]
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(normalized)
    return buffer.getvalue()


def _safe_text(value: Any) -> str:
    text = str(value)
    if any(character in text for character in ("\r", "\n", "\x00", ";")):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_TEXT_NOT_SUPPORTED",
            "/",
            "MGT subset text cannot contain CR, LF, NUL, or the semicolon comment delimiter.",
        )
    return text


def _validate_supported_model_ir_subset(payload: dict[str, Any]) -> None:
    for field in ("load_combinations", "time_functions", "construction_stages"):
        if payload[field]:
            raise MGTReverseProjectionError(
                "MGT_REVERSE_MODEL_FEATURE_NOT_SUPPORTED",
                f"/{field}",
                f"Canonical Phase 0 MGT requires {field} to be empty.",
            )
    if payload["unsupported_features"]:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_UNSUPPORTED_FEATURE_LEDGER_NOT_EMPTY",
            "/unsupported_features",
            "Canonical Phase 0 MGT does not project unsupported feature records.",
        )
    if any(
        row["mapping_status"] not in {"exact", "canonicalized"}
        for row in payload["roundtrip_map"]
    ):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_ROUNDTRIP_STATUS_NOT_SUPPORTED",
            "/roundtrip_map",
            "Approximated or unsupported source mappings cannot be reverse-projected.",
        )

    provenance = payload["provenance"]
    source_units = provenance["source_units"]
    scales = provenance["unit_scales_to_si"]
    if source_units["rotation"] != "deg" or not math.isclose(
        float(scales["rotation_to_rad"]),
        math.pi / 180.0,
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_ROTATION_UNIT_NOT_SUPPORTED",
            "/provenance/source_units/rotation",
            "MIDAS BEAM angles in this subset require degree source provenance.",
        )
    provenance_extensions = provenance.get("extensions", {})
    if provenance_extensions.get("midas_mgt:version") != "9.3.0":
        raise MGTReverseProjectionError(
            "MGT_REVERSE_DIALECT_VERSION_NOT_SUPPORTED",
            "/provenance/extensions/midas_mgt:version",
            "The Phase 0 grammar is gated to MGT version 9.3.0.",
        )
    if (
        provenance_extensions.get("midas_mgt:heat_unit") != "KJ"
        or provenance_extensions.get("midas_mgt:temperature_unit") != "C"
    ):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_AUXILIARY_UNIT_NOT_SUPPORTED",
            "/provenance/extensions",
            "The Phase 0 grammar is gated to KJ/C auxiliary units.",
        )

    for family, kind in (
        ("nodes", "NODE"),
        ("materials", "MATERIAL"),
        ("sections", "SECTION"),
        ("elements", "ELEMENT"),
    ):
        source_ids = [
            _numeric_source_id(row, kind, f"/{family}/{index}")
            for index, row in enumerate(payload[family])
        ]
        if len(source_ids) != len(set(source_ids)):
            raise MGTReverseProjectionError(
                "MGT_REVERSE_DUPLICATE_SOURCE_ID",
                f"/{family}",
                f"MGT {kind} source IDs must be unique.",
            )

    case_names = [
        _required_extension_text(
            pattern["extensions"],
            "midas_mgt:source_name",
            f"/load_patterns/{index}",
        )
        for index, pattern in enumerate(payload["load_patterns"])
    ]
    if len(case_names) != len({name.casefold() for name in case_names}):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_DUPLICATE_LOAD_CASE_NAME",
            "/load_patterns",
            "MGT static load-case names must be case-insensitively unique.",
        )

    constrained_nodes = [str(row["node_id"]) for row in payload["constraints"]]
    if len(constrained_nodes) != len(set(constrained_nodes)):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_DUPLICATE_CONSTRAINT_NODE",
            "/constraints",
            "The strict subset requires one restraint record per node.",
        )
    for index, constraint in enumerate(payload["constraints"]):
        if any(
            float(value) != 0.0
            for value in constraint["prescribed_values_si"].values()
        ):
            raise MGTReverseProjectionError(
                "MGT_REVERSE_PRESCRIBED_VALUE_NOT_SUPPORTED",
                f"/constraints/{index}/prescribed_values_si",
                "The Phase 0 MGT subset supports zero-valued restraints only.",
            )


def _validate_section_derivation(
    section: dict[str, Any],
    *,
    height_m: float,
    width_m: float,
    path: str,
) -> None:
    expected = _solid_rectangle_properties(height_m=height_m, width_m=width_m)
    actual = section["parameters"]
    keys = (
        "area_m2",
        "iy_m4",
        "iz_m4",
        "torsional_constant_m4",
        "shear_area_y_m2",
        "shear_area_z_m2",
    )
    for key in keys:
        if not math.isclose(
            float(actual[key]),
            expected[key],
            rel_tol=1.0e-12,
            abs_tol=1.0e-18,
        ):
            raise MGTReverseProjectionError(
                "MGT_REVERSE_SECTION_DERIVATION_MISMATCH",
                f"{path}/parameters/{key}",
                "ModelIR section parameters do not match the preserved DBUSER/SB geometry.",
            )


def _solid_rectangle_properties(*, height_m: float, width_m: float) -> dict[str, float]:
    if not math.isfinite(height_m) or not math.isfinite(width_m):
        raise MGTReverseProjectionError(
            "MGT_REVERSE_SECTION_DIMENSION_INVALID",
            "/sections",
            "DBUSER/SB dimensions must be finite.",
        )
    if height_m <= 0.0 or width_m <= 0.0:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_SECTION_DIMENSION_INVALID",
            "/sections",
            "DBUSER/SB dimensions must be positive.",
        )
    area = height_m * width_m
    return {
        "area_m2": area,
        "iy_m4": width_m * height_m**3 / 12.0,
        "iz_m4": height_m * width_m**3 / 12.0,
        "torsional_constant_m4": rectangle_saint_venant_j(width_m, height_m),
        "shear_area_y_m2": 5.0 * area / 6.0,
        "shear_area_z_m2": 5.0 * area / 6.0,
    }


def _validated_document(
    model: ModelIRDocument | dict[str, Any],
    *,
    require_analysis_ready: bool,
) -> ModelIRDocument:
    claimed_hash = model.content_hash if isinstance(model, ModelIRDocument) else None
    payload = model.to_dict() if isinstance(model, ModelIRDocument) else model
    document = parse_model_ir_v2(
        payload, require_analysis_ready=require_analysis_ready
    )
    if claimed_hash is not None and claimed_hash != document.content_hash:
        raise MGTReverseProjectionError(
            "MGT_REVERSE_DOCUMENT_HASH_MISMATCH",
            "/",
            "ModelIRDocument hash does not match its canonical payload.",
        )
    return document
