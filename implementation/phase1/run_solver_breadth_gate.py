#!/usr/bin/env python3
"""Aggregate shell/wall/interface/contact-surrogate solver-breadth evidence into one contract report."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from experiment_artifact_archive import archive_test_outputs
from runtime_contracts import InputContractError, validate_input_contract


REASONS = {
    "PASS": "solver breadth evidence is present for shell, wall, interface-boundary, and direct structural-contact workflows",
    "ERR_INVALID_INPUT": "invalid solver breadth gate input",
    "ERR_SHELL_EVIDENCE_FAIL": "shell-beam-mix or diaphragm evidence is missing",
    "ERR_WALL_EVIDENCE_FAIL": "wall material/section evidence is missing",
    "ERR_INTERFACE_BOUNDARY_FAIL": "ssi/interface-boundary evidence is missing",
    "ERR_CONTACT_SURROGATE_FAIL": "interface-compression surrogate evidence is missing",
    "ERR_STRUCTURAL_CONTACT_DIRECT_FAIL": "direct structural-contact link evidence is missing",
    "ERR_GENERAL_FE_CONTACT_MATRIX_FAIL": "general FE contact benchmark matrix evidence is missing",
    "ERR_SURFACE_INTERACTION_BENCHMARK_FAIL": "surface-style FE interaction benchmark evidence is missing",
    "ERR_BENCHMARK_COVERAGE_FAIL": "benchmark topology coverage is missing wall-frame or shell-beam-mix cases",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "topology_report",
        "pushover_stress_report",
        "flexible_diaphragm_report",
        "ssi_boundary_report",
        "substructuring_interface_report",
        "ndtha_stress_report",
        "structural_contact_gate_report",
        "general_fe_contact_benchmark_report",
        "surface_interaction_benchmark_report",
        "benchmark_cases",
        "min_wall_frame_cases",
        "min_shell_beam_mix_cases",
        "out",
    ],
    "properties": {
        "topology_report": {"type": "string", "minLength": 1},
        "pushover_stress_report": {"type": "string", "minLength": 1},
        "flexible_diaphragm_report": {"type": "string", "minLength": 1},
        "ssi_boundary_report": {"type": "string", "minLength": 1},
        "substructuring_interface_report": {"type": "string", "minLength": 1},
        "ndtha_stress_report": {"type": "string", "minLength": 1},
        "structural_contact_gate_report": {"type": "string", "minLength": 1},
        "general_fe_contact_benchmark_report": {"type": "string", "minLength": 1},
        "element_material_breadth_report": {"type": "string", "minLength": 1},
        "surface_interaction_benchmark_report": {"type": "string", "minLength": 1},
        "benchmark_cases": {"type": "string", "minLength": 1},
        "min_wall_frame_cases": {"type": "integer", "minimum": 1},
        "min_shell_beam_mix_cases": {"type": "integer", "minimum": 1},
        "out": {"type": "string", "minLength": 1},
    },
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_csv(text: str) -> list[str]:
    return [item.strip() for item in str(text).split(",") if item.strip()]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _int_or_zero(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _required_family_count(value: object) -> int:
    if isinstance(value, dict):
        return len([key for key in value if str(key).strip()])
    if isinstance(value, (list, tuple, set)):
        return len([item for item in value if str(item).strip()])
    return 0


def _ratio_status_label(ready: int, total: int) -> str:
    if total <= 0:
        return "n/a"
    return f"{int(ready)}/{int(total)}"


def _summary_line_int(summary_line: str, label: str) -> int:
    match = re.search(rf"{re.escape(label)}=(\d+)", summary_line)
    return int(match.group(1)) if match else 0


def _summary_line_ratio(summary_line: str, label: str) -> tuple[int, int]:
    match = re.search(rf"{re.escape(label)}=(\d+)/(\d+)", summary_line)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def _iter_wall_family_rows(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for key in ("rows", "material_effect_rows"):
        block = payload.get(key)
        if not isinstance(block, list):
            continue
        for row in block:
            if not isinstance(row, dict):
                continue
            summary = row.get("summary") if isinstance(row.get("summary"), dict) else row
            family_counts = summary.get("section_family_counts")
            if not isinstance(family_counts, dict):
                continue
            if any(str(name).startswith("wall_") for name in family_counts):
                rows.append(
                    {
                        "case_id": str(row.get("case_id", summary.get("case_id", ""))),
                        "section_family_counts": family_counts,
                    }
                )
    return rows


def _compression_damage_evidence(payload: dict) -> dict:
    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    qualifying_rows: list[dict] = []
    values: list[float] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        material_indices = summary.get("material_indices") if isinstance(summary.get("material_indices"), dict) else {}
        try:
            compression_damage = float(material_indices.get("compression_damage_mean", 0.0) or 0.0)
        except Exception:
            compression_damage = 0.0
        values.append(compression_damage)
        if compression_damage > 0.0:
            qualifying_rows.append(
                {
                    "case_id": str(row.get("case_id", "")),
                    "topology_type": str(row.get("topology_type", "")),
                    "hazard_type": str(row.get("hazard_type", "")),
                    "compression_damage_mean": compression_damage,
                }
            )
    return {
        "row_count": len(rows),
        "qualifying_row_count": len(qualifying_rows),
        "qualifying_rows": qualifying_rows,
        "compression_damage_mean_min": min(values) if values else 0.0,
        "compression_damage_mean_max": max(values) if values else 0.0,
    }


def _aggregate_benchmark_cases(case_paths: list[Path]) -> dict:
    topology_counts: Counter[str] = Counter()
    element_mix_counts: Counter[str] = Counter()
    measured_topology_counts: Counter[str] = Counter()
    measured_element_mix_counts: Counter[str] = Counter()
    source_families: set[str] = set()
    measured_source_families: set[str] = set()
    case_count = 0
    measured_case_count = 0
    rows_by_file: list[dict] = []

    for path in case_paths:
        payload = _load_json(path)
        rows = payload.get("cases")
        if not isinstance(rows, list):
            rows = []
        file_topology_counts: Counter[str] = Counter()
        file_mix_counts: Counter[str] = Counter()
        file_measured_topology_counts: Counter[str] = Counter()
        file_measured_mix_counts: Counter[str] = Counter()
        file_measured_case_count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            case_count += 1
            topology = str(row.get("topology_type", "")).strip()
            mix = str(row.get("element_mix", "")).strip()
            source_family = str(row.get("source_family", "")).strip()
            metric_source = str(row.get("metric_source", "")).strip()
            is_measured = metric_source == "open_data_measurement"
            if topology:
                topology_counts[topology] += 1
                file_topology_counts[topology] += 1
            if mix:
                element_mix_counts[mix] += 1
                file_mix_counts[mix] += 1
            if source_family:
                source_families.add(source_family)
            if is_measured:
                measured_case_count += 1
                file_measured_case_count += 1
                if topology:
                    measured_topology_counts[topology] += 1
                    file_measured_topology_counts[topology] += 1
                if mix:
                    measured_element_mix_counts[mix] += 1
                    file_measured_mix_counts[mix] += 1
                if source_family:
                    measured_source_families.add(source_family)
        rows_by_file.append(
            {
                "cases_path": str(path),
                "cases_sha256": _sha256(path) if path.exists() else "",
                "case_count": len(rows),
                "topology_counts": dict(sorted(file_topology_counts.items())),
                "element_mix_counts": dict(sorted(file_mix_counts.items())),
                "measured_case_count": int(file_measured_case_count),
                "measured_topology_counts": dict(sorted(file_measured_topology_counts.items())),
                "measured_element_mix_counts": dict(sorted(file_measured_mix_counts.items())),
            }
        )

    return {
        "case_count": int(case_count),
        "measured_case_count": int(measured_case_count),
        "source_family_count": len(source_families),
        "measured_source_family_count": len(measured_source_families),
        "topology_counts": dict(sorted(topology_counts.items())),
        "element_mix_counts": dict(sorted(element_mix_counts.items())),
        "measured_topology_counts": dict(sorted(measured_topology_counts.items())),
        "measured_element_mix_counts": dict(sorted(measured_element_mix_counts.items())),
        "rows_by_file": rows_by_file,
    }


def _archive(paths: list[str]) -> str:
    try:
        return str(
            archive_test_outputs(
                test_name="solver_breadth_gate",
                paths=paths,
                run_root="implementation/phase1/experiments/by_test",
                move=False,
            )
        )
    except Exception:
        return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topology-report", default="implementation/phase1/opensees_topology_report.json")
    parser.add_argument("--pushover-stress-report", default="implementation/phase1/nonlinear_pushover_stress_report.json")
    parser.add_argument("--flexible-diaphragm-report", default="implementation/phase1/flexible_diaphragm_gate_report.json")
    parser.add_argument("--ssi-boundary-report", default="implementation/phase1/ssi_boundary_gate_report.json")
    parser.add_argument("--substructuring-interface-report", default="implementation/phase1/substructuring_interface_report.json")
    parser.add_argument("--ndtha-stress-report", default="implementation/phase1/nonlinear_ndtha_stress_report.json")
    parser.add_argument("--structural-contact-gate-report", default="implementation/phase1/structural_contact_gate_report.json")
    parser.add_argument(
        "--general-fe-contact-benchmark-report",
        default="implementation/phase1/general_fe_contact_benchmark_gate_report.json",
    )
    parser.add_argument(
        "--element-material-breadth-report",
        default="implementation/phase1/element_material_breadth_gate_report.json",
    )
    parser.add_argument(
        "--surface-interaction-benchmark-report",
        default="implementation/phase1/surface_interaction_benchmark_gate_report.json",
    )
    parser.add_argument(
        "--benchmark-cases",
        default=(
            "implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,"
            "implementation/phase1/commercial_benchmark_cases.from_csv.json,"
            "implementation/phase1/commercial_benchmark_cases.atwood_open.json"
        ),
    )
    parser.add_argument("--min-wall-frame-cases", type=int, default=1)
    parser.add_argument("--min-shell-beam-mix-cases", type=int, default=1)
    parser.add_argument("--out", default="implementation/phase1/solver_breadth_report.json")
    args = parser.parse_args()

    input_payload = {
        "topology_report": str(args.topology_report),
        "pushover_stress_report": str(args.pushover_stress_report),
        "flexible_diaphragm_report": str(args.flexible_diaphragm_report),
        "ssi_boundary_report": str(args.ssi_boundary_report),
        "substructuring_interface_report": str(args.substructuring_interface_report),
        "ndtha_stress_report": str(args.ndtha_stress_report),
        "structural_contact_gate_report": str(args.structural_contact_gate_report),
        "general_fe_contact_benchmark_report": str(args.general_fe_contact_benchmark_report),
        "element_material_breadth_report": str(args.element_material_breadth_report),
        "surface_interaction_benchmark_report": str(args.surface_interaction_benchmark_report),
        "benchmark_cases": str(args.benchmark_cases),
        "min_wall_frame_cases": int(args.min_wall_frame_cases),
        "min_shell_beam_mix_cases": int(args.min_shell_beam_mix_cases),
        "out": str(args.out),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.run_solver_breadth_gate")
        case_paths = [Path(item) for item in _parse_csv(args.benchmark_cases)]
        if not case_paths:
            raise ValueError("no benchmark case files provided")

        topology = _load_json(Path(args.topology_report))
        pushover = _load_json(Path(args.pushover_stress_report))
        diaphragm = _load_json(Path(args.flexible_diaphragm_report))
        ssi = _load_json(Path(args.ssi_boundary_report))
        substructuring = _load_json(Path(args.substructuring_interface_report))
        ndtha = _load_json(Path(args.ndtha_stress_report))
        structural_contact = _load_json(Path(args.structural_contact_gate_report))
        general_fe_contact_matrix = _load_json(Path(args.general_fe_contact_benchmark_report))
        element_material_breadth = _load_json(Path(args.element_material_breadth_report))
        surface_interaction_benchmark = _load_json(Path(args.surface_interaction_benchmark_report))
        benchmarks = _aggregate_benchmark_cases(case_paths)

        topology_checks = topology.get("checks") if isinstance(topology.get("checks"), dict) else {}
        topology_metrics = topology.get("metrics") if isinstance(topology.get("metrics"), dict) else {}
        diaphragm_checks = diaphragm.get("checks") if isinstance(diaphragm.get("checks"), dict) else {}
        pushover_checks = pushover.get("checks") if isinstance(pushover.get("checks"), dict) else {}
        pushover_summary = pushover.get("summary") if isinstance(pushover.get("summary"), dict) else {}
        ssi_checks = ssi.get("checks") if isinstance(ssi.get("checks"), dict) else {}
        substructuring_checks = substructuring.get("checks") if isinstance(substructuring.get("checks"), dict) else {}
        ndtha_checks = ndtha.get("checks") if isinstance(ndtha.get("checks"), dict) else {}
        ndtha_summary = ndtha.get("summary") if isinstance(ndtha.get("summary"), dict) else {}

        wall_rows = _iter_wall_family_rows(pushover)
        pushover_compression = _compression_damage_evidence(pushover)
        ndtha_compression = _compression_damage_evidence(ndtha)
        wall_family_counter: Counter[str] = Counter()
        for row in wall_rows:
            wall_family_counter.update(
                {
                    str(name): int(count)
                    for name, count in (row.get("section_family_counts") or {}).items()
                    if str(name).startswith("wall_")
                }
            )

        shell_topology_pass = bool(
            topology.get("contract_pass", False)
            and topology_checks.get("shell_beam_mix_pass", False)
            and int(topology_metrics.get("shell_element_count", 0) or 0) >= 1
        )
        shell_diaphragm_pass = bool(
            diaphragm.get("contract_pass", False)
            and diaphragm_checks.get("flexible_diaphragm_modeled", False)
            and diaphragm_checks.get("shell_beam_mix_topology_pass", False)
            and diaphragm_checks.get("slab_shear_stress_pass", False)
        )
        shell_evidence_pass = bool(shell_topology_pass and shell_diaphragm_pass)

        wall_evidence_pass = bool(
            pushover.get("contract_pass", False)
            and pushover_checks.get("material_model_pass", False)
            and pushover_checks.get("section_family_pass", False)
            and len(wall_rows) >= 1
            and sum(wall_family_counter.values()) >= 1
        )

        interface_boundary_pass = bool(
            ssi.get("contract_pass", False)
            and ssi_checks.get("ssi_nonlinear_boundary_active", False)
            and ssi_checks.get("section_family_pass", False)
            and ssi_checks.get("material_model_pass", False)
            and ssi_checks.get("ssi_transfer_finite", False)
        )
        contact_surrogate_pass = bool(
            interface_boundary_pass
            and substructuring.get("contract_pass", False)
            and bool(substructuring_checks.get("finite_transfer", False))
            and bool(substructuring_checks.get("coupling_stability", False))
            and ndtha.get("contract_pass", False)
            and bool(ndtha_checks.get("material_model_pass", False))
            and bool(ndtha_checks.get("section_family_pass", False))
            and int(pushover_compression.get("qualifying_row_count", 0)) >= 1
            and int(ndtha_compression.get("qualifying_row_count", 0)) >= 1
        )
        structural_contact_checks = (
            structural_contact.get("checks")
            if isinstance(structural_contact.get("checks"), dict)
            else {}
        )
        general_fe_contact_checks = (
            general_fe_contact_matrix.get("checks")
            if isinstance(general_fe_contact_matrix.get("checks"), dict)
            else {}
        )
        general_fe_contact_summary = (
            general_fe_contact_matrix.get("summary")
            if isinstance(general_fe_contact_matrix.get("summary"), dict)
            else {}
        )
        general_fe_contact_summary_line = str(general_fe_contact_matrix.get("summary_line", "") or "")
        element_material_checks = (
            element_material_breadth.get("checks")
            if isinstance(element_material_breadth.get("checks"), dict)
            else {}
        )
        element_material_summary = (
            element_material_breadth.get("summary")
            if isinstance(element_material_breadth.get("summary"), dict)
            else {}
        )
        surface_interaction_checks = (
            surface_interaction_benchmark.get("checks")
            if isinstance(surface_interaction_benchmark.get("checks"), dict)
            else {}
        )
        surface_interaction_summary = (
            surface_interaction_benchmark.get("summary")
            if isinstance(surface_interaction_benchmark.get("summary"), dict)
            else {}
        )
        structural_contact_direct_pass = bool(
            structural_contact.get("contract_pass", False)
            and bool(structural_contact_checks.get("all_structural_contact_categories_ready", False))
            and bool(structural_contact_checks.get("structural_contact_event_sequence_zero_pass", False))
        )
        general_fe_contact_matrix_pass = bool(
            general_fe_contact_matrix.get("contract_pass", False)
            and bool(general_fe_contact_checks.get("direct_structural_contact_pass", False))
            and bool(general_fe_contact_checks.get("foundation_soil_link_pass", False))
            and bool(general_fe_contact_checks.get("interface_transfer_pass", False))
            and bool(general_fe_contact_checks.get("ssi_boundary_pass", False))
            and bool(general_fe_contact_checks.get("soil_tunnel_dynamic_pass", False))
            and bool(general_fe_contact_checks.get("all_matrix_rows_ready", False))
        )
        surface_interaction_benchmark_pass = bool(
            surface_interaction_benchmark.get("contract_pass", False)
            and bool(surface_interaction_checks.get("shell_surface_coupling_pass", False))
            and bool(surface_interaction_checks.get("interface_transfer_pass", False))
            and bool(surface_interaction_checks.get("interface_gap_continuity_pass", False))
            and bool(surface_interaction_checks.get("foundation_soil_impedance_pass", False))
            and bool(surface_interaction_checks.get("ssi_boundary_interaction_pass", False))
            and bool(surface_interaction_checks.get("soil_tunnel_dynamic_interaction_pass", False))
            and bool(surface_interaction_checks.get("direct_structural_contact_family_pass", False))
            and bool(surface_interaction_checks.get("interaction_family_matrix_pass", True))
            and bool(surface_interaction_checks.get("all_matrix_rows_ready", False))
        )

        general_fe_support_depth_score = _int_or_zero(general_fe_contact_summary.get("support_depth_score")) or _summary_line_int(
            general_fe_contact_summary_line, "support_depth"
        )
        general_fe_coupling_depth_score = _int_or_zero(general_fe_contact_summary.get("coupling_depth_score")) or _summary_line_int(
            general_fe_contact_summary_line, "coupling_depth"
        )
        general_fe_support_search_count = _int_or_zero(
            general_fe_contact_summary.get("support_search_model_count")
        ) or _summary_line_int(general_fe_contact_summary_line, "support_search")
        general_fe_node_surface_proxy_count = _int_or_zero(
            general_fe_contact_summary.get("node_to_surface_proxy_model_count")
        ) or _summary_line_int(general_fe_contact_summary_line, "node_surface_proxy")
        general_fe_support_family_required_count = _required_family_count(
            general_fe_contact_summary.get("support_search_family_requirements")
        )
        support_family_line_ready_count, support_family_line_total_count = _summary_line_ratio(
            general_fe_contact_summary_line, "support_families"
        )
        proxy_family_line_ready_count, proxy_family_line_total_count = _summary_line_ratio(
            general_fe_contact_summary_line, "proxy_families"
        )
        general_fe_support_family_ready_count = min(
            _int_or_zero(general_fe_contact_summary.get("support_search_family_count")) or support_family_line_ready_count,
            general_fe_support_family_required_count
            or support_family_line_total_count
            or _int_or_zero(general_fe_contact_summary.get("support_search_family_count"))
            or support_family_line_ready_count,
        )
        general_fe_proxy_family_ready_count = min(
            _int_or_zero(general_fe_contact_summary.get("node_to_surface_proxy_family_count")) or proxy_family_line_ready_count,
            general_fe_support_family_required_count
            or proxy_family_line_total_count
            or _int_or_zero(general_fe_contact_summary.get("node_to_surface_proxy_family_count"))
            or proxy_family_line_ready_count,
        )
        general_fe_proxy_family_required_count = (
            general_fe_support_family_required_count
            or proxy_family_line_total_count
            or _int_or_zero(general_fe_contact_summary.get("node_to_surface_proxy_family_count"))
        )
        element_material_coupling_available = bool(
            element_material_breadth
            and (
                bool(element_material_checks.get("beam_shell_contact_coupling_surface_present", False))
                or _int_or_zero(element_material_summary.get("beam_shell_contact_coupling_signal_count")) > 0
            )
        )
        contact_coupling_depth_score = max(
            general_fe_coupling_depth_score,
            _int_or_zero(element_material_summary.get("beam_shell_contact_coupling_signal_count")),
        )
        contact_support_depth_score = max(
            general_fe_support_depth_score,
            _int_or_zero(element_material_summary.get("beam_shell_contact_support_depth_score")),
        )
        contact_support_search_count = max(
            general_fe_support_search_count,
            _int_or_zero(element_material_summary.get("beam_shell_contact_support_search_count")),
        )
        contact_node_surface_proxy_count = max(
            general_fe_node_surface_proxy_count,
            _int_or_zero(element_material_summary.get("beam_shell_contact_node_surface_proxy_count")),
        )
        contact_support_family_ready_count = max(
            general_fe_support_family_ready_count,
            _int_or_zero(element_material_summary.get("beam_shell_contact_support_family_count")),
        )
        contact_support_family_total_count = max(
            general_fe_support_family_required_count,
            _int_or_zero(element_material_summary.get("beam_shell_contact_support_family_count")),
        )
        contact_proxy_family_ready_count = max(
            general_fe_proxy_family_ready_count,
            _int_or_zero(element_material_summary.get("beam_shell_contact_proxy_family_count")),
        )
        contact_proxy_family_total_count = max(
            general_fe_proxy_family_required_count,
            _int_or_zero(element_material_summary.get("beam_shell_contact_proxy_family_count")),
        )
        contact_family_readiness_pass = bool(
            general_fe_contact_checks.get("support_search_family_surface_pass", False)
            and general_fe_contact_checks.get("node_to_surface_proxy_family_surface_pass", False)
        )
        contact_coupling_surface_pass = bool(
            general_fe_contact_matrix_pass
            and (
                not element_material_breadth
                or element_material_coupling_available
            )
        )

        wall_frame_case_count = int((benchmarks.get("topology_counts") or {}).get("wall-frame", 0) or 0)
        shell_beam_mix_case_count = int((benchmarks.get("element_mix_counts") or {}).get("shell_beam_mix", 0) or 0)
        measured_wall_frame_case_count = int((benchmarks.get("measured_topology_counts") or {}).get("wall-frame", 0) or 0)
        measured_shell_beam_mix_case_count = int(
            (benchmarks.get("measured_element_mix_counts") or {}).get("shell_beam_mix", 0) or 0
        )
        benchmark_coverage_pass = bool(
            wall_frame_case_count >= int(args.min_wall_frame_cases)
            and shell_beam_mix_case_count >= int(args.min_shell_beam_mix_cases)
        )

        contact_surface_status = (
            "full_structural_contact"
            if structural_contact_direct_pass
            else "interface_compression_surrogate"
            if contact_surrogate_pass
            else "tracked_gap"
        )
        contact_surface_declared = True

        checks = {
            "shell_topology_pass": bool(shell_topology_pass),
            "shell_diaphragm_pass": bool(shell_diaphragm_pass),
            "shell_evidence_pass": bool(shell_evidence_pass),
            "wall_evidence_pass": bool(wall_evidence_pass),
            "interface_boundary_pass": bool(interface_boundary_pass),
            "contact_surrogate_pass": bool(contact_surrogate_pass),
            "structural_contact_direct_pass": bool(structural_contact_direct_pass),
            "general_fe_contact_matrix_pass": bool(general_fe_contact_matrix_pass),
            "surface_interaction_benchmark_pass": bool(surface_interaction_benchmark_pass),
            "benchmark_coverage_pass": bool(benchmark_coverage_pass),
            "contact_surface_declared": bool(contact_surface_declared),
        }

        contract_pass = bool(
            checks["shell_evidence_pass"]
            and checks["wall_evidence_pass"]
            and checks["interface_boundary_pass"]
            and checks["contact_surrogate_pass"]
            and checks["structural_contact_direct_pass"]
            and checks["general_fe_contact_matrix_pass"]
            and checks["surface_interaction_benchmark_pass"]
            and checks["benchmark_coverage_pass"]
            and checks["contact_surface_declared"]
        )

        if not checks["shell_evidence_pass"]:
            reason_code = "ERR_SHELL_EVIDENCE_FAIL"
        elif not checks["wall_evidence_pass"]:
            reason_code = "ERR_WALL_EVIDENCE_FAIL"
        elif not checks["interface_boundary_pass"]:
            reason_code = "ERR_INTERFACE_BOUNDARY_FAIL"
        elif not checks["contact_surrogate_pass"]:
            reason_code = "ERR_CONTACT_SURROGATE_FAIL"
        elif not checks["structural_contact_direct_pass"]:
            reason_code = "ERR_STRUCTURAL_CONTACT_DIRECT_FAIL"
        elif not checks["general_fe_contact_matrix_pass"]:
            reason_code = "ERR_GENERAL_FE_CONTACT_MATRIX_FAIL"
        elif not checks["surface_interaction_benchmark_pass"]:
            reason_code = "ERR_SURFACE_INTERACTION_BENCHMARK_FAIL"
        elif not checks["benchmark_coverage_pass"]:
            reason_code = "ERR_BENCHMARK_COVERAGE_FAIL"
        else:
            reason_code = "PASS"

        summary = {
            "shell_element_count": int(topology_metrics.get("shell_element_count", 0) or 0),
            "shell_beam_mix_case_count": shell_beam_mix_case_count,
            "wall_frame_case_count": wall_frame_case_count,
            "measured_shell_beam_mix_case_count": measured_shell_beam_mix_case_count,
            "measured_wall_frame_case_count": measured_wall_frame_case_count,
            "benchmark_case_count": int(benchmarks.get("case_count", 0) or 0),
            "measured_case_count": int(benchmarks.get("measured_case_count", 0) or 0),
            "source_family_count": int(benchmarks.get("source_family_count", 0) or 0),
            "measured_source_family_count": int(benchmarks.get("measured_source_family_count", 0) or 0),
            "wall_row_count": len(wall_rows),
            "wall_family_counts": dict(sorted(wall_family_counter.items())),
            "wall_material_model": str(pushover_summary.get("material_model", "")),
            "contact_surrogate_scope": "ssi_interface_plus_unilateral_compression_surrogate",
            "contact_surface_status": contact_surface_status,
            "structural_contact_direct_contract_pass": bool(structural_contact_direct_pass),
            "general_fe_contact_matrix_contract_pass": bool(general_fe_contact_matrix_pass),
            "general_fe_contact_ready_row_count": int(general_fe_contact_summary.get("ready_row_count", 0) or 0),
            "general_fe_contact_total_row_count": int(general_fe_contact_summary.get("total_row_count", 0) or 0),
            "general_fe_contact_support_depth_score": int(general_fe_support_depth_score),
            "general_fe_contact_coupling_depth_score": int(general_fe_coupling_depth_score),
            "general_fe_contact_support_search_count": int(general_fe_support_search_count),
            "general_fe_contact_node_surface_proxy_count": int(general_fe_node_surface_proxy_count),
            "general_fe_contact_support_family_ready_count": int(general_fe_support_family_ready_count),
            "general_fe_contact_support_family_total_count": int(general_fe_support_family_required_count),
            "general_fe_contact_proxy_family_ready_count": int(general_fe_proxy_family_ready_count),
            "general_fe_contact_proxy_family_total_count": int(general_fe_proxy_family_required_count),
            "contact_coupling_surface_status": "pass" if contact_coupling_surface_pass else "check",
            "contact_coupling_depth_score": int(contact_coupling_depth_score),
            "contact_support_depth_score": int(contact_support_depth_score),
            "contact_support_search_count": int(contact_support_search_count),
            "contact_node_surface_proxy_count": int(contact_node_surface_proxy_count),
            "contact_support_family_ready_count": int(contact_support_family_ready_count),
            "contact_support_family_total_count": int(contact_support_family_total_count),
            "contact_proxy_family_ready_count": int(contact_proxy_family_ready_count),
            "contact_proxy_family_total_count": int(contact_proxy_family_total_count),
            "contact_family_readiness_status": "pass" if contact_family_readiness_pass else "check",
            "contact_coupling_source_label": (
                "general_fe+element_material"
                if general_fe_contact_matrix_pass and element_material_coupling_available
                else "general_fe"
                if general_fe_contact_matrix_pass
                else "partial"
            ),
            "contact_coupling_summary_label": (
                f"depth={int(contact_coupling_depth_score)},support={int(contact_support_depth_score)},"
                f"search={int(contact_support_search_count)},proxy={int(contact_node_surface_proxy_count)}"
            ),
            "contact_family_readiness_label": (
                f"support={_ratio_status_label(contact_support_family_ready_count, contact_support_family_total_count)},"
                f"proxy={_ratio_status_label(contact_proxy_family_ready_count, contact_proxy_family_total_count)}"
            ),
            "element_material_contact_coupling_present": bool(
                element_material_checks.get("beam_shell_contact_coupling_surface_present", False)
            ),
            "element_material_contact_coupling_signal_count": _int_or_zero(
                element_material_summary.get("beam_shell_contact_coupling_signal_count")
            ),
            "element_material_contact_support_depth_score": _int_or_zero(
                element_material_summary.get("beam_shell_contact_support_depth_score")
            ),
            "element_material_contact_support_search_count": _int_or_zero(
                element_material_summary.get("beam_shell_contact_support_search_count")
            ),
            "element_material_contact_node_surface_proxy_count": _int_or_zero(
                element_material_summary.get("beam_shell_contact_node_surface_proxy_count")
            ),
            "element_material_contact_support_family_count": _int_or_zero(
                element_material_summary.get("beam_shell_contact_support_family_count")
            ),
            "element_material_contact_proxy_family_count": _int_or_zero(
                element_material_summary.get("beam_shell_contact_proxy_family_count")
            ),
            "surface_interaction_benchmark_contract_pass": bool(surface_interaction_benchmark_pass),
            "surface_interaction_ready_row_count": int(surface_interaction_summary.get("ready_row_count", 0) or 0),
            "surface_interaction_total_row_count": int(surface_interaction_summary.get("total_row_count", 0) or 0),
            "surface_interaction_family_ready_count": int(surface_interaction_summary.get("interaction_family_ready_count", 0) or 0),
            "surface_interaction_family_total_count": int(surface_interaction_summary.get("interaction_family_total_count", 0) or 0),
            "surface_interaction_source_family_ready_count": int(surface_interaction_summary.get("interaction_source_family_ready_count", 0) or 0),
            "surface_interaction_source_family_total_count": int(surface_interaction_summary.get("interaction_source_family_total_count", 0) or 0),
            "surface_interaction_group_label": str(surface_interaction_summary.get("interaction_family_group_label", "") or ""),
            "substructuring_contract_pass": bool(substructuring.get("contract_pass", False)),
            "substructuring_transfer_ratio": float(
                (substructuring.get("metrics") or {}).get("mean_transfer_ratio_building_to_track", 0.0)
            )
            if isinstance(substructuring.get("metrics"), dict)
            else 0.0,
            "pushover_compression_damage_row_count": int(pushover_compression.get("qualifying_row_count", 0)),
            "ndtha_compression_damage_row_count": int(ndtha_compression.get("qualifying_row_count", 0)),
            "ndtha_material_model": str(ndtha_summary.get("material_model", "")),
        }
        summary_line = (
            f"Solver breadth: {'PASS' if contract_pass else 'CHECK'} | "
            f"shell={'yes' if shell_evidence_pass else 'no'}(elems={summary['shell_element_count']},cases={shell_beam_mix_case_count}) | "
            f"wall={'yes' if wall_evidence_pass else 'no'}(rows={len(wall_rows)},cases={wall_frame_case_count},material={summary['wall_material_model'] or 'n/a'}) | "
            f"interface={'yes' if interface_boundary_pass else 'no'}(ssi_nonlinear_boundary) | "
            f"contact={contact_surface_status} | "
            f"general_fe_contact={'yes' if general_fe_contact_matrix_pass else 'no'}"
            f"({summary['general_fe_contact_ready_row_count']}/{summary['general_fe_contact_total_row_count']}) | "
            f"contact_coupling={'yes' if contact_coupling_surface_pass else 'no'}"
            f"(depth={summary['contact_coupling_depth_score']},support={summary['contact_support_depth_score']},"
            f"search={summary['contact_support_search_count']},proxy={summary['contact_node_surface_proxy_count']}) | "
            f"contact_families={'yes' if contact_family_readiness_pass else 'no'}"
            f"(support={summary['contact_support_family_ready_count']}/{summary['contact_support_family_total_count']},"
            f"proxy={summary['contact_proxy_family_ready_count']}/{summary['contact_proxy_family_total_count']}) | "
            f"surface_interaction={'yes' if surface_interaction_benchmark_pass else 'no'}"
            f"({summary['surface_interaction_ready_row_count']}/{summary['surface_interaction_total_row_count']}) | "
            f"interaction_family="
            f"{'yes' if summary['surface_interaction_family_total_count'] and summary['surface_interaction_family_ready_count'] == summary['surface_interaction_family_total_count'] else 'no'}"
            f"({summary['surface_interaction_family_ready_count']}/{summary['surface_interaction_family_total_count']}) | "
            f"interaction_sources={summary['surface_interaction_source_family_ready_count']}/{summary['surface_interaction_source_family_total_count']}"
            f"{' | groups=' + summary['surface_interaction_group_label'] if summary['surface_interaction_group_label'] else ''}"
        )

        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-solver-breadth-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "checks": checks,
            "summary": summary,
            "benchmark_cases": benchmarks,
            "summary_line": summary_line,
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        archive_manifest = _archive(
            [
                str(out),
                str(args.topology_report),
                str(args.pushover_stress_report),
                str(args.flexible_diaphragm_report),
                str(args.ssi_boundary_report),
                str(args.substructuring_interface_report),
                str(args.ndtha_stress_report),
                str(args.structural_contact_gate_report),
                str(args.general_fe_contact_benchmark_report),
                str(args.element_material_breadth_report),
                str(args.surface_interaction_benchmark_report),
                *[str(path) for path in case_paths],
            ]
        )
        if archive_manifest:
            payload["artifact_archive_manifest"] = archive_manifest
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(summary_line)
        print(f"Wrote solver breadth gate report: {out}")
        if not contract_pass:
            raise SystemExit(1)

    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-solver-breadth-gate",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(payload["reason"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
