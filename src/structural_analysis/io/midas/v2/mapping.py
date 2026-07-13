"""Strict document-state mapping from lossless MGT tokens to ModelIR v2."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Callable, TypeVar

from structural_analysis.io.midas.v2.classification import (
    RecordDisposition,
    default_card_disposition,
)
from structural_analysis.io.midas.v2.grammar import (
    LogicalRow as GrammarRow,
    MGTConcentratedLoad,
    MGTConstraint,
    MGTElement,
    MGTGrammarError,
    MGTMaterial,
    MGTNode,
    MGTSection,
    MGTStaticLoadCase,
    MGTStructureType,
    MGTUnit,
    parse_concentrated_load,
    parse_constraint,
    parse_element,
    parse_material,
    parse_node,
    parse_section,
    parse_static_load_case,
    parse_structure_type,
    parse_unit,
)
from structural_analysis.io.midas.v2.tokens import LogicalRow, MgtBlock, MgtDocument
from structural_analysis.io.midas.v2.writer import MGT_PHASE0_SUBSET_CONTRACT


DOF_COMPONENTS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
LOAD_COMPONENTS = ("FX", "FY", "FZ", "MX", "MY", "MZ")
_BLOCK_PRIORITY = {
    RecordDisposition.SUPPORTED_EXACT: 0,
    RecordDisposition.SUPPORTED_NORMALIZED: 1,
    RecordDisposition.PRESERVED_NONANALYTIC: 1,
    RecordDisposition.BLOCKED_UNSUPPORTED: 10,
    RecordDisposition.BLOCKED_INVALID_SYNTAX: 11,
    RecordDisposition.BLOCKED_DUPLICATE_ID: 12,
    RecordDisposition.BLOCKED_DANGLING_REFERENCE: 13,
    RecordDisposition.BLOCKED_CONTEXT_MISSING: 14,
}
_CASE_SAFE_RE = re.compile(r"[^A-Za-z0-9_.:-]+")
_T = TypeVar("_T")


@dataclass(frozen=True)
class MGTMappingOutcome:
    payload: dict[str, Any] | None
    cards: tuple[dict[str, Any], ...]
    source_mappings: tuple[dict[str, Any], ...]
    diagnostics: tuple[dict[str, Any], ...]
    duplicate_ids: tuple[str, ...]
    dangling_references: tuple[str, ...]
    fatal_syntax: bool


class _AuditBuilder:
    def __init__(self, document: MgtDocument) -> None:
        self.document = document
        self.cards: list[dict[str, Any]] = []
        self.mappings: list[dict[str, Any]] = []
        self._record_by_key: dict[tuple[int, int | None], dict[str, Any]] = {}
        for block_index, block in enumerate(document.blocks):
            if block.name == "ROOT":
                disposition = (
                    RecordDisposition.PRESERVED_NONANALYTIC
                    if not block.rows
                    else RecordDisposition.BLOCKED_INVALID_SYNTAX
                )
                reasons = () if not block.rows else ("MGT_DATA_BEFORE_FIRST_HEADER",)
            else:
                disposition, reasons = default_card_disposition(block.name)
            header_line = (
                block.header.span.line_start
                if block.header is not None
                else block.span.line_start
            )
            card = {
                "name": block.name,
                "occurrence_index": block.occurrence_index,
                "header_line": header_line,
                "row_count": len(block.rows),
                "disposition": disposition.value,
                "active_load_case": None,
                "reason_codes": list(reasons),
            }
            self.cards.append(card)
            if block.header is not None:
                self._add_record(
                    block_index,
                    None,
                    block=block,
                    row=None,
                    disposition=disposition,
                    reasons=reasons,
                )
            for row in block.rows:
                self._add_record(
                    block_index,
                    row.block_row_index,
                    block=block,
                    row=row,
                    disposition=disposition,
                    reasons=reasons,
                )

    def _add_record(
        self,
        block_index: int,
        row_index: int | None,
        *,
        block: MgtBlock,
        row: LogicalRow | None,
        disposition: RecordDisposition,
        reasons: tuple[str, ...],
    ) -> None:
        if row is None:
            assert block.header is not None
            span = block.header.span
            raw_hash = block.header.raw_fragment_sha256
            suffix = "HEADER"
        else:
            span = row.span
            raw_hash = row.raw_fragment_sha256
            suffix = f"ROW:{row.block_row_index + 1}"
        record = {
            "source_record_id": (
                f"MGT:{block.name}:{block.occurrence_index}:{suffix}"
            ),
            "source_ref": {
                "section": block.name,
                "block_occurrence": block.occurrence_index,
                "header_line": (
                    block.header.span.line_start
                    if block.header is not None
                    else span.line_start
                ),
                "line_start": span.line_start,
                "line_end": span.line_end,
                "logical_row_index": row.block_row_index if row is not None else None,
                "raw_sha256": "sha256:" + raw_hash,
            },
            "disposition": disposition.value,
            "target_refs": [],
            "transformations": [],
            "reason_codes": list(reasons),
        }
        self._record_by_key[(block_index, row_index)] = record
        self.mappings.append(record)

    def set_active_case(self, block_index: int, case_name: str | None) -> None:
        self.cards[block_index]["active_load_case"] = case_name

    def mark(
        self,
        block_index: int,
        disposition: RecordDisposition,
        reason: str,
        *,
        row_index: int | None = None,
        whole_block: bool = False,
    ) -> None:
        card = self.cards[block_index]
        current = RecordDisposition(card["disposition"])
        if _BLOCK_PRIORITY[disposition] >= _BLOCK_PRIORITY[current]:
            card["disposition"] = disposition.value
        _append_unique(card["reason_codes"], reason)
        keys = (
            [key for key in self._record_by_key if key[0] == block_index]
            if whole_block
            else [(block_index, row_index)]
        )
        for key in keys:
            record = self._record_by_key.get(key)
            if record is None:
                continue
            record["disposition"] = disposition.value
            _append_unique(record["reason_codes"], reason)

    def add_target(
        self,
        block_index: int,
        row_index: int | None,
        *,
        entity_kind: str,
        entity_id: str,
        json_pointer: str,
        transformations: tuple[str, ...] = (),
    ) -> None:
        record = self._record_by_key[(block_index, row_index)]
        record["target_refs"].append(
            {
                "entity_kind": entity_kind,
                "entity_id": entity_id,
                "json_pointer": json_pointer,
            }
        )
        for transformation in transformations:
            _append_unique(record["transformations"], transformation)


def map_mgt_document_to_model_ir(document: MgtDocument) -> MGTMappingOutcome:
    """Map only the versioned Phase 0 subset; retain a complete classification audit."""

    builder = _AuditBuilder(document)
    diagnostics: list[dict[str, Any]] = []
    duplicates: list[str] = []
    dangling: list[str] = []
    fatal = False

    for diagnostic in document.diagnostics:
        diagnostics.append(
            {
                "severity": diagnostic.severity.value,
                "code": diagnostic.code,
                "message": diagnostic.message,
                "line_start": diagnostic.span.line_start,
                "line_end": diagnostic.span.line_end,
            }
        )
        if diagnostic.severity.value == "error":
            fatal = True

    unsupported_features: list[dict[str, Any]] = []
    unsupported_index = 0
    for block_index, block in enumerate(document.blocks):
        disposition = RecordDisposition(builder.cards[block_index]["disposition"])
        if block.name == "ROOT":
            if block.rows:
                fatal = True
                _diagnostic(
                    diagnostics,
                    "MGT_DATA_BEFORE_FIRST_HEADER",
                    "Data before the first MGT header is not part of the strict dialect.",
                    block.span.line_start,
                    block.span.line_end,
                )
            continue
        if disposition is RecordDisposition.BLOCKED_UNSUPPORTED:
            unsupported_index += 1
            reason_codes = tuple(builder.cards[block_index]["reason_codes"])
            unsupported_features.append(
                {
                    "feature_id": f"UF:{unsupported_index}:{_stable_fragment(block.name)}",
                    "kind": "mgt_card_not_supported",
                    "source_entity_id": f"MGT:{block.name}:{block.occurrence_index}",
                    "disposition": "blocked",
                    "blocking": True,
                    "detail": (
                        f"*{block.name} is outside {MGT_PHASE0_SUBSET_CONTRACT}; "
                        "the record was preserved in the lossless source document."
                    ),
                    "extensions": {"midas_mgt:reason_codes": list(reason_codes)},
                }
            )
            _diagnostic(
                diagnostics,
                reason_codes[0] if reason_codes else "MGT_CARD_NOT_SUPPORTED",
                f"*{block.name} is not supported by the Phase 0 analytical subset.",
                block.span.line_start,
                block.span.line_end,
            )

    supported_with_no_header_args = {
        "VERSION",
        "UNIT",
        "STRUCTYPE",
        "NODE",
        "MATERIAL",
        "SECTION",
        "ELEMENT",
        "CONSTRAINT",
        "STLDCASE",
        "CONLOAD",
        "ENDDATA",
    }
    for block_index, block in enumerate(document.blocks):
        if block.name in supported_with_no_header_args and any(block.args):
            fatal = True
            _mark_error(
                builder,
                diagnostics,
                block_index,
                None,
                RecordDisposition.BLOCKED_INVALID_SYNTAX,
                "MGT_HEADER_ARGUMENT_NOT_ALLOWED",
                f"*{block.name} does not accept header arguments in this subset.",
                block,
            )

    version_row = _require_single_row(document, builder, diagnostics, "VERSION")
    unit_row = _require_single_row(document, builder, diagnostics, "UNIT")
    structure_row = _require_single_row(document, builder, diagnostics, "STRUCTYPE")
    end_blocks = [(index, block) for index, block in enumerate(document.blocks) if block.name == "ENDDATA"]
    if len(end_blocks) != 1 or (end_blocks and end_blocks[0][1].rows):
        fatal = True
        _diagnostic(
            diagnostics,
            "MGT_ENDDATA_CARDINALITY",
            "Exactly one empty *ENDDATA block is required.",
            None,
            None,
        )

    version: str | None = None
    units: MGTUnit | None = None
    structure: MGTStructureType | None = None
    if version_row is None or unit_row is None or structure_row is None:
        fatal = True
    else:
        version_block_index, version_source = version_row
        version = version_source.text.strip()
        if version != "9.3.0":
            fatal = True
            _mark_error(
                builder,
                diagnostics,
                version_block_index,
                version_source.block_row_index,
                RecordDisposition.BLOCKED_INVALID_SYNTAX,
                "MGT_DIALECT_VERSION_NOT_SUPPORTED",
                "The strict grammar is gated to MIDAS MGT version 9.3.0.",
                document.blocks[version_block_index],
            )
        try:
            units = parse_unit(_grammar_row(document, unit_row[1]))
            structure = parse_structure_type(
                _grammar_row(document, structure_row[1]), units
            )
            if units.heat_unit.upper() != "KJ" or units.temperature_unit.upper() != "C":
                raise MGTGrammarError(
                    "MGT_V2_AUXILIARY_UNITS",
                    "strict Phase 0 MGT requires heat unit KJ and temperature unit C",
                )
            if structure.structure_type != 0:
                raise MGTGrammarError(
                    "MGT_V2_STRUCTURE_TYPE",
                    "strict Phase 0 MGT requires 3D structure type iSTYP=0",
                )
        except MGTGrammarError as exc:
            fatal = True
            target_block, target_row = (
                (unit_row[0], unit_row[1])
                if units is None
                else (structure_row[0], structure_row[1])
            )
            _mark_grammar_error(
                builder, diagnostics, target_block, target_row, exc, document.blocks[target_block]
            )

    nodes: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    elements: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    load_patterns: list[dict[str, Any]] = []
    roundtrip_map: list[dict[str, Any]] = []
    node_ids: dict[int, str] = {}
    material_ids: dict[int, str] = {}
    section_ids: dict[int, str] = {}
    constraint_nodes: set[int] = set()
    case_by_name: dict[str, dict[str, Any]] = {}
    case_record: dict[str, tuple[int, LogicalRow]] = {}

    if units is not None and structure is not None:
        parsed_nodes, node_fatal = _parse_entity_rows(
            document,
            builder,
            diagnostics,
            "NODE",
            lambda row: parse_node(row, units),
        )
        fatal = fatal or node_fatal
        for block_index, source_row, parsed in parsed_nodes:
            assert isinstance(parsed, MGTNode)
            if parsed.id in node_ids:
                fatal = True
                duplicate = f"node:{parsed.id}"
                duplicates.append(duplicate)
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_DUPLICATE_ID,
                    "MGT_DUPLICATE_NODE_ID",
                    row_index=source_row.block_row_index,
                )
                _diagnostic(
                    diagnostics,
                    "MGT_DUPLICATE_NODE_ID",
                    f"Duplicate NODE id {parsed.id}.",
                    source_row.span.line_start,
                    source_row.span.line_end,
                )
                continue
            entity_id = f"N:{parsed.id}"
            node_ids[parsed.id] = entity_id
            index = len(nodes)
            nodes.append(
                {
                    "id": entity_id,
                    "index": index,
                    "coordinates_m": list(parsed.coordinates_m),
                    "source_id": f"mgt:NODE:{parsed.id}",
                    "extensions": {"midas_mgt:source_line": source_row.span.line_start},
                }
            )
            _roundtrip_row(roundtrip_map, f"MGT:NODE:{parsed.id}", "node", entity_id)
            builder.add_target(
                block_index,
                source_row.block_row_index,
                entity_kind="node",
                entity_id=entity_id,
                json_pointer=f"/nodes/{index}",
                transformations=("unit_conversion_length_to_m",),
            )

        parsed_materials, material_fatal = _parse_entity_rows(
            document,
            builder,
            diagnostics,
            "MATERIAL",
            lambda row: parse_material(row, units),
        )
        fatal = fatal or material_fatal
        for block_index, source_row, parsed in parsed_materials:
            assert isinstance(parsed, MGTMaterial)
            if parsed.id in material_ids:
                fatal = True
                duplicates.append(f"material:{parsed.id}")
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_DUPLICATE_ID,
                    "MGT_DUPLICATE_MATERIAL_ID",
                    row_index=source_row.block_row_index,
                )
                continue
            entity_id = f"M:{parsed.id}"
            material_ids[parsed.id] = entity_id
            index = len(materials)
            density_kg_m3 = parsed.density_n_per_m3 / structure.gravity_m_s2
            materials.append(
                {
                    "id": entity_id,
                    "index": index,
                    "law_id": "linear_elastic_isotropic",
                    "parameter_set_version": "1",
                    "parameters": {
                        "elastic_modulus_pa": parsed.youngs_modulus_pa,
                        "poisson_ratio": parsed.poisson_ratio,
                        "density_kg_m3": density_kg_m3,
                    },
                    "state_schema": {
                        "stateful": False,
                        "state_update_epoch": "none",
                        "supports_trial_commit_rollback": True,
                    },
                    "source_id": f"mgt:MATERIAL:{parsed.id}",
                    "extensions": {
                        "midas_mgt:source_type": parsed.material_type,
                        "midas_mgt:source_name": parsed.name,
                        "midas_mgt:damping_ratio": parsed.damping_ratio,
                        "midas_mgt:thermal_coefficient": parsed.thermal_expansion,
                        "midas_mgt:unit_weight_n_m3": parsed.density_n_per_m3,
                        "midas_mgt:source_line": source_row.span.line_start,
                    },
                }
            )
            _roundtrip_row(
                roundtrip_map, f"MGT:MATERIAL:{parsed.id}", "material", entity_id
            )
            builder.add_target(
                block_index,
                source_row.block_row_index,
                entity_kind="material",
                entity_id=entity_id,
                json_pointer=f"/materials/{index}",
                transformations=(
                    "unit_conversion_modulus_to_pa",
                    "unit_weight_to_mass_density_using_declared_gravity",
                ),
            )

        parsed_sections, section_fatal = _parse_entity_rows(
            document,
            builder,
            diagnostics,
            "SECTION",
            lambda row: parse_section(row, units),
        )
        fatal = fatal or section_fatal
        for block_index, source_row, parsed in parsed_sections:
            assert isinstance(parsed, MGTSection)
            if parsed.id in section_ids:
                fatal = True
                duplicates.append(f"section:{parsed.id}")
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_DUPLICATE_ID,
                    "MGT_DUPLICATE_SECTION_ID",
                    row_index=source_row.block_row_index,
                )
                continue
            entity_id = f"S:{parsed.id}"
            section_ids[parsed.id] = entity_id
            index = len(sections)
            sections.append(
                {
                    "id": entity_id,
                    "index": index,
                    "family_id": "frame_3d",
                    "parameter_set_version": "1",
                    "parameters": {
                        "area_m2": parsed.area_m2,
                        "iy_m4": parsed.iy_m4,
                        "iz_m4": parsed.iz_m4,
                        "torsional_constant_m4": parsed.j_m4,
                        "shear_area_y_m2": parsed.shear_area_y_m2,
                        "shear_area_z_m2": parsed.shear_area_z_m2,
                    },
                    "source_id": f"mgt:SECTION:{parsed.id}",
                    "extensions": {
                        "midas_mgt:source_type": parsed.section_type,
                        "midas_mgt:source_name": parsed.name,
                        "midas_mgt:shape": parsed.shape,
                        "midas_mgt:height_m": parsed.height_m,
                        "midas_mgt:width_m": parsed.width_m,
                        "midas_mgt:source_line": source_row.span.line_start,
                    },
                }
            )
            _roundtrip_row(
                roundtrip_map, f"MGT:SECTION:{parsed.id}", "section", entity_id
            )
            builder.add_target(
                block_index,
                source_row.block_row_index,
                entity_kind="section",
                entity_id=entity_id,
                json_pointer=f"/sections/{index}",
                transformations=(
                    "unit_conversion_section_geometry_to_si",
                    "dbuser_sb_property_derivation",
                ),
            )

        parsed_elements, element_fatal = _parse_entity_rows(
            document, builder, diagnostics, "ELEMENT", parse_element
        )
        fatal = fatal or element_fatal
        element_source_ids: set[int] = set()
        for block_index, source_row, parsed in parsed_elements:
            assert isinstance(parsed, MGTElement)
            missing = []
            for kind, source_id, table in (
                ("node", parsed.node_i, node_ids),
                ("node", parsed.node_j, node_ids),
                ("material", parsed.material_id, material_ids),
                ("section", parsed.section_id, section_ids),
            ):
                if source_id not in table:
                    missing.append(f"{kind}:{source_id}")
            if parsed.id in element_source_ids:
                fatal = True
                duplicates.append(f"element:{parsed.id}")
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_DUPLICATE_ID,
                    "MGT_DUPLICATE_ELEMENT_ID",
                    row_index=source_row.block_row_index,
                )
                continue
            if missing:
                fatal = True
                dangling.extend(f"element:{parsed.id}->{value}" for value in missing)
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_DANGLING_REFERENCE,
                    "MGT_ELEMENT_DANGLING_REFERENCE",
                    row_index=source_row.block_row_index,
                )
                continue
            element_source_ids.add(parsed.id)
            entity_id = f"E:{parsed.id}"
            index = len(elements)
            elements.append(
                {
                    "id": entity_id,
                    "index": index,
                    "type": "frame_3d",
                    "formulation": "euler_bernoulli_3d",
                    "node_ids": [node_ids[parsed.node_i], node_ids[parsed.node_j]],
                    "material_id": material_ids[parsed.material_id],
                    "section_id": section_ids[parsed.section_id],
                    "local_axis_rotation_rad": parsed.angle_rad,
                    "offsets": {
                        "i_global_m": [0.0, 0.0, 0.0],
                        "j_global_m": [0.0, 0.0, 0.0],
                    },
                    "releases": {"i": [], "j": []},
                    "source_id": f"mgt:ELEMENT:{parsed.id}",
                    "extensions": {
                        "midas_mgt:source_type": parsed.element_type,
                        "midas_mgt:source_angle_deg": parsed.angle_deg,
                        "midas_mgt:subtype": parsed.subtype,
                        "midas_mgt:source_line": source_row.span.line_start,
                    },
                }
            )
            _roundtrip_row(
                roundtrip_map, f"MGT:ELEMENT:{parsed.id}", "element", entity_id
            )
            builder.add_target(
                block_index,
                source_row.block_row_index,
                entity_kind="element",
                entity_id=entity_id,
                json_pointer=f"/elements/{index}",
                transformations=("angle_degree_to_radian", "zero_offset_release_contract"),
            )

        parsed_constraints, constraint_fatal = _parse_entity_rows(
            document, builder, diagnostics, "CONSTRAINT", parse_constraint
        )
        fatal = fatal or constraint_fatal
        for block_index, source_row, parsed in parsed_constraints:
            assert isinstance(parsed, MGTConstraint)
            if not any(parsed.restraint_mask):
                fatal = True
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_INVALID_SYNTAX,
                    "MGT_CONSTRAINT_EMPTY_MASK",
                    row_index=source_row.block_row_index,
                )
                continue
            row_targets: list[tuple[str, int]] = []
            for source_node_id in parsed.node_ids:
                if source_node_id not in node_ids:
                    fatal = True
                    dangling.append(f"constraint->{source_node_id}")
                    builder.mark(
                        block_index,
                        RecordDisposition.BLOCKED_DANGLING_REFERENCE,
                        "MGT_CONSTRAINT_DANGLING_NODE",
                        row_index=source_row.block_row_index,
                    )
                    continue
                if source_node_id in constraint_nodes:
                    fatal = True
                    duplicates.append(f"constraint_node:{source_node_id}")
                    builder.mark(
                        block_index,
                        RecordDisposition.BLOCKED_DUPLICATE_ID,
                        "MGT_DUPLICATE_CONSTRAINT_NODE",
                        row_index=source_row.block_row_index,
                    )
                    continue
                constraint_nodes.add(source_node_id)
                entity_id = f"BC:{source_node_id}"
                index = len(constraints)
                restrained_dofs = [
                    dof
                    for dof, restrained in zip(
                        DOF_COMPONENTS, parsed.restraint_mask, strict=True
                    )
                    if restrained
                ]
                constraints.append(
                    {
                        "id": entity_id,
                        "index": index,
                        "type": "fixed_dofs",
                        "node_id": node_ids[source_node_id],
                        "dofs": restrained_dofs,
                        "prescribed_values_si": {dof: 0.0 for dof in restrained_dofs},
                        "source_id": (
                            f"mgt:CONSTRAINT:{block_index + 1}:{source_node_id}"
                        ),
                        "extensions": {
                            "midas_mgt:restraint_code": parsed.restraint_code,
                            "midas_mgt:group": parsed.group,
                            "midas_mgt:source_line": source_row.span.line_start,
                        },
                    }
                )
                _roundtrip_row(
                    roundtrip_map,
                    f"MGT:CONSTRAINT:{block_index + 1}:{source_node_id}",
                    "constraint",
                    entity_id,
                )
                row_targets.append((entity_id, index))
            for entity_id, index in row_targets:
                builder.add_target(
                    block_index,
                    source_row.block_row_index,
                    entity_kind="constraint",
                    entity_id=entity_id,
                    json_pointer=f"/constraints/{index}",
                    transformations=("node_range_expansion", "dof_mask_normalization"),
                )

        parsed_cases, case_fatal = _parse_entity_rows(
            document, builder, diagnostics, "STLDCASE", parse_static_load_case
        )
        fatal = fatal or case_fatal
        for block_index, source_row, parsed in parsed_cases:
            assert isinstance(parsed, MGTStaticLoadCase)
            case_key = parsed.name.casefold()
            if case_key in case_by_name:
                fatal = True
                duplicates.append(f"load_case:{parsed.name}")
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_DUPLICATE_ID,
                    "MGT_DUPLICATE_LOAD_CASE_NAME",
                    row_index=source_row.block_row_index,
                )
                continue
            entity_id = _load_case_id(parsed.name)
            index = len(load_patterns)
            pattern = {
                "id": entity_id,
                "index": index,
                "analysis_type": "linear_static",
                "self_weight": [0.0, 0.0, 0.0],
                "nodal_loads": [],
                "source_id": f"mgt:STLDCASE:{parsed.name}",
                "extensions": {
                    "midas_mgt:source_name": parsed.name,
                    "midas_mgt:load_type": parsed.load_type,
                    "midas_mgt:description": parsed.description,
                    "midas_mgt:source_line": source_row.span.line_start,
                },
            }
            case_by_name[case_key] = pattern
            case_record[case_key] = (block_index, source_row)
            load_patterns.append(pattern)
            _roundtrip_row(
                roundtrip_map,
                f"MGT:STLDCASE:{parsed.name}",
                "load_pattern",
                entity_id,
            )
            builder.add_target(
                block_index,
                source_row.block_row_index,
                entity_kind="load_pattern",
                entity_id=entity_id,
                json_pointer=f"/load_patterns/{index}",
                transformations=("load_case_id_canonicalization",),
            )

        active_case_key: str | None = None
        for block_index, block in enumerate(document.blocks):
            if block.name == "USE-STLD":
                if len(block.args) != 1 or not block.args[0].strip():
                    fatal = True
                    active_case_key = None
                    _mark_error(
                        builder,
                        diagnostics,
                        block_index,
                        None,
                        RecordDisposition.BLOCKED_CONTEXT_MISSING,
                        "MGT_USE_STLD_CONTEXT_MISSING",
                        "*USE-STLD requires exactly one declared static load-case name.",
                        block,
                    )
                    continue
                requested = block.args[0].strip()
                requested_key = requested.casefold()
                builder.set_active_case(block_index, requested)
                if requested_key not in case_by_name:
                    fatal = True
                    active_case_key = None
                    dangling.append(f"use_stld->{requested}")
                    _mark_error(
                        builder,
                        diagnostics,
                        block_index,
                        None,
                        RecordDisposition.BLOCKED_DANGLING_REFERENCE,
                        "MGT_USE_STLD_UNKNOWN_CASE",
                        f"*USE-STLD references undeclared case {requested!r}.",
                        block,
                    )
                    continue
                active_case_key = requested_key
                pattern = case_by_name[active_case_key]
                builder.add_target(
                    block_index,
                    None,
                    entity_kind="load_pattern",
                    entity_id=str(pattern["id"]),
                    json_pointer=f"/load_patterns/{pattern['index']}",
                    transformations=("load_case_context_binding",),
                )
                continue
            if block.name != "CONLOAD":
                continue
            active_name = (
                str(case_by_name[active_case_key]["extensions"]["midas_mgt:source_name"])
                if active_case_key is not None
                else None
            )
            builder.set_active_case(block_index, active_name)
            if active_case_key is None:
                fatal = True
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_CONTEXT_MISSING,
                    "MGT_CONLOAD_CONTEXT_MISSING",
                    whole_block=True,
                )
                _diagnostic(
                    diagnostics,
                    "MGT_CONLOAD_CONTEXT_MISSING",
                    "*CONLOAD must follow a valid *USE-STLD context.",
                    block.span.line_start,
                    block.span.line_end,
                )
                continue
            pattern = case_by_name[active_case_key]
            for source_row in block.rows:
                try:
                    parsed_load = parse_concentrated_load(
                        _grammar_row(document, source_row), units
                    )
                except MGTGrammarError as exc:
                    fatal = True
                    _mark_grammar_error(
                        builder, diagnostics, block_index, source_row, exc, block
                    )
                    continue
                _append_concentrated_loads(
                    parsed_load,
                    source_row,
                    block_index,
                    pattern,
                    node_ids,
                    builder,
                    dangling,
                )
                if any(node_id not in node_ids for node_id in parsed_load.node_ids):
                    fatal = True

        for case_key, pattern in case_by_name.items():
            loads = pattern["nodal_loads"]
            if not loads or not any(
                any(float(value) != 0.0 for value in load["components_si"].values())
                for load in loads
            ):
                fatal = True
                block_index, source_row = case_record[case_key]
                builder.mark(
                    block_index,
                    RecordDisposition.BLOCKED_CONTEXT_MISSING,
                    "MGT_LOAD_CASE_HAS_NO_NONZERO_CONLOAD",
                    row_index=source_row.block_row_index,
                )
                _diagnostic(
                    diagnostics,
                    "MGT_LOAD_CASE_HAS_NO_NONZERO_CONLOAD",
                    f"Static load case {pattern['extensions']['midas_mgt:source_name']!r} "
                    "has no non-zero concentrated load.",
                    source_row.span.line_start,
                    source_row.span.line_end,
                )

    required_collections = {
        "NODE": nodes,
        "MATERIAL": materials,
        "SECTION": sections,
        "ELEMENT": elements,
        "CONSTRAINT": constraints,
        "STLDCASE": load_patterns,
    }
    for card, collection in required_collections.items():
        if not collection:
            fatal = True
            _diagnostic(
                diagnostics,
                f"MGT_REQUIRED_{card}_MISSING",
                f"At least one successfully mapped *{card} record is required.",
                None,
                None,
            )

    payload: dict[str, Any] | None = None
    if not fatal and units is not None and structure is not None and version is not None:
        source_sha = "sha256:" + document.source.sha256
        payload = {
            "schema_version": "structural-analysis-model-ir.v2",
            "model_id": f"MGT:{document.source.sha256[:24]}",
            "capability_profile": "engine_v2_phase0_linear_3d",
            "provenance": {
                "source_format": "midas_mgt",
                "source_ref": document.source.source_name,
                "source_sha256": source_sha,
                "normalizer_id": "midas-mgt-v2-adapter",
                "normalizer_version": "1",
                "source_units": {
                    "length": units.length_unit,
                    "force": units.force_unit,
                    "mass": "kg",
                    "time": "s",
                    "rotation": "deg",
                },
                "unit_scales_to_si": {
                    "length_to_m": units.length_to_m,
                    "force_to_n": units.force_to_n,
                    "mass_to_kg": 1.0,
                    "time_to_s": 1.0,
                    "rotation_to_rad": math.pi / 180.0,
                },
                "extensions": {
                    "midas_mgt:subset_contract": MGT_PHASE0_SUBSET_CONTRACT,
                    "midas_mgt:version": version,
                    "midas_mgt:heat_unit": units.heat_unit.upper(),
                    "midas_mgt:temperature_unit": units.temperature_unit.upper(),
                    "midas_mgt:gravity_m_s2": structure.gravity_m_s2,
                    "midas_mgt:den_semantics": "unit_weight_divided_by_declared_gravity",
                },
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
            "dof_components": list(DOF_COMPONENTS),
            "nodes": nodes,
            "materials": materials,
            "sections": sections,
            "elements": elements,
            "constraints": constraints,
            "load_patterns": load_patterns,
            "load_combinations": [],
            "time_functions": [],
            "construction_stages": [],
            "roundtrip_map": roundtrip_map,
            "unsupported_features": unsupported_features,
            "extensions": {
                "midas_mgt:subset_contract": MGT_PHASE0_SUBSET_CONTRACT,
                "midas_mgt:parse_lossless": True,
                "midas_mgt:geometry_exact": True,
                "midas_mgt:properties_normalized": True,
                "midas_mgt:boundary_exact": True,
                "midas_mgt:loads_exact_by_case": True,
            },
        }

        if version_row is not None:
            builder.add_target(
                version_row[0],
                version_row[1].block_row_index,
                entity_kind="model",
                entity_id=str(payload["model_id"]),
                json_pointer="/provenance/extensions/midas_mgt:version",
                transformations=("dialect_version_gate",),
            )
        if unit_row is not None:
            builder.add_target(
                unit_row[0],
                unit_row[1].block_row_index,
                entity_kind="model",
                entity_id=str(payload["model_id"]),
                json_pointer="/provenance/source_units",
                transformations=("unit_system_normalization",),
            )
        if structure_row is not None:
            builder.add_target(
                structure_row[0],
                structure_row[1].block_row_index,
                entity_kind="model",
                entity_id=str(payload["model_id"]),
                json_pointer="/provenance/extensions/midas_mgt:gravity_m_s2",
                transformations=("gravity_length_unit_conversion",),
            )

    return MGTMappingOutcome(
        payload=payload,
        cards=tuple(builder.cards),
        source_mappings=tuple(builder.mappings),
        diagnostics=tuple(diagnostics),
        duplicate_ids=tuple(sorted(set(duplicates))),
        dangling_references=tuple(sorted(set(dangling))),
        fatal_syntax=fatal,
    )


def _parse_entity_rows(
    document: MgtDocument,
    builder: _AuditBuilder,
    diagnostics: list[dict[str, Any]],
    card_name: str,
    parser: Callable[[GrammarRow], _T],
) -> tuple[list[tuple[int, LogicalRow, _T]], bool]:
    parsed: list[tuple[int, LogicalRow, _T]] = []
    fatal = False
    rows = _rows(document, card_name)
    if not rows:
        return parsed, True
    for block_index, source_row in rows:
        try:
            value = parser(_grammar_row(document, source_row))
        except MGTGrammarError as exc:
            fatal = True
            _mark_grammar_error(
                builder,
                diagnostics,
                block_index,
                source_row,
                exc,
                document.blocks[block_index],
            )
            continue
        parsed.append((block_index, source_row, value))
    return parsed, fatal


def _append_concentrated_loads(
    parsed: MGTConcentratedLoad,
    source_row: LogicalRow,
    block_index: int,
    pattern: dict[str, Any],
    node_ids: dict[int, str],
    builder: _AuditBuilder,
    dangling: list[str],
) -> None:
    for source_node_id in parsed.node_ids:
        if source_node_id not in node_ids:
            dangling.append(f"conload:{pattern['id']}->node:{source_node_id}")
            builder.mark(
                block_index,
                RecordDisposition.BLOCKED_DANGLING_REFERENCE,
                "MGT_CONLOAD_DANGLING_NODE",
                row_index=source_row.block_row_index,
            )
            continue
        load_index = len(pattern["nodal_loads"])
        load_id = f"L:{pattern['index']}:{load_index}"
        pattern["nodal_loads"].append(
            {
                "id": load_id,
                "index": load_index,
                "node_id": node_ids[source_node_id],
                "components_si": dict(
                    zip(
                        LOAD_COMPONENTS,
                        (*parsed.forces_n, *parsed.moments_nm),
                        strict=True,
                    )
                ),
                "source_id": (
                    f"mgt:CONLOAD:{block_index + 1}:{source_row.block_row_index + 1}:"
                    f"{source_node_id}"
                ),
                "extensions": {
                    "midas_mgt:group": parsed.group,
                    "midas_mgt:structure_type_name": parsed.structure_type_name,
                    "midas_mgt:source_line": source_row.span.line_start,
                },
            }
        )
        builder.add_target(
            block_index,
            source_row.block_row_index,
            entity_kind="nodal_load",
            entity_id=load_id,
            json_pointer=(
                f"/load_patterns/{pattern['index']}/nodal_loads/{load_index}"
            ),
            transformations=(
                "load_case_context_binding",
                "node_range_expansion",
                "force_and_moment_unit_conversion",
            ),
        )


def _require_single_row(
    document: MgtDocument,
    builder: _AuditBuilder,
    diagnostics: list[dict[str, Any]],
    card_name: str,
) -> tuple[int, LogicalRow] | None:
    rows = _rows(document, card_name)
    if len(rows) == 1:
        return rows[0]
    for block_index, source_row in rows:
        builder.mark(
            block_index,
            RecordDisposition.BLOCKED_INVALID_SYNTAX,
            f"MGT_{card_name}_CARDINALITY",
            row_index=source_row.block_row_index,
        )
    _diagnostic(
        diagnostics,
        f"MGT_{card_name}_CARDINALITY",
        f"Exactly one *{card_name} data row is required; found {len(rows)}.",
        None,
        None,
    )
    return None


def _rows(document: MgtDocument, card_name: str) -> list[tuple[int, LogicalRow]]:
    return [
        (block_index, row)
        for block_index, block in enumerate(document.blocks)
        if block.name == card_name
        for row in block.rows
    ]


def _grammar_row(document: MgtDocument, row: LogicalRow) -> GrammarRow:
    return GrammarRow(
        text=row.text,
        line_number=row.span.line_start,
        source=document.source.source_name,
    )


def _mark_grammar_error(
    builder: _AuditBuilder,
    diagnostics: list[dict[str, Any]],
    block_index: int,
    row: LogicalRow,
    error: MGTGrammarError,
    block: MgtBlock,
) -> None:
    _mark_error(
        builder,
        diagnostics,
        block_index,
        row.block_row_index,
        RecordDisposition.BLOCKED_INVALID_SYNTAX,
        error.code,
        error.message,
        block,
        line_start=row.span.line_start,
        line_end=row.span.line_end,
    )


def _mark_error(
    builder: _AuditBuilder,
    diagnostics: list[dict[str, Any]],
    block_index: int,
    row_index: int | None,
    disposition: RecordDisposition,
    code: str,
    message: str,
    block: MgtBlock,
    *,
    line_start: int | None = None,
    line_end: int | None = None,
) -> None:
    builder.mark(block_index, disposition, code, row_index=row_index)
    _diagnostic(
        diagnostics,
        code,
        message,
        line_start if line_start is not None else block.span.line_start,
        line_end if line_end is not None else block.span.line_end,
    )


def _diagnostic(
    diagnostics: list[dict[str, Any]],
    code: str,
    message: str,
    line_start: int | None,
    line_end: int | None,
) -> None:
    diagnostics.append(
        {
            "severity": "error",
            "code": code,
            "message": message,
            "line_start": line_start,
            "line_end": line_end,
        }
    )


def _roundtrip_row(
    rows: list[dict[str, Any]],
    source_entity_id: str,
    entity_kind: str,
    model_ir_entity_id: str,
) -> None:
    rows.append(
        {
            "source_entity_id": source_entity_id,
            "entity_kind": entity_kind,
            "model_ir_entity_id": model_ir_entity_id,
            "mapping_status": "canonicalized",
            "extensions": {"midas_mgt:subset_contract": MGT_PHASE0_SUBSET_CONTRACT},
        }
    )


def _load_case_id(name: str) -> str:
    normalized = _CASE_SAFE_RE.sub("_", name).strip("_.:-") or "CASE"
    encoded = name.encode("utf-8")
    if normalized != name or len(normalized) > 96:
        normalized = normalized[:80] + ":" + hashlib.sha256(encoded).hexdigest()[:12]
    return "LC:" + normalized


def _stable_fragment(value: str) -> str:
    normalized = _CASE_SAFE_RE.sub("_", value).strip("_.:-") or "CARD"
    return normalized[:64]


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
