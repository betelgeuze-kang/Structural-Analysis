#!/usr/bin/env python3
"""Run one pinned OpenSees nonlinear/material/recovery reference case.

This file is copied byte-for-byte into the external execution package.  It is
therefore intentionally standalone and imports no product implementation.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import openseespy.opensees as ops


SCHEMA_VERSION = "bounded-planar-opensees-nonlinear-material-recovery-result.v1"
PACKAGE_ID = "bounded-planar-nonlinear-material-recovery-v1"
PINNED_OPENSEESPY_VERSION = "3.7.1.2"
PINNED_OPENSEES_CORE_VERSION = "3.7.1"
ZERO_HASH = "sha256:" + "0" * 64


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


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"external_case_model_nonfinite_json:{token}")


def _finite_json_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"external_case_model_nonfinite_json:{token}")
    return value


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"external_case_model_duplicate_json_key:{key}")
        payload[key] = value
    return payload


def _load_case(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    payload = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
        parse_float=_finite_json_float,
    )
    if not isinstance(payload, dict):
        raise ValueError("external_case_model_invalid")
    if payload.get("artifact_hash") != _artifact_hash(payload):
        raise ValueError("external_case_model_hash_invalid")
    return payload, raw


def _runtime() -> dict[str, str]:
    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "openseespy_version": importlib.metadata.version("openseespy"),
        "opensees_core_version": str(ops.version()),
    }


def _basic_analysis() -> None:
    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-13, 50)
    ops.algorithm("Newton")


def _p_delta_metrics(model: dict[str, Any]) -> tuple[dict[str, float], list[int]]:
    properties = model["properties"]
    ratios = [float(value) for value in model["load_ratios"]]
    height = float(properties["story_height_m"])
    width = float(properties["bay_width_m"])
    modulus = float(properties["youngs_modulus_kn_per_m2"])
    column_area = float(properties["column_area_m2"])
    column_inertia = float(properties["column_second_moment_m4"])
    beam_area = float(properties["beam_area_m2"])
    beam_inertia = float(properties["beam_second_moment_m4"])
    critical = float(model["product_critical_gravity_load_kn"])
    return_codes: list[int] = []
    stiffnesses: list[float] = []

    for ratio in ratios:
        ops.wipe()
        ops.model("basic", "-ndm", 2, "-ndf", 3)
        for tag, x_value, y_value in (
            (1, 0.0, 0.0),
            (2, 0.0, height),
            (3, width, height),
            (4, width, 0.0),
        ):
            ops.node(tag, x_value, y_value)
        ops.fix(1, 1, 1, 1)
        ops.fix(4, 1, 1, 1)
        ops.geomTransf("PDelta", 1)
        ops.geomTransf("Linear", 2)
        ops.element(
            "elasticBeamColumn",
            1,
            1,
            2,
            column_area,
            modulus,
            column_inertia,
            1,
        )
        ops.element(
            "elasticBeamColumn",
            2,
            2,
            3,
            beam_area,
            modulus,
            beam_inertia,
            2,
        )
        ops.element(
            "elasticBeamColumn",
            3,
            4,
            3,
            column_area,
            modulus,
            column_inertia,
            1,
        )
        gravity = critical * ratio
        ops.timeSeries("Linear", 1)
        ops.pattern("Plain", 1, 1)
        ops.load(2, 0.0, -0.5 * gravity, 0.0)
        ops.load(3, 0.0, -0.5 * gravity, 0.0)
        _basic_analysis()
        ops.integrator("LoadControl", 0.1)
        ops.analysis("Static")
        gravity_code = int(ops.analyze(10))
        return_codes.append(gravity_code)
        if gravity_code != 0:
            stiffnesses.append(float("nan"))
            continue
        ops.loadConst("-time", 0.0)
        ops.timeSeries("Linear", 2)
        ops.pattern("Plain", 2, 2)
        ops.load(2, 0.5, 0.0, 0.0)
        ops.load(3, 0.5, 0.0, 0.0)
        ops.integrator("LoadControl", 1.0)
        ops.analysis("Static")
        lateral_code = int(ops.analyze(1))
        return_codes.append(lateral_code)
        if lateral_code != 0:
            stiffnesses.append(float("nan"))
            continue
        sway = 0.5 * (float(ops.nodeDisp(2, 1)) + float(ops.nodeDisp(3, 1)))
        stiffnesses.append(1.0 / sway)

    ops.wipe()
    base = stiffnesses[0]
    metrics = {"pdelta.base_effective_stiffness_kn_per_m": base}
    for ratio, stiffness in zip(ratios[1:], stiffnesses[1:], strict=True):
        token = str(ratio).replace("0.", "0p")
        metrics[f"pdelta.amplification.ratio_{token}"] = base / stiffness
    metrics["pdelta.response.monotonic"] = float(
        all(
            stiffnesses[index + 1] < stiffnesses[index]
            for index in range(len(stiffnesses) - 1)
        )
    )
    return metrics, return_codes


def _snap_through_metrics(
    model: dict[str, Any],
) -> tuple[dict[str, float], list[int]]:
    properties = model["properties"]
    count = int(properties["elements_per_member"])
    length = float(properties["member_length_m"])
    modulus = float(properties["youngs_modulus_kn_per_m2"])
    area = float(properties["area_m2"])
    inertia = float(properties["second_moment_m4"])
    arc_length = float(model["arc_length_m"])
    load_metric_scale = float(model["load_factor_metric_scale_m"])
    maximum_steps = int(model["maximum_steps"])

    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    coordinates = [(0.0, length * index / count) for index in range(count + 1)] + [
        (length * index / count, length) for index in range(1, count + 1)
    ]
    for tag, (x_value, y_value) in enumerate(coordinates, start=1):
        ops.node(tag, x_value, y_value)
    ops.fix(1, 1, 1, 0)
    ops.fix(2 * count + 1, 1, 1, 0)
    ops.geomTransf("Corotational", 1)
    for tag in range(1, 2 * count + 1):
        ops.element("elasticBeamColumn", tag, tag, tag + 1, area, modulus, inertia, 1)
    load_node = count + count // 5 + 1
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    ops.load(load_node, 0.0, -1.0, 0.0)
    ops.constraints("Plain")
    ops.numberer("RCM")
    ops.system("UmfPack")
    ops.test("NormUnbalance", 1.0e-7, 40)
    ops.algorithm("Newton")
    ops.integrator("ArcLength", arc_length, load_metric_scale)
    ops.analysis("Static")

    rows: list[tuple[float, float, float]] = []
    return_codes: list[int] = []
    for _step in range(maximum_steps):
        code = int(ops.analyze(1))
        return_codes.append(code)
        if code != 0:
            break
        horizontal = float(ops.nodeDisp(load_node, 1))
        downward = -float(ops.nodeDisp(load_node, 2))
        load_factor = float(ops.getLoadFactor(1))
        rows.append((horizontal, downward, load_factor))
        if load_factor < -2.0 and horizontal > 0.7:
            break
    ops.wipe()
    if not rows:
        return {
            "snap.first_limit.load_factor": float("nan"),
            "snap.first_limit.horizontal_displacement_m": float("nan"),
            "snap.first_limit.downward_displacement_m": float("nan"),
            "snap.descending_branch_observed": 0.0,
            "snap.negative_load_observed": 0.0,
        }, return_codes
    first_limit_index = max(range(len(rows)), key=lambda index: rows[index][2])
    horizontal, downward, load_factor = rows[first_limit_index]
    descending = any(
        rows[index + 1][2] < rows[index][2] - 1.0e-8
        for index in range(first_limit_index, len(rows) - 1)
    )
    return {
        "snap.first_limit.load_factor": load_factor,
        "snap.first_limit.horizontal_displacement_m": horizontal,
        "snap.first_limit.downward_displacement_m": downward,
        "snap.descending_branch_observed": float(descending),
        "snap.negative_load_observed": float(any(row[2] < 0.0 for row in rows)),
    }, return_codes


def _steel_yield_metrics(
    model: dict[str, Any],
) -> tuple[dict[str, float], list[int]]:
    material = model["steel"]
    modulus = float(material["elastic_modulus_mpa"])
    yield_stress = float(material["yield_stress_mpa"])
    hardening = float(material["isotropic_hardening_modulus_mpa"]) + float(
        material["kinematic_hardening_modulus_mpa"]
    )
    post_yield_ratio = hardening / (modulus + hardening)
    strains = [float(value) for value in model["strain_path"]]
    metrics: dict[str, float] = {}
    yielded_count = 0
    for strain in strains:
        ops.wipe()
        ops.uniaxialMaterial("Steel01", 1, yield_stress, modulus, post_yield_ratio)
        ops.testUniaxialMaterial(1)
        ops.setStrain(strain)
        stress = float(ops.getStress())
        tangent = float(ops.getTangent())
        token = f"{strain:.6f}".replace("0.", "0p").replace(".", "p")
        metrics[f"steel.stress.strain_{token}_mpa"] = stress
        if abs(stress) >= yield_stress and tangent < 0.5 * modulus:
            yielded_count += 1
    metrics["steel.post_yield_tangent_mpa"] = modulus * post_yield_ratio
    metrics["steel.yielded_point_count"] = float(yielded_count)
    ops.wipe()
    return metrics, [0] * len(strains)


def _build_section(model: dict[str, Any]) -> None:
    concrete = model["concrete"]
    steel = model["steel"]
    hardening = float(steel["isotropic_hardening_modulus_mpa"]) + float(
        steel["kinematic_hardening_modulus_mpa"]
    )
    modulus = float(steel["elastic_modulus_mpa"])
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    ops.node(1, 0.0, 0.0)
    ops.node(2, 0.0, 0.0)
    ops.node(3, 1.0, 0.0)
    ops.node(4, 2.0, 0.0)
    ops.fix(1, 1, 1, 1)
    ops.fix(2, 0, 1, 0)
    ops.fix(3, 0, 1, 1)
    ops.fix(4, 1, 1, 1)
    if model["case_kind"] == "rc_fiber_nonlinear_section":
        ops.uniaxialMaterial(
            "Concrete02",
            1,
            -float(concrete["compressive_strength_mpa"]),
            -float(concrete["compressive_peak_strain"]),
            -float(concrete["residual_compressive_strength_mpa"]),
            -float(concrete["ultimate_compressive_strain"]),
            float(concrete["unloading_ratio"]),
            float(concrete["tensile_strength_mpa"]),
            float(concrete["tension_softening_slope_mpa"]),
        )
    else:
        # The product recovery rows intentionally exercise the undamaged
        # elastic section state.  Concrete02 has a parabolic compressive
        # branch even below the nominal strength, so using it here would
        # compare different constitutive laws rather than recovery accuracy.
        ops.uniaxialMaterial("Elastic", 1, float(concrete["elastic_modulus_mpa"]))
    ops.uniaxialMaterial(
        "Steel01",
        2,
        float(steel["yield_stress_mpa"]),
        modulus,
        hardening / (modulus + hardening),
    )
    ops.uniaxialMaterial("Elastic", 3, 1.0)
    ops.section("Fiber", 1)
    for fiber in model["fibers"]:
        material_tag = 2 if fiber["material_kind"] == "steel" else 1
        ops.fiber(
            float(fiber["y_m"]),
            0.0,
            float(fiber["area_m2"]),
            material_tag,
        )
    ops.element("zeroLengthSection", 1, 1, 2, 1)
    ops.element("truss", 2, 3, 4, 1.0, 3)


def _section_metrics(
    model: dict[str, Any],
) -> tuple[dict[str, float], list[int]]:
    _build_section(model)
    deformation = model["generalized_strain"]
    axial_strain = float(deformation["axial_strain"])
    curvature = float(deformation["curvature_z_per_m"])
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    ops.sp(2, 1, axial_strain)
    ops.sp(2, 3, curvature)
    ops.constraints("Transformation")
    ops.numberer("Plain")
    ops.system("BandGeneral")
    ops.test("NormDispIncr", 1.0e-12, 20)
    ops.algorithm("Newton")
    ops.integrator("LoadControl", 1.0)
    ops.analysis("Static")
    code = int(ops.analyze(1))
    section_force = [
        float(value) * 1000.0 for value in ops.eleResponse(1, "section", "force")
    ]
    metrics: dict[str, float] = {
        "section.axial_force_kn": section_force[0],
        "section.moment_z_kn_m": section_force[1],
        "fiber.count": float(len(model["fibers"])),
    }
    nonlinear_concrete = 0
    yielded_steel = 0
    for index, fiber in enumerate(model["fibers"]):
        stress, strain = (
            float(value)
            for value in ops.eleResponse(
                1,
                "section",
                "fiber",
                float(fiber["y_m"]),
                0.0,
                "stressStrain",
            )
        )
        metrics[f"fiber.{index}.strain"] = strain
        metrics[f"fiber.{index}.stress_mpa"] = stress
        if fiber["material_kind"] == "steel":
            yielded_steel += int(
                abs(strain)
                > float(model["steel"]["yield_stress_mpa"])
                / float(model["steel"]["elastic_modulus_mpa"])
            )
        else:
            elastic_stress = float(model["concrete"]["elastic_modulus_mpa"]) * strain
            nonlinear_concrete += int(
                abs(stress - elastic_stress) > 1.0e-6 * max(1.0, abs(elastic_stress))
            )
    metrics["rc.yielded_steel_fiber_count"] = float(yielded_steel)
    metrics["rc.nonlinear_concrete_fiber_count"] = float(nonlinear_concrete)
    ops.wipe()
    return metrics, [code]


def _run(model: dict[str, Any]) -> tuple[dict[str, float], list[int]]:
    case_id = str(model["case_id"])
    if case_id == "bounded_planar_p_delta":
        return _p_delta_metrics(model)
    if case_id == "bounded_planar_snap_through":
        return _snap_through_metrics(model)
    if case_id == "bounded_planar_steel_yield":
        return _steel_yield_metrics(model)
    if case_id in {
        "bounded_planar_rc_fiber",
        "bounded_planar_section_recovery",
        "bounded_planar_fiber_recovery",
    }:
        return _section_metrics(model)
    raise ValueError("external_case_identity_invalid")


def _signature_blockers(case_id: str, metrics: dict[str, float]) -> list[str]:
    blockers: list[str] = []
    if (
        case_id == "bounded_planar_p_delta"
        and metrics.get("pdelta.response.monotonic") != 1.0
    ):
        blockers.append("pdelta_amplification_not_monotonic")
    if case_id == "bounded_planar_snap_through":
        if metrics.get("snap.descending_branch_observed") != 1.0:
            blockers.append("snap_through_descending_branch_missing")
        if metrics.get("snap.negative_load_observed") != 1.0:
            blockers.append("snap_through_negative_load_branch_missing")
    if (
        case_id == "bounded_planar_steel_yield"
        and metrics.get("steel.yielded_point_count", 0.0) < 2.0
    ):
        blockers.append("steel_yield_signature_missing")
    if case_id == "bounded_planar_rc_fiber":
        if metrics.get("rc.yielded_steel_fiber_count", 0.0) < 1.0:
            blockers.append("rc_steel_yield_signature_missing")
        if metrics.get("rc.nonlinear_concrete_fiber_count", 0.0) < 1.0:
            blockers.append("rc_concrete_nonlinearity_signature_missing")
    if (
        case_id
        in {
            "bounded_planar_section_recovery",
            "bounded_planar_fiber_recovery",
        }
        and metrics.get("fiber.count") != 4.0
    ):
        blockers.append("recovery_fiber_inventory_invalid")
    return blockers


def build_result(*, case_id: str, model_path: Path) -> dict[str, Any]:
    model, model_bytes = _load_case(model_path)
    if model.get("package_id") != PACKAGE_ID or model.get("case_id") != case_id:
        raise ValueError("external_case_binding_mismatch")
    runtime = _runtime()
    metrics, return_codes = _run(model)
    blockers: list[str] = []
    if runtime["openseespy_version"] != PINNED_OPENSEESPY_VERSION:
        blockers.append("openseespy_version_mismatch")
    if runtime["opensees_core_version"] != PINNED_OPENSEES_CORE_VERSION:
        blockers.append("opensees_core_version_mismatch")
    if not return_codes or any(code != 0 for code in return_codes):
        blockers.append("nonzero_return_code")
    if not metrics or any(not math.isfinite(value) for value in metrics.values()):
        blockers.append("nonfinite_metric")
    blockers.extend(_signature_blockers(case_id, metrics))
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "case_id": case_id,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "runner_file_sha256": _hash_bytes(Path(__file__).read_bytes()),
        "source_model_file_sha256": _hash_bytes(model_bytes),
        "runtime": runtime,
        "return_codes": return_codes,
        "metrics": metrics,
        "contract_pass": not blockers,
        "blockers": sorted(set(blockers)),
        "artifact_hash": ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_result(case_id=args.case_id, model_path=args.model)
        _write_json(args.out, result)
    except Exception as exc:  # standalone runner must fail visibly
        print(
            f"external_case_execution_failed:{type(exc).__name__}:{exc}",
            file=sys.stderr,
        )
        return 1
    print(
        f"{args.case_id}: contract_pass={str(result['contract_pass']).lower()} | "
        f"metrics={len(result['metrics'])}"
    )
    return 0 if result["contract_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
