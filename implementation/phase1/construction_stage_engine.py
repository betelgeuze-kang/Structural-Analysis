#!/usr/bin/env python3
"""Deterministic staged construction engine with activation/deactivation history."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
except ImportError:  # pragma: no cover - script execution fallback
    from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract


DEFAULT_OUT = "implementation/phase1/construction_stage_engine_report.json"

REASONS = {
    "PASS": "construction stage engine validation and staged demand replay passed",
    "ERR_INVALID_INPUT": "invalid construction stage engine input",
    "ERR_SEQUENCE": "construction stage sequence violated activation or history invariants",
    "ERR_DEMAND_LIMIT": "construction stage cumulative demand exceeded the utilization limit",
    "ERR_EMPTY_DEMAND": "construction stage replay produced no cumulative demand",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["elements", "loads", "stages"],
    "properties": {
        "elements": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "kind", "stiffness", "capacity"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "minLength": 1},
                    "stiffness": {"type": "number", "exclusiveMinimum": 0.0},
                    "capacity": {"type": "number", "exclusiveMinimum": 0.0},
                    "self_weight": {"type": "number", "minimum": 0.0},
                    "demand_factor": {"type": "number", "exclusiveMinimum": 0.0},
                },
            },
        },
        "loads": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "target", "magnitude"],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "target": {"type": "string", "minLength": 1},
                    "magnitude": {"type": "number", "exclusiveMinimum": 0.0},
                    "category": {"type": "string", "minLength": 1},
                    "demand_factor": {"type": "number", "exclusiveMinimum": 0.0},
                },
            },
        },
        "stages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "duration_days": {"type": "number", "minimum": 0.0},
                    "load_scale": {"type": "number", "minimum": 0.0},
                    "activate_elements": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "deactivate_elements": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "activate_loads": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "deactivate_loads": {"type": "array", "items": {"type": "string", "minLength": 1}},
                    "note": {"type": "string"},
                },
            },
        },
        "max_utilization_ratio": {"type": "number", "exclusiveMinimum": 0.0},
        "out": {"type": "string", "minLength": 1},
    },
}

_ELEMENT_KIND_FACTORS = {
    "foundation": 0.90,
    "core": 0.95,
    "column": 1.00,
    "wall": 1.00,
    "beam": 1.10,
    "slab": 1.15,
    "brace": 0.88,
    "truss": 0.92,
}

_LOAD_CATEGORY_FACTORS = {
    "dead": 1.00,
    "self_weight": 1.00,
    "construction": 1.05,
    "temporary": 0.92,
    "live": 1.10,
    "equipment": 1.08,
}


@dataclass(frozen=True)
class ConstructionElement:
    id: str
    kind: str
    stiffness: float
    capacity: float
    self_weight: float = 0.0
    demand_factor: float = 1.0


@dataclass(frozen=True)
class ConstructionLoad:
    id: str
    target: str
    magnitude: float
    category: str = "dead"
    demand_factor: float = 1.0


@dataclass(frozen=True)
class StageDefinition:
    name: str
    duration_days: float = 0.0
    load_scale: float = 1.0
    activate_elements: tuple[str, ...] = ()
    deactivate_elements: tuple[str, ...] = ()
    activate_loads: tuple[str, ...] = ()
    deactivate_loads: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class ConstructionStageModel:
    elements: tuple[ConstructionElement, ...]
    loads: tuple[ConstructionLoad, ...]
    stages: tuple[StageDefinition, ...]
    max_utilization_ratio: float = 1.0


def _ordered_unique_text(values: Any) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values if isinstance(values, list) else []:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _duplicates(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    dup: list[str] = []
    for item in ids:
        if item in seen and item not in dup:
            dup.append(item)
            continue
        seen.add(item)
    return dup


def _element_kind_factor(kind: str) -> float:
    return float(_ELEMENT_KIND_FACTORS.get(str(kind).strip().lower(), 1.0))


def _load_category_factor(category: str) -> float:
    return float(_LOAD_CATEGORY_FACTORS.get(str(category).strip().lower(), 1.0))


def _duration_factor(duration_days: float) -> float:
    return 1.0 + max(float(duration_days), 0.0) / 30.0


def _ordered_ids(order: tuple[str, ...], active_ids: set[str]) -> list[str]:
    return [item for item in order if item in active_ids]


def _format_float_dict(order: tuple[str, ...], values: dict[str, float]) -> dict[str, float]:
    return {item: float(values.get(item, 0.0)) for item in order}


def _build_model(payload: dict[str, Any]) -> ConstructionStageModel:
    elements_raw = [row for row in payload.get("elements", []) if isinstance(row, dict)]
    loads_raw = [row for row in payload.get("loads", []) if isinstance(row, dict)]
    stages_raw = [row for row in payload.get("stages", []) if isinstance(row, dict)]

    element_ids = [str(row.get("id", "")).strip() for row in elements_raw]
    load_ids = [str(row.get("id", "")).strip() for row in loads_raw]
    stage_names = [str(row.get("name", "")).strip() for row in stages_raw]

    dup_elements = _duplicates(element_ids)
    dup_loads = _duplicates(load_ids)
    dup_stages = _duplicates(stage_names)
    if dup_elements or dup_loads or dup_stages:
        parts: list[str] = []
        if dup_elements:
            parts.append(f"duplicate element ids: {', '.join(dup_elements)}")
        if dup_loads:
            parts.append(f"duplicate load ids: {', '.join(dup_loads)}")
        if dup_stages:
            parts.append(f"duplicate stage names: {', '.join(dup_stages)}")
        raise ValueError("; ".join(parts))

    elements = tuple(
        ConstructionElement(
            id=str(row["id"]).strip(),
            kind=str(row["kind"]).strip(),
            stiffness=float(row["stiffness"]),
            capacity=float(row["capacity"]),
            self_weight=float(row.get("self_weight", 0.0) or 0.0),
            demand_factor=float(row.get("demand_factor", 1.0) or 1.0),
        )
        for row in elements_raw
    )
    loads = tuple(
        ConstructionLoad(
            id=str(row["id"]).strip(),
            target=str(row["target"]).strip(),
            magnitude=float(row["magnitude"]),
            category=str(row.get("category", "dead") or "dead").strip(),
            demand_factor=float(row.get("demand_factor", 1.0) or 1.0),
        )
        for row in loads_raw
    )
    stages = tuple(
        StageDefinition(
            name=str(row["name"]).strip(),
            duration_days=float(row.get("duration_days", 0.0) or 0.0),
            load_scale=float(row.get("load_scale", 1.0) if "load_scale" in row else 1.0),
            activate_elements=_ordered_unique_text(row.get("activate_elements", [])),
            deactivate_elements=_ordered_unique_text(row.get("deactivate_elements", [])),
            activate_loads=_ordered_unique_text(row.get("activate_loads", [])),
            deactivate_loads=_ordered_unique_text(row.get("deactivate_loads", [])),
            note=str(row.get("note", "") or ""),
        )
        for row in stages_raw
    )
    return ConstructionStageModel(
        elements=elements,
        loads=loads,
        stages=stages,
        max_utilization_ratio=float(payload.get("max_utilization_ratio", 1.0) or 1.0),
    )


def _validate_model_domain(model: ConstructionStageModel) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    element_ids = {element.id for element in model.elements}
    loads_by_id = {load.id: load for load in model.loads}

    for load in model.loads:
        if load.target not in element_ids:
            errors.append(f"load '{load.id}' targets unknown element '{load.target}'")

    active_elements: set[str] = set()
    active_loads: set[str] = set()
    for stage_index, stage in enumerate(model.stages, start=1):
        stage_label = f"stage {stage_index} '{stage.name}'"
        for field_name, ids, known_ids in (
            ("activate_elements", stage.activate_elements, element_ids),
            ("deactivate_elements", stage.deactivate_elements, element_ids),
            ("activate_loads", stage.activate_loads, set(loads_by_id)),
            ("deactivate_loads", stage.deactivate_loads, set(loads_by_id)),
        ):
            unknown = [item for item in ids if item not in known_ids]
            if unknown:
                errors.append(f"{stage_label} references unknown ids in {field_name}: {', '.join(unknown)}")

        overlap_elements = sorted(set(stage.activate_elements) & set(stage.deactivate_elements))
        overlap_loads = sorted(set(stage.activate_loads) & set(stage.deactivate_loads))
        if overlap_elements:
            errors.append(f"{stage_label} both activates and deactivates elements: {', '.join(overlap_elements)}")
        if overlap_loads:
            errors.append(f"{stage_label} both activates and deactivates loads: {', '.join(overlap_loads)}")

        next_active_elements = set(active_elements)
        next_active_loads = set(active_loads)
        next_active_elements.difference_update(stage.deactivate_elements)
        next_active_elements.update(stage.activate_elements)
        next_active_loads.difference_update(stage.deactivate_loads)
        next_active_loads.update(stage.activate_loads)

        invalid_load_activations = [
            load_id
            for load_id in stage.activate_loads
            if load_id in loads_by_id and loads_by_id[load_id].target not in next_active_elements
        ]
        if invalid_load_activations:
            errors.append(
                f"{stage_label} activates loads before their target elements are active: "
                f"{', '.join(invalid_load_activations)}"
            )

        auto_drop = sorted(
            load_id
            for load_id in next_active_loads
            if load_id in loads_by_id and loads_by_id[load_id].target not in next_active_elements
        )
        if auto_drop:
            warnings.append(
                f"{stage_label} auto-deactivates loads {', '.join(auto_drop)} because their target elements are inactive"
            )
            next_active_loads.difference_update(auto_drop)

        if (
            not stage.activate_elements
            and not stage.deactivate_elements
            and not stage.activate_loads
            and not stage.deactivate_loads
            and stage.duration_days <= 0.0
        ):
            warnings.append(f"{stage_label} has no state change and zero duration")

        active_elements = next_active_elements
        active_loads = next_active_loads

    return errors, warnings


def validate_construction_stage_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        validate_input_contract(payload, INPUT_SCHEMA, label="construction_stage_engine")
        model = _build_model(payload)
        errors, warnings = _validate_model_domain(model)
    except (InputContractError, ValueError) as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": []}

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "element_count": len(model.elements),
        "load_count": len(model.loads),
        "stage_count": len(model.stages),
    }


def generate_construction_stage_report(payload: dict[str, Any]) -> dict[str, Any]:
    validate_input_contract(payload, INPUT_SCHEMA, label="construction_stage_engine")
    model = _build_model(payload)
    validation_errors, validation_warnings = _validate_model_domain(model)
    if validation_errors:
        raise ValueError("; ".join(validation_errors))

    elements_by_id = {element.id: element for element in model.elements}
    loads_by_id = {load.id: load for load in model.loads}
    element_order = tuple(element.id for element in model.elements)
    load_order = tuple(load.id for load in model.loads)

    active_elements: set[str] = set()
    active_loads: set[str] = set()
    cumulative_demand = {element.id: 0.0 for element in model.elements}
    history_snapshots: list[dict[str, Any]] = []
    runtime_warnings = list(validation_warnings)
    cumulative_duration_days = 0.0
    auto_deactivated_load_count_total = 0

    for stage_index, stage in enumerate(model.stages, start=1):
        active_elements.difference_update(stage.deactivate_elements)
        active_loads.difference_update(stage.deactivate_loads)
        active_elements.update(stage.activate_elements)
        active_loads.update(stage.activate_loads)

        auto_deactivated_loads = sorted(
            load_id for load_id in active_loads if loads_by_id[load_id].target not in active_elements
        )
        if auto_deactivated_loads:
            active_loads.difference_update(auto_deactivated_loads)
            auto_deactivated_load_count_total += len(auto_deactivated_loads)
            msg = (
                f"stage {stage_index} '{stage.name}' auto-deactivates loads "
                f"{', '.join(auto_deactivated_loads)} because their target elements are inactive"
            )
            if msg not in runtime_warnings:
                runtime_warnings.append(msg)

        cumulative_duration_days += float(stage.duration_days)
        duration_factor = _duration_factor(stage.duration_days)
        stage_base_demand = {element_id: 0.0 for element_id in element_order}
        stage_load_demand = {element_id: 0.0 for element_id in element_order}
        stage_total_demand = {element_id: 0.0 for element_id in element_order}

        for element_id in element_order:
            if element_id not in active_elements:
                continue
            element = elements_by_id[element_id]
            element_factor = _element_kind_factor(element.kind) * float(element.demand_factor)
            base_demand = duration_factor * element_factor * float(element.self_weight) / float(element.stiffness)
            load_effect = sum(
                float(loads_by_id[load_id].magnitude)
                * float(loads_by_id[load_id].demand_factor)
                * _load_category_factor(loads_by_id[load_id].category)
                for load_id in active_loads
                if loads_by_id[load_id].target == element_id
            )
            load_demand = duration_factor * element_factor * load_effect * float(stage.load_scale) / float(element.stiffness)
            total_demand = base_demand + load_demand
            stage_base_demand[element_id] = float(base_demand)
            stage_load_demand[element_id] = float(load_demand)
            stage_total_demand[element_id] = float(total_demand)
            cumulative_demand[element_id] += float(total_demand)

        utilization_by_element = {
            element.id: float(cumulative_demand[element.id] / element.capacity) for element in model.elements
        }
        snapshot = {
            "stage_index": int(stage_index),
            "stage_name": stage.name,
            "duration_days": float(stage.duration_days),
            "cumulative_duration_days": float(cumulative_duration_days),
            "load_scale": float(stage.load_scale),
            "note": stage.note,
            "operations": {
                "activate_elements": list(stage.activate_elements),
                "deactivate_elements": list(stage.deactivate_elements),
                "activate_loads": list(stage.activate_loads),
                "deactivate_loads": list(stage.deactivate_loads),
                "auto_deactivated_loads": auto_deactivated_loads,
            },
            "active_element_ids": _ordered_ids(element_order, active_elements),
            "active_load_ids": _ordered_ids(load_order, active_loads),
            "element_stage_base_demand": _format_float_dict(element_order, stage_base_demand),
            "element_stage_load_demand": _format_float_dict(element_order, stage_load_demand),
            "element_stage_total_demand": _format_float_dict(element_order, stage_total_demand),
            "cumulative_demand_by_element": _format_float_dict(element_order, cumulative_demand),
            "utilization_by_element": _format_float_dict(element_order, utilization_by_element),
            "stage_total_demand": float(sum(stage_total_demand.values())),
            "cumulative_total_demand": float(sum(cumulative_demand.values())),
            "max_utilization_ratio": float(max(utilization_by_element.values(), default=0.0)),
        }
        history_snapshots.append(snapshot)

    cumulative_series = [float(snapshot["cumulative_total_demand"]) for snapshot in history_snapshots]
    cumulative_monotonic_pass = all(
        later >= earlier - 1.0e-12 for earlier, later in zip(cumulative_series, cumulative_series[1:])
    )
    active_target_integrity_pass = all(
        loads_by_id[load_id].target in set(snapshot["active_element_ids"])
        for snapshot in history_snapshots
        for load_id in snapshot["active_load_ids"]
    )
    final_snapshot = history_snapshots[-1] if history_snapshots else {}
    final_cumulative_total = float(final_snapshot.get("cumulative_total_demand", 0.0))
    max_utilization = float(max((snapshot["max_utilization_ratio"] for snapshot in history_snapshots), default=0.0))
    critical_element_id = ""
    if model.elements:
        critical_element_id = max(
            model.elements,
            key=lambda element: float(cumulative_demand[element.id] / element.capacity),
        ).id

    checks = {
        "validation_pass": True,
        "history_snapshot_count_pass": len(history_snapshots) == len(model.stages),
        "cumulative_total_monotonic_pass": bool(cumulative_monotonic_pass),
        "active_target_integrity_pass": bool(active_target_integrity_pass),
        "utilization_limit_pass": bool(max_utilization <= model.max_utilization_ratio),
        "demand_present_pass": bool(final_cumulative_total > 0.0),
    }
    contract_pass = bool(all(checks.values()))
    if not checks["history_snapshot_count_pass"] or not checks["cumulative_total_monotonic_pass"] or not checks["active_target_integrity_pass"]:
        reason_code = "ERR_SEQUENCE"
    elif not checks["demand_present_pass"]:
        reason_code = "ERR_EMPTY_DEMAND"
    elif not checks["utilization_limit_pass"]:
        reason_code = "ERR_DEMAND_LIMIT"
    else:
        reason_code = "PASS"

    report = {
        "schema_version": "1.0",
        "run_id": "phase1-construction-stage-engine",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": payload,
        "checks": checks,
        "summary": {
            "element_count": int(len(model.elements)),
            "load_count": int(len(model.loads)),
            "stage_count": int(len(model.stages)),
            "history_snapshot_count": int(len(history_snapshots)),
            "cumulative_duration_days": float(cumulative_duration_days),
            "final_active_element_count": int(len(final_snapshot.get("active_element_ids", []))),
            "final_active_load_count": int(len(final_snapshot.get("active_load_ids", []))),
            "final_cumulative_total_demand": float(final_cumulative_total),
            "max_stage_total_demand": float(max((snapshot["stage_total_demand"] for snapshot in history_snapshots), default=0.0)),
            "max_utilization_ratio": float(max_utilization),
            "critical_element_id": critical_element_id,
            "auto_deactivated_load_count_total": int(auto_deactivated_load_count_total),
            "validation_warning_count": int(len(runtime_warnings)),
        },
        "summary_line": (
            f"Construction stage engine: {'PASS' if contract_pass else 'CHECK'} | "
            f"stages={len(model.stages)} | "
            f"final_active={len(final_snapshot.get('active_element_ids', []))} elements/"
            f"{len(final_snapshot.get('active_load_ids', []))} loads | "
            f"cumulative_total={final_cumulative_total:.4f} | "
            f"max_utilization={max_utilization:.4f}/{model.max_utilization_ratio:.4f} | "
            f"auto_drop={auto_deactivated_load_count_total}"
        ),
        "reasons": [
            (
                f"sequence={'pass' if checks['active_target_integrity_pass'] else 'check'} via "
                f"snapshots={len(history_snapshots)}, monotonic={checks['cumulative_total_monotonic_pass']}, "
                f"final_active_elements={len(final_snapshot.get('active_element_ids', []))}."
            ),
            (
                f"demand={'pass' if checks['demand_present_pass'] else 'check'} via "
                f"final_cumulative_total={final_cumulative_total:.4f}, "
                f"max_stage_total={float(max((snapshot['stage_total_demand'] for snapshot in history_snapshots), default=0.0)):.4f}."
            ),
            (
                f"utilization={'pass' if checks['utilization_limit_pass'] else 'check'} via "
                f"critical_element={critical_element_id or 'n/a'}, "
                f"max_utilization={max_utilization:.4f}/{model.max_utilization_ratio:.4f}."
            ),
        ],
        "validation": {
            "valid": True,
            "errors": [],
            "warnings": runtime_warnings,
        },
        "elements": [asdict(element) for element in model.elements],
        "loads": [asdict(load) for load in model.loads],
        "stages": [asdict(stage) for stage in model.stages],
        "history_snapshots": history_snapshots,
        "final_snapshot": final_snapshot,
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }
    return report


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    logger = get_logger("phase1.construction_stage_engine")
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    input_metadata = {"input": str(args.input), "out": str(args.out)}

    try:
        payload = _load_json(Path(args.input))
        if not isinstance(payload, dict):
            raise ValueError("input JSON must be an object")
        payload = dict(payload)
        payload["out"] = str(args.out)
        report = generate_construction_stage_report(payload)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(
            logger,
            logging.INFO,
            "construction_stage_engine.completed",
            contract_pass=bool(report["contract_pass"]),
            stage_count=int(report["summary"]["stage_count"]),
            max_utilization_ratio=float(report["summary"]["max_utilization_ratio"]),
        )
        print(f"Wrote construction stage engine report: {out}")
        if not bool(report["contract_pass"]):
            raise SystemExit(1)
    except (FileNotFoundError, ValueError, InputContractError, json.JSONDecodeError) as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-construction-stage-engine",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_metadata,
            "validation": {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
            },
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        log_event(logger, logging.ERROR, "construction_stage_engine.invalid_input", error=str(exc))
        print(f"Wrote construction stage engine report: {out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
