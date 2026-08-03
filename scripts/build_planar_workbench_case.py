#!/usr/bin/env python3
"""Project a public planar result into the Workbench v2 evidence contract.

Only values explicitly present in the ModelIR, public result, or validation report
are projected. Missing numerical fields remain explicit ``unavailable`` evidence;
the adapter never derives convergence or substitutes numeric defaults.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence


PROFILE = "planar_frame_verified_alpha.v1"


class PlanarWorkbenchProjectionError(RuntimeError):
    """Raised when a public planar artifact cannot be projected safely."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanarWorkbenchProjectionError(f"invalid_json:{path}") from error
    if not isinstance(payload, dict):
        raise PlanarWorkbenchProjectionError(f"json_not_object:{path}")
    return payload


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(serialized)
        temporary = Path(handle.name)
    temporary.replace(path)


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: object) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _available(value: object) -> dict[str, Any]:
    return {"status": "available", "value": value}


def _unavailable() -> dict[str, str]:
    return {"status": "unavailable"}


def _number(value: object, *, integer: bool = False) -> dict[str, Any]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _unavailable()
    normalized = int(value) if integer and isinstance(value, int) else float(value)
    if integer and (not isinstance(value, int) or value < 0):
        return _unavailable()
    return _available(normalized)


def _first_number(row: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    for key in keys:
        if key in row:
            value = _number(row[key])
            if value["status"] == "available":
                return value
    return _unavailable()


def _history(result_ir: Mapping[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(_rows(result_ir.get("convergence_history"))):
        iteration = _first_number(row, ("iteration", "iteration_index"))
        if iteration["status"] == "unavailable":
            iteration = _available(index)
        elif not float(iteration["value"]).is_integer():
            iteration = _unavailable()
        else:
            iteration = _available(int(iteration["value"]))
        normalized.append(
            {
                "iteration": iteration,
                "residual": _first_number(
                    row,
                    (
                        "scaled_residual_norm",
                        "normalized_residual",
                        "relative_residual",
                        "residual_norm",
                        "residual",
                    ),
                ),
                "relativeIncrement": _first_number(
                    row,
                    (
                        "relative_increment",
                        "scaled_increment_norm",
                        "increment_norm",
                    ),
                ),
                "alpha": _first_number(
                    row,
                    ("line_search_alpha", "accepted_alpha", "alpha"),
                ),
                "source": dict(row),
            }
        )
    return normalized


def build_workbench_case(
    *,
    model_path: Path,
    result_path: Path,
    report_path: Path,
    source_commit_sha: str,
    engine_version: str,
    generated_at: str,
) -> dict[str, Any]:
    if len(source_commit_sha) != 40 or any(
        character not in "0123456789abcdef" for character in source_commit_sha
    ):
        raise PlanarWorkbenchProjectionError("source_commit_sha_invalid")
    if not engine_version or engine_version == "unknown":
        raise PlanarWorkbenchProjectionError("engine_version_invalid")
    if not generated_at or generated_at == "unknown":
        raise PlanarWorkbenchProjectionError("generated_at_invalid")

    model = _load_object(model_path)
    result = _load_object(result_path)
    report = _load_object(report_path)
    if model.get("capability_profile") != PROFILE:
        raise PlanarWorkbenchProjectionError("model_profile_not_public_planar")
    if result.get("profile") != PROFILE:
        raise PlanarWorkbenchProjectionError("result_profile_not_public_planar")
    if report.get("artifact_contract_pass") is not True:
        raise PlanarWorkbenchProjectionError("result_artifact_contract_blocked")
    if report.get("execution_contract_pass") is not True:
        raise PlanarWorkbenchProjectionError("result_execution_contract_blocked")

    result_ir = _mapping(result.get("result_ir"))
    configuration = _mapping(result_ir.get("configuration"))
    metrics = _mapping(result_ir.get("metrics"))
    bindings = _mapping(result_ir.get("contract_bindings"))
    execution_plan = _mapping(bindings.get("bounded_planar_execution_plan"))
    scaling = _mapping(configuration.get("equation_scaling"))
    history = _history(result_ir)
    last_history = history[-1] if history else {}

    status = str(result.get("status", "not_run"))
    if status not in {"converged", "not_converged", "not_run"}:
        raise PlanarWorkbenchProjectionError("result_status_invalid")
    converged: object
    if status == "converged":
        converged = True
    elif status == "not_converged":
        converged = False
    else:
        converged = _unavailable()

    node_count = len(model.get("nodes", [])) if isinstance(model.get("nodes"), list) else None
    element_count = (
        len(model.get("elements", [])) if isinstance(model.get("elements"), list) else None
    )
    physical_dof_count = execution_plan.get("physical_dof_count")
    terminal_residual = _first_number(
        metrics,
        ("dimensionless_scaled_residual_linf", "scaled_residual_norm"),
    )
    if terminal_residual["status"] == "unavailable" and last_history:
        terminal_residual = last_history.get("residual", _unavailable())
    terminal_increment = (
        last_history.get("relativeIncrement", _unavailable())
        if last_history
        else _unavailable()
    )

    public_result_hash = result.get("result_hash")
    if not isinstance(public_result_hash, str) or not public_result_hash.startswith("sha256:"):
        raise PlanarWorkbenchProjectionError("public_result_hash_invalid")

    return {
        "schemaVersion": "workbench-case.v2",
        "capability_profile": PROFILE,
        "provenance": {
            "sourcePath": model_path.as_posix(),
            "sourceSha256": _sha256(model_path),
            "sourceCommitSha": source_commit_sha,
            "engineVersion": engine_version,
            "generatedAt": generated_at,
            "publicResultHash": public_result_hash,
            "validationReportSha256": _sha256(report_path),
        },
        "model": {
            "unitSystem": "SI",
            "coordinateSystem": "global_xyz",
            "nodeCount": _number(node_count, integer=True),
            "elementCount": _number(element_count, integer=True),
            "dofCount": _number(physical_dof_count, integer=True),
        },
        "analysis": {
            "type": "nonlinear_static",
            "solver": str(result_ir.get("solver_id", "public_planar_load_control")),
            "status": status,
            "converged": converged,
            "loadScale": _first_number(
                metrics, ("terminal_solved_load_factor", "terminal_load_factor")
            ),
            "iterationCount": _available(len(history)),
            "residualTolerance": _first_number(
                configuration,
                ("scaled_residual_tolerance", "residual_tolerance"),
            ),
            "finalNormalizedResidual": terminal_residual,
            "finalRelativeIncrement": terminal_increment,
            "equation_scaling_6dof": {
                "reference_force": _first_number(
                    scaling, ("reference_force_n", "reference_force")
                ),
                "characteristic_length": _first_number(
                    scaling, ("characteristic_length_m", "characteristic_length")
                ),
                "translation_residual_norm": _first_number(
                    metrics, ("raw_translational_residual_linf_n",)
                ),
                "rotation_residual_norm": _first_number(
                    metrics, ("raw_rotational_residual_linf_nm",)
                ),
                "scaled_residual_norm": terminal_residual,
                "translation_increment_norm": _unavailable(),
                "rotation_increment_norm": _unavailable(),
                "scaled_increment_norm": terminal_increment,
                "scaled_tangent_condition": _first_number(
                    metrics,
                    (
                        "scaled_tangent_condition",
                        "linear_solver_scaled_condition_number",
                    ),
                ),
                "scaling_hash": (
                    _available(execution_plan["engine_equation_scaling_hash"])
                    if isinstance(execution_plan.get("engine_equation_scaling_hash"), str)
                    else _unavailable()
                ),
            },
        },
        "residualHistory": history,
        "publicResult": {
            "result_hash": public_result_hash,
            "artifact_contract_pass": report.get("artifact_contract_pass"),
            "execution_contract_pass": report.get("execution_contract_pass"),
            "diagnostic_authority": report.get("diagnostic_authority"),
            "numerical_result_authority": report.get("numerical_result_authority"),
            "engineering_result_authority": report.get("engineering_result_authority"),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--engine-version", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_workbench_case(
        model_path=args.model,
        result_path=args.result,
        report_path=args.report,
        source_commit_sha=args.source_commit,
        engine_version=args.engine_version,
        generated_at=args.generated_at,
    )
    _write_json(args.out, payload)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "planar Workbench case: ready | "
            f"profile={PROFILE} | result={payload['publicResult']['result_hash']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
