#!/usr/bin/env python3
"""Build an honest actual-MGT-to-stateful-material binding manifest.

The manifest is deliberately descriptor-only.  It binds every parsed frame
material reference and elastic-link row to an exact implemented constitutive
family without manufacturing nonlinear parameters from elastic MGT data.  It
therefore keeps the Frame3D operator connection, shell scope, and actual-MGT
full-mesh material-coupling claims false until those gaps are implemented.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import math
from pathlib import Path
import sys
from typing import Any


PHASE1_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PHASE1_ROOT.parents[1]
SRC_ROOT = REPO_ROOT / "src"
for candidate in (PHASE1_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from parse_midas_mgt_to_json_npz import (  # noqa: E402
    _parse_elements,
    _parse_elastic_links,
    _parse_materials,
    _parse_nodes,
    _parse_sections,
)
from parse_mgt_section_material_properties import (  # noqa: E402
    load_mgt_section_material_properties,
)
from structural_analysis.assembly.stateful_corotational_frame3d_sparse import (  # noqa: E402
    STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
    StatefulCorotationalFrame3DSparseModel,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    canonical_hash,
)
from structural_analysis.materials.bilinear_link import (  # noqa: E402
    BilinearCombinedHardeningLink,
)
from structural_analysis.materials.composite_section import (  # noqa: E402
    ParallelSteelConcreteSectionMaterial,
)
from structural_analysis.materials.concrete_damage import (  # noqa: E402
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.uniaxial_plasticity import (  # noqa: E402
    BilinearCombinedHardeningSteel,
)


N1_MGT_STATEFUL_MATERIAL_BINDING_SCHEMA_VERSION = (
    "n1-mgt-stateful-material-binding-manifest.v1"
)
N1_MGT_STATEFUL_MATERIAL_BINDING_PROFILE = (
    "actual-mgt-exact-identity-to-stateful-family-descriptor.v1"
)
MGT_MATERIAL_RESOLUTION_POLICY = (
    "MATERIAL_plus_exact_normalized_DGN_MATL_unique_alias.v1"
)
EXPECTED_SOURCE_UNIT_TOKENS = ("KN", "M", "KJ", "C")
STATEFUL_FAMILY_ORDER = (
    "steel_combined_hardening",
    "asymmetric_concrete_damage",
    "parallel_steel_concrete_section",
    "bilinear_combined_hardening_link",
)

_MATERIAL_IDENTITY_BINDINGS: dict[
    tuple[str, str], tuple[str | None, str | None, str]
] = {
    ("STEEL", "q235"): (
        "steel_combined_hardening",
        BilinearCombinedHardeningSteel.__name__,
        "stateful_candidate",
    ),
    ("CONC", "c40"): (
        "asymmetric_concrete_damage",
        AsymmetricConcreteDamageMaterial.__name__,
        "stateful_candidate",
    ),
    ("CONC", "c40wbr"): (
        "asymmetric_concrete_damage",
        AsymmetricConcreteDamageMaterial.__name__,
        "stateful_candidate",
    ),
    ("CONC", "c40f"): (
        "asymmetric_concrete_damage",
        AsymmetricConcreteDamageMaterial.__name__,
        "stateful_candidate",
    ),
    ("SRC", "c40+q235"): (
        "parallel_steel_concrete_section",
        ParallelSteelConcreteSectionMaterial.__name__,
        "stateful_candidate",
    ),
    ("USER", "rigidbar"): (
        None,
        None,
        "explicit_nonstateful_rigid_bar",
    ),
}
_TRANSLATIONAL_LINK_DOF_LABELS = ("SDx", "SDy", "SDz")
_ROTATIONAL_LINK_DOF_LABELS = ("SRx", "SRy", "SRz")
_ALL_LINK_DOF_LABELS = (
    *_TRANSLATIONAL_LINK_DOF_LABELS,
    *_ROTATIONAL_LINK_DOF_LABELS,
)


class N1MGTStatefulMaterialBindingError(ValueError):
    """Raised when source bytes cannot support the strict descriptor manifest."""


def _sha256_prefixed(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _hash(value: object, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise N1MGTStatefulMaterialBindingError(
            f"{field} must be an exact sha256 digest"
        )
    return value


def _exact_keys(value: object, expected: set[str], *, field: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise N1MGTStatefulMaterialBindingError(f"{field} keys are invalid")
    return value


def _exact_int(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise N1MGTStatefulMaterialBindingError(
            f"{field} must be an exact integer >= {minimum}"
        )
    return value


def _finite(value: object, *, field: str, positive: bool = False) -> float:
    if type(value) not in (int, float) or isinstance(value, bool):
        raise N1MGTStatefulMaterialBindingError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        condition = "positive finite" if positive else "finite"
        raise N1MGTStatefulMaterialBindingError(f"{field} must be {condition}")
    return result


def _source_units(unit_rows: list[str]) -> dict[str, str]:
    if len(unit_rows) != 1:
        raise N1MGTStatefulMaterialBindingError(
            "MGT must contain exactly one UNIT data row"
        )
    tokens = tuple(part.strip().upper() for part in unit_rows[0].split(","))
    if tokens != EXPECTED_SOURCE_UNIT_TOKENS:
        raise N1MGTStatefulMaterialBindingError(
            "MGT UNIT must be exact KN,M,KJ,C for this binding profile"
        )
    return {
        "force": "kN",
        "length": "m",
        "energy": "kJ",
        "temperature": "C",
        "elastic_modulus": "kN/m^2",
        "target_material_modulus": "MPa",
        "elastic_modulus_kN_per_m2_to_MPa": "multiply_by_0.001",
        "translational_link_stiffness": "kN/m",
        "rotational_link_stiffness": "kN*m/rad",
    }


def _material_binding(
    *,
    material_id: int,
    properties: dict[str, Any],
    element_types: list[str],
    frame_element_count: int,
) -> dict[str, Any]:
    material_type = str(properties.get("type") or "").strip().upper()
    material_name = str(properties.get("name") or "").strip()
    identity = (material_type, material_name.casefold())
    try:
        target_family, target_type, classification = _MATERIAL_IDENTITY_BINDINGS[
            identity
        ]
    except KeyError as error:
        raise N1MGTStatefulMaterialBindingError(
            "unsupported exact material identity "
            f"{material_id}:{material_type}:{material_name}"
        ) from error

    modulus = _finite(
        properties.get("E_kN_per_m2"),
        field=f"material[{material_id}].E_kN_per_m2",
        positive=True,
    )
    poisson = _finite(
        properties.get("poisson"),
        field=f"material[{material_id}].poisson",
    )
    if not (-1.0 < poisson < 0.5):
        raise N1MGTStatefulMaterialBindingError(
            f"material[{material_id}].poisson is outside (-1, 0.5)"
        )
    secondary = properties.get("E_secondary_kN_per_m2")
    if target_family == "parallel_steel_concrete_section":
        secondary = _finite(
            secondary,
            field=f"material[{material_id}].E_secondary_kN_per_m2",
            positive=True,
        )
    elif secondary is not None:
        raise N1MGTStatefulMaterialBindingError(
            f"material[{material_id}] has an unsupported secondary modulus"
        )

    inherited_from = properties.get("inherited_from_material_id")
    if inherited_from is not None:
        inherited_from = _exact_int(
            inherited_from,
            field=f"material[{material_id}].inherited_from_material_id",
            minimum=1,
        )
    source_kind = (
        "DGN_MATL_exact_identity_alias" if inherited_from is not None else "MATERIAL"
    )
    return {
        "material_id": material_id,
        "source_kind": source_kind,
        "inherited_from_material_id": inherited_from,
        "material_type": material_type,
        "material_name": material_name,
        "element_types": sorted(element_types),
        "frame_element_count": frame_element_count,
        "classification": classification,
        "target_family": target_family,
        "target_material_exact_type": target_type,
        "elastic_modulus_kN_per_m2": modulus,
        "elastic_modulus_mpa": modulus * 0.001,
        "secondary_elastic_modulus_kN_per_m2": secondary,
        "secondary_elastic_modulus_mpa": (
            secondary * 0.001 if secondary is not None else None
        ),
        "poisson": poisson,
        "constitutive_parameter_complete": False,
        "operator_connected": False,
    }


def _validated_link_rows(
    *,
    raw_row_count: int,
    topology_rows: list[dict[str, Any]],
    typed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(topology_rows) != raw_row_count or len(typed_rows) != raw_row_count:
        raise N1MGTStatefulMaterialBindingError(
            "every ELASTICLINK source row must parse in both existing parsers"
        )
    topology_by_id = {int(row["id"]): row for row in topology_rows}
    if len(topology_by_id) != raw_row_count:
        raise N1MGTStatefulMaterialBindingError("duplicate elastic link id")

    bindings: list[dict[str, Any]] = []
    for row in sorted(typed_rows, key=lambda value: int(value["id"])):
        link_id = _exact_int(row.get("id"), field="elastic_link.id", minimum=1)
        if link_id not in topology_by_id:
            raise N1MGTStatefulMaterialBindingError(
                f"elastic link {link_id} is detached from topology parser"
            )
        topology = topology_by_id[link_id]
        link_type = str(row.get("link_type") or "").strip().upper()
        if link_type != "GEN" or str(topology.get("type") or "") != link_type:
            raise N1MGTStatefulMaterialBindingError(
                f"unsupported elastic link type {link_id}:{link_type}"
            )
        node_i = _exact_int(row.get("node_i"), field="elastic_link.node_i", minimum=1)
        node_j = _exact_int(row.get("node_j"), field="elastic_link.node_j", minimum=1)
        if (
            node_i != topology.get("node1")
            or node_j != topology.get("node2")
            or node_i == node_j
        ):
            raise N1MGTStatefulMaterialBindingError(
                f"elastic link {link_id} topology binding is invalid"
            )
        stiffness = row.get("stiffness")
        if type(stiffness) is not dict or set(stiffness) != set(_ALL_LINK_DOF_LABELS):
            raise N1MGTStatefulMaterialBindingError(
                f"elastic link {link_id} must provide six exact stiffness values"
            )
        normalized_stiffness: dict[str, float] = {}
        for label in _ALL_LINK_DOF_LABELS:
            value = _finite(
                stiffness[label],
                field=f"elastic_link[{link_id}].stiffness.{label}",
            )
            if value < 0.0:
                raise N1MGTStatefulMaterialBindingError(
                    f"elastic_link[{link_id}].stiffness.{label} must be nonnegative"
                )
            normalized_stiffness[label] = value
        if not any(value > 0.0 for value in normalized_stiffness.values()):
            raise N1MGTStatefulMaterialBindingError(
                f"elastic link {link_id} has no positive stiffness axis"
            )
        bindings.append(
            {
                "link_id": link_id,
                "node_i": node_i,
                "node_j": node_j,
                "link_type": link_type,
                "stiffness": normalized_stiffness,
                "target_family": "bilinear_combined_hardening_link",
                "target_material_exact_type": BilinearCombinedHardeningLink.__name__,
            }
        )
    return bindings


def _expected_blockers(metrics: dict[str, Any], source: dict[str, Any]) -> list[str]:
    blockers = [
        "constitutive_parameters_not_source_bound",
        "operator_not_connected",
    ]
    if source["dgn_alias_material_count"]:
        blockers.append("dgn_alias_engineer_review_required")
    if metrics["explicit_nonstateful_frame_element_count"]:
        blockers.append("explicit_nonstateful_rigid_bar_elements")
    if metrics["shell_element_count"]:
        blockers.append("shell_material_scope_not_supported")
    return sorted(blockers)


def build_n1_mgt_stateful_material_binding_manifest(
    mgt_path: Path,
) -> dict[str, Any]:
    """Parse ``mgt_path`` and return a deterministic fail-closed manifest."""

    path = Path(mgt_path)
    if not path.is_file():
        raise N1MGTStatefulMaterialBindingError("MGT source file is missing")
    source_bytes = path.read_bytes()
    sections, _blocks, line_count = _parse_sections(path)
    units = _source_units(sections.get("UNIT", []))

    node_rows = sections.get("NODE", [])
    nodes = _parse_nodes(node_rows)
    if len(nodes) != len(node_rows) or not nodes:
        raise N1MGTStatefulMaterialBindingError(
            "every NODE row must parse to one unique node"
        )
    element_rows = sections.get("ELEMENT", [])
    elements, element_diagnostics = _parse_elements(element_rows, set(nodes))
    if (
        len(elements) != len(element_rows)
        or element_diagnostics.get("skipped_count") != 0
        or len({int(row["id"]) for row in elements}) != len(elements)
    ):
        raise N1MGTStatefulMaterialBindingError(
            "every ELEMENT row must parse to one unique supported element"
        )

    raw_material_rows = _parse_materials(sections.get("MATERIAL", []))
    raw_material_ids = [int(row["id"]) for row in raw_material_rows]
    if (
        len(raw_material_rows) != len(sections.get("MATERIAL", []))
        or len(set(raw_material_ids)) != len(raw_material_ids)
        or not raw_material_rows
    ):
        raise N1MGTStatefulMaterialBindingError(
            "every MATERIAL row must have one unique source material id"
        )
    properties = load_mgt_section_material_properties(
        path,
        resolve_dgn_material_property_aliases=True,
    )
    source_materials = properties["source_materials"]
    if set(source_materials) != set(raw_material_ids):
        raise N1MGTStatefulMaterialBindingError(
            "every MATERIAL row must provide admissible elastic properties"
        )
    alias_audit = properties["dgn_material_property_alias_audit"]
    if alias_audit.get("contract_pass") is not True:
        raise N1MGTStatefulMaterialBindingError(
            "DGN-MATL exact identity resolution did not pass"
        )
    resolved_materials = properties["materials"]

    frame_elements = [row for row in elements if row["family"] == "beam"]
    shell_elements = [row for row in elements if row["family"] == "shell"]
    unsupported_elements = [
        row for row in elements if row["family"] not in {"beam", "shell"}
    ]
    if unsupported_elements:
        raise N1MGTStatefulMaterialBindingError(
            "actual binding only admits parsed beam and shell element families"
        )
    frame_counts = Counter(int(row["material_id"]) for row in frame_elements)
    missing_material_ids = sorted(set(frame_counts) - set(resolved_materials))
    if missing_material_ids:
        raise N1MGTStatefulMaterialBindingError(
            f"frame material ids are unresolved: {missing_material_ids}"
        )

    material_bindings: list[dict[str, Any]] = []
    for material_id in sorted(frame_counts):
        rows = [row for row in frame_elements if int(row["material_id"]) == material_id]
        material_bindings.append(
            _material_binding(
                material_id=material_id,
                properties=resolved_materials[material_id],
                element_types=sorted({str(row["type"]) for row in rows}),
                frame_element_count=len(rows),
            )
        )

    topology_links = _parse_elastic_links(
        sections.get("ELASTICLINK", []),
        set(nodes),
    )
    link_bindings = _validated_link_rows(
        raw_row_count=len(sections.get("ELASTICLINK", [])),
        topology_rows=topology_links,
        typed_rows=properties["elastic_links"],
    )
    if not link_bindings:
        raise N1MGTStatefulMaterialBindingError(
            "the four-family binding profile requires elastic link rows"
        )

    family_counts: Counter[str] = Counter()
    explicit_nonstateful_count = 0
    for row in material_bindings:
        if row["target_family"] is None:
            explicit_nonstateful_count += int(row["frame_element_count"])
        else:
            family_counts[str(row["target_family"])] += int(row["frame_element_count"])
    family_counts["bilinear_combined_hardening_link"] = len(link_bindings)
    if tuple(family for family in STATEFUL_FAMILY_ORDER if family_counts[family]) != (
        STATEFUL_FAMILY_ORDER
    ):
        raise N1MGTStatefulMaterialBindingError(
            "actual MGT binding must expose all four exact stateful families"
        )

    frame_binding_rows = []
    material_by_id = {row["material_id"]: row for row in material_bindings}
    for element in sorted(frame_elements, key=lambda row: int(row["id"])):
        binding = material_by_id[int(element["material_id"])]
        frame_binding_rows.append(
            {
                "element_id": int(element["id"]),
                "element_type": str(element["type"]),
                "node_ids": [int(node_id) for node_id in element["node_ids"]],
                "section_id": int(element["section_id"]),
                "material_id": int(element["material_id"]),
                "classification": binding["classification"],
                "target_family": binding["target_family"],
            }
        )

    stateful_member_count = sum(
        count
        for family, count in family_counts.items()
        if family != "bilinear_combined_hardening_link"
    )
    source = {
        "file_name": path.name,
        "byte_count": len(source_bytes),
        "sha256": _sha256_prefixed(source_bytes),
        "line_count": line_count,
        "source_units": units,
        "topology_parser": "parse_midas_mgt_to_json_npz.existing_strict_helpers.v1",
        "material_parser": "parse_mgt_section_material_properties.existing_parser.v1",
        "material_resolution_policy": MGT_MATERIAL_RESOLUTION_POLICY,
        "source_material_count": len(source_materials),
        "resolved_material_count": len(resolved_materials),
        "dgn_alias_material_count": int(alias_audit["alias_material_count"]),
        "dgn_alias_contract_pass": True,
        "dgn_alias_engineer_review_required": bool(
            alias_audit["engineer_review_required"]
        ),
    }
    metrics = {
        "node_count": len(nodes),
        "element_count": len(elements),
        "frame_element_count": len(frame_elements),
        "stateful_candidate_frame_element_count": stateful_member_count,
        "explicit_nonstateful_frame_element_count": explicit_nonstateful_count,
        "unresolved_frame_element_count": 0,
        "shell_element_count": len(shell_elements),
        "elastic_link_count": len(link_bindings),
        "elastic_link_axis_binding_count": len(link_bindings)
        * len(_ALL_LINK_DOF_LABELS),
        "material_binding_row_count": len(material_bindings),
        "stateful_family_count": len(STATEFUL_FAMILY_ORDER),
        "implicit_fallback_count": 0,
    }
    family_summary = [
        {
            "family": family,
            "source_object_count": int(family_counts[family]),
            "constitutive_parameter_complete": False,
            "operator_connected": False,
        }
        for family in STATEFUL_FAMILY_ORDER
    ]
    manifest: dict[str, Any] = {
        "schema_version": N1_MGT_STATEFUL_MATERIAL_BINDING_SCHEMA_VERSION,
        "profile": N1_MGT_STATEFUL_MATERIAL_BINDING_PROFILE,
        "status": "blocked",
        "source": source,
        "target": {
            "member_operator_profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
            "member_operator_exact_type": StatefulCorotationalFrame3DSparseModel.__name__,
            "member_material_exact_types": [
                BilinearCombinedHardeningSteel.__name__,
                AsymmetricConcreteDamageMaterial.__name__,
                ParallelSteelConcreteSectionMaterial.__name__,
            ],
            "link_material_exact_type": BilinearCombinedHardeningLink.__name__,
            "link_operator_profile": None,
            "operator_connected": False,
        },
        "material_bindings": material_bindings,
        "family_summary": family_summary,
        "mesh_binding": {
            "frame_element_binding_hash": canonical_hash(frame_binding_rows),
            "elastic_link_binding_hash": canonical_hash(link_bindings),
            "material_binding_hash": canonical_hash(material_bindings),
        },
        "metrics": metrics,
        "claims": {
            "actual_mgt_source_bound": True,
            "exact_material_identity_mapping": True,
            "stateful_family_descriptor_breadth": True,
            "constitutive_parameters_source_complete": False,
            "operator_connected": False,
            "actual_mgt_full_mesh_material_coupling": False,
            "implicit_material_fallback_used": False,
            "n1_closure": False,
            "g1_closure": False,
        },
        "blockers": _expected_blockers(metrics, source),
        "claim_boundary": (
            "Binds actual MGT frame material identities and GEN elastic-link "
            "stiffness rows to four exact implemented stateful-family descriptors. "
            "It does not infer nonlinear parameters, connect those descriptors to "
            "the actual Frame3D/link operators, cover shell constitutive behavior, "
            "or claim actual-MGT full-mesh material coupling or N1/G1 closure."
        ),
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    return validate_n1_mgt_stateful_material_binding_manifest(manifest)


def validate_n1_mgt_stateful_material_binding_manifest(
    manifest: object,
) -> dict[str, Any]:
    """Validate canonical shape, counts, target identities, and claim boundary."""

    payload = _exact_keys(
        manifest,
        {
            "schema_version",
            "profile",
            "status",
            "source",
            "target",
            "material_bindings",
            "family_summary",
            "mesh_binding",
            "metrics",
            "claims",
            "blockers",
            "claim_boundary",
            "manifest_hash",
        },
        field="manifest",
    )
    expected_hash = canonical_hash(
        {key: value for key, value in payload.items() if key != "manifest_hash"}
    )
    if payload["manifest_hash"] != expected_hash:
        raise N1MGTStatefulMaterialBindingError("manifest_hash is stale")
    if (
        payload["schema_version"] != N1_MGT_STATEFUL_MATERIAL_BINDING_SCHEMA_VERSION
        or payload["profile"] != N1_MGT_STATEFUL_MATERIAL_BINDING_PROFILE
        or payload["status"] != "blocked"
    ):
        raise N1MGTStatefulMaterialBindingError("manifest identity is invalid")

    source = _exact_keys(
        payload["source"],
        {
            "file_name",
            "byte_count",
            "sha256",
            "line_count",
            "source_units",
            "topology_parser",
            "material_parser",
            "material_resolution_policy",
            "source_material_count",
            "resolved_material_count",
            "dgn_alias_material_count",
            "dgn_alias_contract_pass",
            "dgn_alias_engineer_review_required",
        },
        field="source",
    )
    if (
        source["material_resolution_policy"] != MGT_MATERIAL_RESOLUTION_POLICY
        or source["dgn_alias_contract_pass"] is not True
    ):
        raise N1MGTStatefulMaterialBindingError("source resolution is invalid")
    if (
        type(source["file_name"]) is not str
        or not source["file_name"]
        or Path(source["file_name"]).name != source["file_name"]
        or source["topology_parser"]
        != "parse_midas_mgt_to_json_npz.existing_strict_helpers.v1"
        or source["material_parser"]
        != "parse_mgt_section_material_properties.existing_parser.v1"
    ):
        raise N1MGTStatefulMaterialBindingError("source identity is invalid")
    _hash(source["sha256"], field="source.sha256")
    for field in (
        "byte_count",
        "line_count",
        "source_material_count",
        "resolved_material_count",
        "dgn_alias_material_count",
    ):
        _exact_int(
            source[field],
            field=f"source.{field}",
            minimum=1 if field != "dgn_alias_material_count" else 0,
        )
    expected_units = {
        "force": "kN",
        "length": "m",
        "energy": "kJ",
        "temperature": "C",
        "elastic_modulus": "kN/m^2",
        "target_material_modulus": "MPa",
        "elastic_modulus_kN_per_m2_to_MPa": "multiply_by_0.001",
        "translational_link_stiffness": "kN/m",
        "rotational_link_stiffness": "kN*m/rad",
    }
    if source["source_units"] != expected_units:
        raise N1MGTStatefulMaterialBindingError("source units are invalid")
    if (
        type(source["dgn_alias_engineer_review_required"]) is not bool
        or source["dgn_alias_engineer_review_required"]
        is not bool(source["dgn_alias_material_count"])
        or source["resolved_material_count"]
        != source["source_material_count"] + source["dgn_alias_material_count"]
    ):
        raise N1MGTStatefulMaterialBindingError("source alias cardinality is invalid")

    target = _exact_keys(
        payload["target"],
        {
            "member_operator_profile",
            "member_operator_exact_type",
            "member_material_exact_types",
            "link_material_exact_type",
            "link_operator_profile",
            "operator_connected",
        },
        field="target",
    )
    if target != {
        "member_operator_profile": STATEFUL_COROTATIONAL_FRAME3D_SPARSE_PROFILE,
        "member_operator_exact_type": StatefulCorotationalFrame3DSparseModel.__name__,
        "member_material_exact_types": [
            BilinearCombinedHardeningSteel.__name__,
            AsymmetricConcreteDamageMaterial.__name__,
            ParallelSteelConcreteSectionMaterial.__name__,
        ],
        "link_material_exact_type": BilinearCombinedHardeningLink.__name__,
        "link_operator_profile": None,
        "operator_connected": False,
    }:
        raise N1MGTStatefulMaterialBindingError("target binding is invalid")

    metrics = _exact_keys(
        payload["metrics"],
        {
            "node_count",
            "element_count",
            "frame_element_count",
            "stateful_candidate_frame_element_count",
            "explicit_nonstateful_frame_element_count",
            "unresolved_frame_element_count",
            "shell_element_count",
            "elastic_link_count",
            "elastic_link_axis_binding_count",
            "material_binding_row_count",
            "stateful_family_count",
            "implicit_fallback_count",
        },
        field="metrics",
    )
    positive_metrics = {
        "node_count",
        "element_count",
        "frame_element_count",
        "stateful_candidate_frame_element_count",
        "elastic_link_count",
        "elastic_link_axis_binding_count",
        "material_binding_row_count",
        "stateful_family_count",
    }
    for field, value in metrics.items():
        _exact_int(
            value,
            field=f"metrics.{field}",
            minimum=1 if field in positive_metrics else 0,
        )
    if (
        metrics["element_count"]
        != metrics["frame_element_count"] + metrics["shell_element_count"]
        or metrics["frame_element_count"]
        != metrics["stateful_candidate_frame_element_count"]
        + metrics["explicit_nonstateful_frame_element_count"]
        + metrics["unresolved_frame_element_count"]
        or metrics["unresolved_frame_element_count"] != 0
        or metrics["elastic_link_axis_binding_count"]
        != metrics["elastic_link_count"] * len(_ALL_LINK_DOF_LABELS)
        or metrics["stateful_family_count"] != len(STATEFUL_FAMILY_ORDER)
        or metrics["implicit_fallback_count"] != 0
    ):
        raise N1MGTStatefulMaterialBindingError("manifest counts are inconsistent")

    rows = payload["material_bindings"]
    if type(rows) is not list or len(rows) != metrics["material_binding_row_count"]:
        raise N1MGTStatefulMaterialBindingError("material binding rows are invalid")
    ids: list[int] = []
    stateful_count = 0
    explicit_count = 0
    computed_family_counts: Counter[str] = Counter()
    for row in rows:
        row = _exact_keys(
            row,
            {
                "material_id",
                "source_kind",
                "inherited_from_material_id",
                "material_type",
                "material_name",
                "element_types",
                "frame_element_count",
                "classification",
                "target_family",
                "target_material_exact_type",
                "elastic_modulus_kN_per_m2",
                "elastic_modulus_mpa",
                "secondary_elastic_modulus_kN_per_m2",
                "secondary_elastic_modulus_mpa",
                "poisson",
                "constitutive_parameter_complete",
                "operator_connected",
            },
            field="material_binding",
        )
        material_id = _exact_int(
            row["material_id"], field="material_binding.material_id", minimum=1
        )
        ids.append(material_id)
        if (
            type(row["material_type"]) is not str
            or not row["material_type"]
            or row["material_type"] != row["material_type"].strip().upper()
            or type(row["material_name"]) is not str
            or not row["material_name"]
            or row["material_name"] != row["material_name"].strip()
            or type(row["element_types"]) is not list
            or not row["element_types"]
            or any(
                type(value) is not str or not value or value != value.strip().upper()
                for value in row["element_types"]
            )
            or row["element_types"] != sorted(set(row["element_types"]))
        ):
            raise N1MGTStatefulMaterialBindingError(
                "material binding source fields are invalid"
            )
        expected = _MATERIAL_IDENTITY_BINDINGS.get(
            (
                str(row.get("material_type") or "").strip().upper(),
                str(row.get("material_name") or "").strip().casefold(),
            )
        )
        if expected is None:
            raise N1MGTStatefulMaterialBindingError(
                "material binding contains an unsupported identity"
            )
        family, target_type, classification = expected
        if (
            row.get("target_family") != family
            or row.get("target_material_exact_type") != target_type
            or row.get("classification") != classification
            or row.get("constitutive_parameter_complete") is not False
            or row.get("operator_connected") is not False
        ):
            raise N1MGTStatefulMaterialBindingError(
                "material binding target semantics are invalid"
            )
        modulus = _finite(
            row["elastic_modulus_kN_per_m2"],
            field=f"material_binding[{material_id}].elastic_modulus_kN_per_m2",
            positive=True,
        )
        modulus_mpa = _finite(
            row["elastic_modulus_mpa"],
            field=f"material_binding[{material_id}].elastic_modulus_mpa",
            positive=True,
        )
        poisson = _finite(
            row["poisson"],
            field=f"material_binding[{material_id}].poisson",
        )
        if modulus_mpa != modulus * 0.001 or not (-1.0 < poisson < 0.5):
            raise N1MGTStatefulMaterialBindingError(
                "material binding elastic conversion is invalid"
            )
        secondary = row["secondary_elastic_modulus_kN_per_m2"]
        secondary_mpa = row["secondary_elastic_modulus_mpa"]
        if family == "parallel_steel_concrete_section":
            checked_secondary = _finite(
                secondary,
                field=(
                    f"material_binding[{material_id}]."
                    "secondary_elastic_modulus_kN_per_m2"
                ),
                positive=True,
            )
            if (
                _finite(
                    secondary_mpa,
                    field=(
                        f"material_binding[{material_id}].secondary_elastic_modulus_mpa"
                    ),
                    positive=True,
                )
                != checked_secondary * 0.001
            ):
                raise N1MGTStatefulMaterialBindingError(
                    "secondary elastic conversion is invalid"
                )
        elif secondary is not None or secondary_mpa is not None:
            raise N1MGTStatefulMaterialBindingError(
                "secondary modulus is only valid for the SRC family"
            )
        inherited = row["inherited_from_material_id"]
        if row["source_kind"] == "MATERIAL":
            if inherited is not None:
                raise N1MGTStatefulMaterialBindingError(
                    "direct MATERIAL binding cannot declare inheritance"
                )
        elif row["source_kind"] == "DGN_MATL_exact_identity_alias":
            _exact_int(
                inherited,
                field="material_binding.inherited_from_material_id",
                minimum=1,
            )
        else:
            raise N1MGTStatefulMaterialBindingError(
                "material binding source kind is invalid"
            )
        count = _exact_int(
            row.get("frame_element_count"),
            field="material_binding.frame_element_count",
            minimum=1,
        )
        if family is None:
            explicit_count += count
        else:
            stateful_count += count
            computed_family_counts[family] += count
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise N1MGTStatefulMaterialBindingError(
            "material binding ids must be unique and sorted"
        )
    if (
        stateful_count != metrics["stateful_candidate_frame_element_count"]
        or explicit_count != metrics["explicit_nonstateful_frame_element_count"]
    ):
        raise N1MGTStatefulMaterialBindingError(
            "material binding cardinality is inconsistent"
        )

    mesh_binding = _exact_keys(
        payload["mesh_binding"],
        {
            "frame_element_binding_hash",
            "elastic_link_binding_hash",
            "material_binding_hash",
        },
        field="mesh_binding",
    )
    _hash(
        mesh_binding["frame_element_binding_hash"],
        field="mesh_binding.frame_element_binding_hash",
    )
    _hash(
        mesh_binding["elastic_link_binding_hash"],
        field="mesh_binding.elastic_link_binding_hash",
    )
    if _hash(
        mesh_binding["material_binding_hash"],
        field="mesh_binding.material_binding_hash",
    ) != canonical_hash(rows):
        raise N1MGTStatefulMaterialBindingError(
            "material_binding_hash does not match material rows"
        )

    family_summary = payload["family_summary"]
    if type(family_summary) is not list or [
        row.get("family") for row in family_summary if type(row) is dict
    ] != list(STATEFUL_FAMILY_ORDER):
        raise N1MGTStatefulMaterialBindingError("family summary order is invalid")
    for row in family_summary:
        row = _exact_keys(
            row,
            {
                "family",
                "source_object_count",
                "constitutive_parameter_complete",
                "operator_connected",
            },
            field="family_summary",
        )
        expected_count = (
            metrics["elastic_link_count"]
            if row["family"] == "bilinear_combined_hardening_link"
            else computed_family_counts[row["family"]]
        )
        if (
            _exact_int(
                row.get("source_object_count"),
                field="family_summary.source_object_count",
                minimum=1,
            )
            < 1
            or row["source_object_count"] != expected_count
            or row.get("constitutive_parameter_complete") is not False
            or row.get("operator_connected") is not False
        ):
            raise N1MGTStatefulMaterialBindingError(
                "family summary semantics are invalid"
            )

    claims = payload["claims"]
    expected_claims = {
        "actual_mgt_source_bound": True,
        "exact_material_identity_mapping": True,
        "stateful_family_descriptor_breadth": True,
        "constitutive_parameters_source_complete": False,
        "operator_connected": False,
        "actual_mgt_full_mesh_material_coupling": False,
        "implicit_material_fallback_used": False,
        "n1_closure": False,
        "g1_closure": False,
    }
    if claims != expected_claims:
        raise N1MGTStatefulMaterialBindingError("claim boundary is invalid")
    if payload["blockers"] != _expected_blockers(metrics, source):
        raise N1MGTStatefulMaterialBindingError("blocker set is invalid")
    if type(payload["claim_boundary"]) is not str or not payload["claim_boundary"]:
        raise N1MGTStatefulMaterialBindingError("claim_boundary must be non-empty")
    return payload


__all__ = [
    "MGT_MATERIAL_RESOLUTION_POLICY",
    "N1_MGT_STATEFUL_MATERIAL_BINDING_PROFILE",
    "N1_MGT_STATEFUL_MATERIAL_BINDING_SCHEMA_VERSION",
    "N1MGTStatefulMaterialBindingError",
    "STATEFUL_FAMILY_ORDER",
    "build_n1_mgt_stateful_material_binding_manifest",
    "validate_n1_mgt_stateful_material_binding_manifest",
]
