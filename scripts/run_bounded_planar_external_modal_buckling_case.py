#!/usr/bin/env python3
"""Execute one packaged modal/buckling case in OpenSees or CalculiX."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any, NoReturn


SCHEMA_VERSION = "bounded-planar-external-modal-buckling-result.v1"
PACKAGE_ID = "bounded-planar-modal-buckling-v1"
EXPECTED_OPENSEES_VERSION = "3.7.1"
EXPECTED_CALCULIX_VERSION = "2.17"
ZERO_HASH = "sha256:" + "0" * 64
DOF_INDEX = {"UX": 1, "UY": 2, "UZ": 3, "RX": 4, "RY": 5, "RZ": 6}


class PackagedExternalCaseError(ValueError):
    """Stable fail-closed error for a packaged external execution."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise PackagedExternalCaseError(code)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackagedExternalCaseError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _finite_rows(values: object, code: str) -> list[list[float]]:
    if not isinstance(values, list):
        _fail(code)
    rows: list[list[float]] = []
    for row in values:
        if not isinstance(row, list):
            _fail(code)
        numbers = [float(value) for value in row]
        if not numbers or any(not math.isfinite(value) for value in numbers):
            _fail(code)
        rows.append(numbers)
    return rows


def _package_case(
    *, package_root: Path, case_id: str, model_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(package_root / "manifest.json", "package_manifest_invalid")
    if manifest.get("package_id") != PACKAGE_ID:
        _fail("package_identity_invalid")
    if manifest.get("artifact_hash") != _artifact_hash(manifest):
        _fail("package_manifest_hash_invalid")
    rows = [row for row in manifest.get("cases", []) if row.get("case_id") == case_id]
    if len(rows) != 1:
        _fail("package_case_identity_invalid")
    case = rows[0]
    expected_model = (package_root / case["model"]["path"]).resolve()
    if model_path.resolve() != expected_model:
        _fail("package_model_path_invalid")
    if _file_hash(model_path) != case["model"]["file_sha256"]:
        _fail("package_model_hash_invalid")
    runner = Path(__file__).resolve()
    expected_runner = (package_root / case["external_runner"]["path"]).resolve()
    if runner != expected_runner:
        _fail("package_runner_path_invalid")
    if _file_hash(runner) != case["external_runner"]["file_sha256"]:
        _fail("package_runner_hash_invalid")
    return manifest, case


def _single_material_section(model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    materials = model.get("materials")
    sections = model.get("sections")
    if not isinstance(materials, list) or len(materials) != 1:
        _fail("external_model_material_set_invalid")
    if not isinstance(sections, list) or len(sections) != 1:
        _fail("external_model_section_set_invalid")
    return materials[0], sections[0]


def _run_opensees(model: dict[str, Any], case_id: str) -> dict[str, Any]:
    try:
        import openseespy.opensees as ops
    except ImportError as exc:
        raise PackagedExternalCaseError("opensees_runtime_unavailable") from exc
    version = str(ops.version())
    if version != EXPECTED_OPENSEES_VERSION:
        _fail("opensees_runtime_version_invalid")
    material, section = _single_material_section(model)
    nodes = model.get("nodes")
    elements = model.get("elements")
    if not isinstance(nodes, list) or not isinstance(elements, list):
        _fail("external_model_topology_invalid")
    node_tags = {str(row["id"]): index + 1 for index, row in enumerate(nodes)}
    if len(node_tags) != len(nodes):
        _fail("external_model_node_id_invalid")
    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    for row in nodes:
        coordinates = [float(value) for value in row["coordinates"]]
        if len(coordinates) != 3 or any(not math.isfinite(value) for value in coordinates):
            _fail("external_model_node_coordinates_invalid")
        ops.node(node_tags[str(row["id"])], *coordinates)
    constrained: dict[str, set[str]] = {node_id: set() for node_id in node_tags}
    for support in model.get("supports", []):
        node_id = str(support.get("node") or "")
        if node_id not in constrained:
            _fail("external_model_support_node_invalid")
        dofs = support.get("dofs")
        constrained[node_id].update(DOF_INDEX if dofs == "all" else dofs)
    for node_id, dofs in constrained.items():
        ops.fix(node_tags[node_id], *(int(name in dofs) for name in DOF_INDEX))
    e = float(material["elastic_modulus"])
    nu = float(material["poisson_ratio"])
    density = float(material["density"])
    area = float(section["area"])
    iy = float(section["iy"])
    iz = float(section["iz"])
    torsion = float(section["torsional_constant"])
    values = (e, nu, density, area, iy, iz, torsion)
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        _fail("external_model_properties_invalid")
    g = e / (2.0 * (1.0 + nu))
    ops.geomTransf("Linear", 1, 0.0, 0.0, 1.0)
    line_mass = density * area / 1000.0
    for index, element in enumerate(elements, start=1):
        connectivity = element.get("nodes")
        if not isinstance(connectivity, list) or len(connectivity) != 2:
            _fail("external_model_element_connectivity_invalid")
        ops.element(
            "elasticBeamColumn",
            index,
            node_tags[str(connectivity[0])],
            node_tags[str(connectivity[1])],
            area,
            e,
            g,
            torsion,
            iy,
            iz,
            1,
            "-mass",
            line_mass,
            "-cMass",
        )
    requested = 12 if case_id == "bounded_planar_modal_rigid_mode" else 2
    eigenvalues = [float(value) for value in ops.eigen("-fullGenLapack", requested)]
    if len(eigenvalues) != requested or any(not math.isfinite(value) for value in eigenvalues):
        _fail("opensees_modal_eigenvalues_invalid")
    scale = max((abs(value) for value in eigenvalues), default=0.0)
    threshold = max(1.0e-12, 1.0e-9 * scale)
    rigid_count = sum(abs(value) <= threshold for value in eigenvalues)
    mode_vectors: list[list[float]] = []
    for mode in range(1, requested + 1):
        mode_vectors.append(
            [
                float(ops.nodeEigenvector(node_tags[str(node["id"])], mode, dof))
                for node in nodes
                for dof in range(1, 7)
            ]
        )
    ops.wipe()
    return {
        "solver_version": version,
        "eigenvalues": eigenvalues,
        "rigid_mode_count": rigid_count,
        "mode_vectors": _finite_rows(mode_vectors, "opensees_modal_vectors_invalid"),
    }


def _calculix_b32_mapping(
    model: dict[str, Any],
    *,
    tags: dict[str, int],
    elements: list[dict[str, Any]],
    section: dict[str, Any],
) -> tuple[list[str], float]:
    metadata = model.get("metadata")
    if not isinstance(metadata, dict):
        _fail("calculix_b32_mapping_missing")
    if metadata.get("external_element_formulation") != "CalculiX_B32":
        _fail("calculix_b32_formulation_invalid")
    if metadata.get("external_section_geometry") != "circle_diameter_0.12m":
        _fail("calculix_b32_section_geometry_invalid")
    mapping = metadata.get("external_discretization")
    if not isinstance(mapping, dict):
        _fail("calculix_b32_mapping_missing")
    if mapping.get("schema_version") != "bounded-planar-calculix-b32-mapping.v1":
        _fail("calculix_b32_mapping_schema_invalid")
    if mapping.get("section_type") != "CIRC":
        _fail("calculix_b32_section_type_invalid")

    diameter = float(mapping.get("diameter_m", math.nan))
    if not math.isfinite(diameter) or diameter <= 0.0:
        _fail("calculix_b32_diameter_invalid")
    expected_area = math.pi * diameter**2 / 4.0
    expected_inertia = math.pi * diameter**4 / 64.0
    expected_section_values = {
        "area": expected_area,
        "iy": expected_inertia,
        "iz": expected_inertia,
        "torsional_constant": 2.0 * expected_inertia,
        "width": diameter,
        "depth": diameter,
    }
    for field, expected in expected_section_values.items():
        actual = float(section.get(field, math.nan))
        if not math.isfinite(actual) or not math.isclose(
            actual, expected, rel_tol=1.0e-12, abs_tol=1.0e-15
        ):
            _fail(f"calculix_b32_section_property_invalid:{field}")

    linear_count = mapping.get("product_linear_elements_per_member")
    quadratic_count = mapping.get("calculix_quadratic_elements_per_member")
    if (
        isinstance(linear_count, bool)
        or not isinstance(linear_count, int)
        or isinstance(quadratic_count, bool)
        or not isinstance(quadratic_count, int)
        or linear_count <= 0
        or quadratic_count <= 0
        or linear_count != 2 * quadratic_count
    ):
        _fail("calculix_b32_mapping_count_invalid")

    canonical_edges: list[tuple[str, str]] = []
    for element in elements:
        connectivity = element.get("nodes")
        if (
            element.get("type") != "frame"
            or not isinstance(connectivity, list)
            or len(connectivity) != 2
        ):
            _fail("calculix_b32_product_element_invalid")
        edge = (str(connectivity[0]), str(connectivity[1]))
        if edge[0] not in tags or edge[1] not in tags or edge[0] == edge[1]:
            _fail("calculix_b32_product_element_invalid")
        canonical_edges.append(edge)
    if len(Counter(canonical_edges)) != len(canonical_edges):
        _fail("calculix_b32_product_element_duplicate")

    members = mapping.get("member_paths")
    if not isinstance(members, list) or len(members) != 3:
        _fail("calculix_b32_member_paths_invalid")
    expected_member_ids = ("C1", "B1", "C2")
    mapped_edges: list[tuple[str, str]] = []
    mapped_nodes: set[str] = set()
    element_lines: list[str] = []
    for member_index, member in enumerate(members):
        if not isinstance(member, dict) or member.get("member_id") != expected_member_ids[
            member_index
        ]:
            _fail("calculix_b32_member_paths_invalid")
        node_ids = member.get("node_ids")
        if (
            not isinstance(node_ids, list)
            or len(node_ids) != linear_count + 1
            or len(set(node_ids)) != len(node_ids)
            or any(not isinstance(node_id, str) or node_id not in tags for node_id in node_ids)
        ):
            _fail("calculix_b32_member_path_nodes_invalid")
        mapped_nodes.update(node_ids)
        mapped_edges.extend(zip(node_ids, node_ids[1:]))
        for index in range(quadratic_count):
            start, middle, end = node_ids[2 * index : 2 * index + 3]
            element_lines.append(
                f"{len(element_lines) + 1}, {tags[start]}, {tags[middle]}, {tags[end]}"
            )
    if Counter(mapped_edges) != Counter(canonical_edges):
        _fail("calculix_b32_mapping_element_coverage_invalid")
    if mapped_nodes != set(tags):
        _fail("calculix_b32_mapping_node_coverage_invalid")
    return element_lines, diameter


def _calculix_deck(model: dict[str, Any]) -> str:
    material, section = _single_material_section(model)
    nodes = model.get("nodes")
    elements = model.get("elements")
    if not isinstance(nodes, list) or not nodes or not isinstance(elements, list) or not elements:
        _fail("external_model_topology_invalid")
    tags = {str(row.get("id") or ""): index + 1 for index, row in enumerate(nodes)}
    if "" in tags or len(tags) != len(nodes):
        _fail("external_model_node_id_invalid")
    node_lines: list[str] = []
    for row in nodes:
        coordinates = row.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) != 3:
            _fail("external_model_node_coordinates_invalid")
        values = [float(value) for value in coordinates]
        if any(not math.isfinite(value) for value in values):
            _fail("external_model_node_coordinates_invalid")
        node_lines.append(
            f"{tags[str(row['id'])]}, "
            + ", ".join(f"{value:.17g}" for value in values)
        )
    element_lines, diameter = _calculix_b32_mapping(
        model,
        tags=tags,
        elements=elements,
        section=section,
    )
    boundary_lines: list[str] = []
    for support in model.get("supports", []):
        node = tags[str(support["node"])]
        dofs = support["dofs"]
        if dofs == "all":
            boundary_lines.append(f"{node}, 1, 6")
        else:
            boundary_lines.extend(f"{node}, {DOF_INDEX[name]}, {DOF_INDEX[name]}" for name in dofs)
    load_lines: list[str] = []
    for load in model.get("loads", []):
        node = tags[str(load["node"])]
        for dof, value in enumerate(load["components"], start=1):
            numeric = float(value)
            if numeric:
                load_lines.append(f"{node}, {dof}, {numeric:.17g}")
    e = float(material["elastic_modulus"])
    nu = float(material["poisson_ratio"])
    if (
        not math.isfinite(e)
        or e <= 0.0
        or not math.isfinite(nu)
        or not -1.0 < nu < 0.5
    ):
        _fail("calculix_material_properties_invalid")
    return "\n".join(
        [
            "*HEADING",
            "Bounded planar exact three-member portal buckling case",
            "*NODE, NSET=NALL",
            *node_lines,
            "*ELEMENT, TYPE=B32, ELSET=EALL",
            *element_lines,
            "*BEAM SECTION, ELSET=EALL, MATERIAL=MAT, SECTION=CIRC",
            f"{diameter:.17g}, {diameter:.17g}",
            "0.0, 1.0, 0.0",
            "*MATERIAL, NAME=MAT",
            "*ELASTIC",
            f"{e:.17g}, {nu:.17g}",
            "*BOUNDARY",
            *boundary_lines,
            "*STEP",
            "*BUCKLE",
            "2, 1.0E-8, 12, 1000",
            "*CLOAD",
            *load_lines,
            "*NODE FILE, OUTPUT=2D, NSET=NALL",
            "U",
            "*END STEP",
            "",
        ]
    )


def _parse_calculix_factors(dat_text: str) -> list[float]:
    marker = "B U C K L I N G   F A C T O R   O U T P U T"
    if marker not in dat_text:
        _fail("calculix_buckling_table_missing")
    values = [
        float(value)
        for value in re.findall(
            r"^\s*\d+\s+([+-]?\d+\.\d+E[+-]\d+)\s*$",
            dat_text.split(marker, 1)[1],
            flags=re.MULTILINE,
        )[:2]
    ]
    if len(values) != 2 or any(not math.isfinite(value) or value <= 0.0 for value in values):
        _fail("calculix_buckling_factors_invalid")
    return values


def _run_calculix(model: dict[str, Any], binary: Path) -> dict[str, Any]:
    version_run = subprocess.run(
        [str(binary), "-v"], check=False, capture_output=True, text=True
    )
    version_match = re.search(r"Version\s+(\d+\.\d+)", version_run.stdout + version_run.stderr)
    if (
        version_run.returncode not in (0, 201)
        or version_match is None
        or version_match.group(1) != EXPECTED_CALCULIX_VERSION
    ):
        _fail("calculix_runtime_version_invalid")
    with TemporaryDirectory(prefix="bounded-planar-portal-buckling-") as temporary:
        root = Path(temporary)
        (root / "portal.inp").write_text(_calculix_deck(model), encoding="utf-8")
        completed = subprocess.run(
            [str(binary), "portal"], cwd=root, check=False, capture_output=True, text=True
        )
        dat_path = root / "portal.dat"
        if completed.returncode != 0 or not dat_path.is_file():
            _fail("calculix_buckling_execution_failed")
        factors = _parse_calculix_factors(dat_path.read_text(encoding="utf-8"))
    return {
        "solver_version": version_match.group(1),
        "eigenvalues": factors,
        "rigid_mode_count": None,
        "mode_vectors": [],
    }


def execute_case(
    *, case_id: str, model_path: Path, output_path: Path, calculix_binary: Path
) -> dict[str, Any]:
    package_root = Path(__file__).resolve().parents[1]
    _manifest, case = _package_case(
        package_root=package_root, case_id=case_id, model_path=model_path
    )
    model = _load_json(model_path, "external_model_invalid")
    solver = str(case["external_solver"])
    if solver == "OpenSees":
        external = _run_opensees(model, case_id)
    elif solver == "CalculiX":
        external = _run_calculix(model, calculix_binary)
    else:
        _fail("external_solver_invalid")
    observations = {
        "eigenvalues": external["eigenvalues"],
        "rigid_mode_count": external["rigid_mode_count"],
        "mode_vectors": external["mode_vectors"],
    }
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "case_id": case_id,
        "analysis_type": case["analysis_type"],
        "external_solver": solver,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runner_file_sha256": _file_hash(Path(__file__).resolve()),
        "source_model_file_sha256": _file_hash(model_path),
        "runtime": {
            "solver_version": external["solver_version"],
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "observations": observations,
        "contract_pass": True,
        "blockers": [],
        "artifact_hash": ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--calculix-binary", type=Path, default=Path("ccx"))
    args = parser.parse_args()
    try:
        execute_case(
            case_id=args.case_id,
            model_path=args.model,
            output_path=args.out,
            calculix_binary=args.calculix_binary,
        )
    except PackagedExternalCaseError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
