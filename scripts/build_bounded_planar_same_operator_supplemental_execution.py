#!/usr/bin/env python3
"""Build and validate the non-promoting same-operator 16-case execution bundle."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
SRC_ROOT = ROOT / "src"
for search_root in (SCRIPT_DIR, SRC_ROOT):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import build_bounded_planar_external_linear_case_package as linear_package  # noqa: E402
import build_bounded_planar_external_modal_buckling_case_package as modal_package  # noqa: E402
import build_bounded_planar_external_negative_case_package as negative_package  # noqa: E402
import build_bounded_planar_external_nonlinear_material_recovery_case_package as nonlinear_package  # noqa: E402
import build_bounded_planar_external_scaling_case_package as scaling_package  # noqa: E402
import ingest_bounded_planar_external_linear_results as linear_ingest  # noqa: E402
import ingest_bounded_planar_external_modal_buckling_results as modal_ingest  # noqa: E402
import ingest_bounded_planar_external_negative_results as negative_ingest  # noqa: E402
import ingest_bounded_planar_external_nonlinear_material_recovery_results as nonlinear_ingest  # noqa: E402
import ingest_bounded_planar_external_scaling_results as scaling_ingest  # noqa: E402


SCHEMA_VERSION = "bounded-planar-same-operator-supplemental-execution.v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_same_operator_supplemental_execution_v1.schema.json"
)
DEFAULT_OUT_DIR = Path(
    "artifacts/vv/bounded_planar_same_operator_supplemental_execution"
)
RECEIPT_NAME = "receipt.json"
HISTORICAL_PACKAGE_DIRNAME = "historical_packages"
ZERO_HASH = "sha256:" + "0" * 64
DEFAULT_REUSE_REASON = (
    "Retained same-operator external result bytes were compared with product "
    "results regenerated from the current source; no external runtime was "
    "executed while generating this replay receipt."
)
_CURRENT_PACKAGE_CHECK_CACHE: set[tuple[str, str, str]] = set()


class SameOperatorSupplementalExecutionError(ValueError):
    """Stable fail-closed error for the local supplemental execution bundle."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise SameOperatorSupplementalExecutionError(code)


@dataclass(frozen=True)
class Family:
    family_id: str
    input_subdir: str
    package_dir: Path
    package_id: str
    package_module: ModuleType
    ingest_module: ModuleType
    receipt_name: str
    case_ids: tuple[str, ...]
    builder_name: str
    model_descriptor_key: str
    runner_descriptor_key: str


FAMILIES = (
    Family(
        family_id="linear",
        input_subdir="linear",
        package_dir=linear_package.DEFAULT_OUT_DIR,
        package_id="bounded-planar-linear-portal-multistory-v1",
        package_module=linear_package,
        ingest_module=linear_ingest,
        receipt_name="linear-technical-receipt.json",
        case_ids=(
            "bounded_planar_linear_portal",
            "bounded_planar_linear_multistory",
        ),
        builder_name="build_execution_receipt",
        model_descriptor_key="model_ir",
        runner_descriptor_key="opensees_runner",
    ),
    Family(
        family_id="negative",
        input_subdir="negative",
        package_dir=negative_package.DEFAULT_OUT_DIR,
        package_id="bounded-planar-negative-rejection-v1",
        package_module=negative_package,
        ingest_module=negative_ingest,
        receipt_name="negative-technical-receipt.json",
        case_ids=(
            "bounded_planar_negative_mechanism",
            "bounded_planar_negative_singular",
            "bounded_planar_negative_invalid_geometry",
        ),
        builder_name="build_execution_receipt",
        model_descriptor_key="model_ir",
        runner_descriptor_key="opensees_runner",
    ),
    Family(
        family_id="scaling",
        input_subdir="scaling",
        package_dir=scaling_package.DEFAULT_OUT_DIR,
        package_id="bounded-planar-scaling-invariance-v1",
        package_module=scaling_package,
        ingest_module=scaling_ingest,
        receipt_name="scaling-technical-receipt.json",
        case_ids=(
            "bounded_planar_scaling_unit_invariance",
            "bounded_planar_scaling_characteristic_length_invariance",
        ),
        builder_name="build_execution_receipt",
        model_descriptor_key="model_pair",
        runner_descriptor_key="opensees_runner",
    ),
    Family(
        family_id="modal_buckling",
        input_subdir="modal-buckling",
        package_dir=modal_package.DEFAULT_OUT_DIR,
        package_id="bounded-planar-modal-buckling-v1",
        package_module=modal_package,
        ingest_module=modal_ingest,
        receipt_name="modal-buckling-technical-receipt.json",
        case_ids=(
            "bounded_planar_modal_rigid_mode",
            "bounded_planar_modal_repeated_mode",
            "bounded_planar_buckling_portal",
        ),
        builder_name="build_receipt",
        model_descriptor_key="model",
        runner_descriptor_key="external_runner",
    ),
    Family(
        family_id="nonlinear_material_recovery",
        input_subdir="nonlinear-material-recovery",
        package_dir=nonlinear_package.DEFAULT_OUT_DIR,
        package_id="bounded-planar-nonlinear-material-recovery-v1",
        package_module=nonlinear_package,
        ingest_module=nonlinear_ingest,
        receipt_name="nonlinear-material-recovery-technical-receipt.json",
        case_ids=(
            "bounded_planar_p_delta",
            "bounded_planar_snap_through",
            "bounded_planar_steel_yield",
            "bounded_planar_rc_fiber",
            "bounded_planar_section_recovery",
            "bounded_planar_fiber_recovery",
        ),
        builder_name="build_execution_receipt",
        model_descriptor_key="model",
        runner_descriptor_key="external_runner",
    ),
)


RUNTIME_ASSETS = (
    {
        "asset_id": "openseespy",
        "file_name": "openseespy-3.7.1.2-py3-none-any.whl",
        "version": "3.7.1.2",
        "file_sha256": "sha256:1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65",
        "size_bytes": 5337,
        "bytes_attached": False,
    },
    {
        "asset_id": "openseespylinux",
        "file_name": "openseespylinux-3.7.1.2-py3-none-any.whl",
        "version": "3.7.1.2",
        "file_sha256": "sha256:63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a",
        "size_bytes": 58094841,
        "bytes_attached": False,
    },
    {
        "asset_id": "calculix_ccx",
        "file_name": "calculix-ccx_2.17-3_amd64.deb",
        "version": "2.17-3",
        "file_sha256": "sha256:3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e",
        "size_bytes": 1824872,
        "bytes_attached": False,
    },
    {
        "asset_id": "libarpack2",
        "file_name": "libarpack2_3.8.0-1_amd64.deb",
        "version": "3.8.0-1",
        "file_sha256": "sha256:07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a",
        "size_bytes": 92420,
        "bytes_attached": False,
    },
    {
        "asset_id": "libspooles2.2",
        "file_name": "libspooles2.2_2.2-14_amd64.deb",
        "version": "2.2-14",
        "file_sha256": "sha256:34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917",
        "size_bytes": 465536,
        "bytes_attached": False,
    },
)


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


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SameOperatorSupplementalExecutionError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _resolved(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _resolved_non_symlink_root(
    repo_root: Path, path: Path, *, code: str
) -> Path:
    candidate = path if path.is_absolute() else repo_root / path
    if candidate.is_symlink():
        _fail(code)
    return candidate.resolve()


def _relative(repo_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _parse_timestamp(value: object, code: str) -> datetime:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SameOperatorSupplementalExecutionError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


def _validate_runtime_assets(asset_root: Path) -> None:
    expected_names = {row["file_name"] for row in RUNTIME_ASSETS}
    actual_names = {path.name for path in asset_root.iterdir() if path.is_file()}
    if actual_names != expected_names:
        _fail("same_operator_runtime_asset_file_set_invalid")
    for descriptor in RUNTIME_ASSETS:
        path = asset_root / descriptor["file_name"]
        if (
            _file_hash(path) != descriptor["file_sha256"]
            or path.stat().st_size != descriptor["size_bytes"]
        ):
            _fail(f"same_operator_runtime_asset_invalid:{descriptor['asset_id']}")


def _validate_input_results(input_root: Path, family: Family) -> Path:
    source = input_root / family.input_subdir
    if not source.is_dir():
        _fail(f"same_operator_input_directory_missing:{family.family_id}")
    expected = {f"{case_id}.json" for case_id in family.case_ids}
    actual = {path.name for path in source.iterdir() if path.is_file()}
    if actual != expected:
        _fail(f"same_operator_input_file_set_invalid:{family.family_id}")
    return source


def _safe_relative_path(value: object, code: str) -> Path:
    if not isinstance(value, str) or not value:
        _fail(code)
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        _fail(code)
    return path


def _descriptor_path(
    descriptor: object, *, code: str
) -> tuple[Path, str, str | None]:
    if not isinstance(descriptor, dict):
        _fail(code)
    relative = _safe_relative_path(descriptor.get("path"), code)
    file_hash = descriptor.get("file_sha256")
    artifact_hash = descriptor.get("artifact_hash")
    if (
        not isinstance(file_hash, str)
        or not file_hash.startswith("sha256:")
        or (
            artifact_hash is not None
            and (
                not isinstance(artifact_hash, str)
                or not artifact_hash.startswith("sha256:")
            )
        )
    ):
        _fail(code)
    return relative, file_hash, artifact_hash


def _package_descriptors(
    *, manifest: dict[str, Any], family: Family
) -> tuple[dict[Path, tuple[str, str | None]], list[dict[str, Any]]]:
    if (
        manifest.get("package_id") != family.package_id
        or manifest.get("artifact_hash") != _artifact_hash(manifest)
    ):
        _fail(f"same_operator_historical_manifest_invalid:{family.family_id}")
    cases = manifest.get("cases")
    if (
        not isinstance(cases, list)
        or [str(row.get("case_id") or "") for row in cases]
        != list(family.case_ids)
    ):
        _fail(f"same_operator_historical_case_set_invalid:{family.family_id}")
    descriptors: dict[Path, tuple[str, str | None]] = {}
    for key in (
        "operator_readme",
        "python_requirements",
        "execution_workflow",
        "external_result_schema",
    ):
        relative, file_hash, artifact_hash = _descriptor_path(
            manifest.get(key),
            code=f"same_operator_historical_descriptor_invalid:{family.family_id}",
        )
        descriptors[relative] = (file_hash, artifact_hash)
    for case in cases:
        for key in (
            family.model_descriptor_key,
            family.runner_descriptor_key,
            "product_result",
        ):
            relative, file_hash, artifact_hash = _descriptor_path(
                case.get(key),
                code=(
                    "same_operator_historical_case_descriptor_invalid:"
                    f"{case.get('case_id')}"
                ),
            )
            previous = descriptors.get(relative)
            if previous is not None and previous != (file_hash, artifact_hash):
                _fail(
                    "same_operator_historical_duplicate_descriptor_invalid:"
                    f"{family.family_id}"
                )
            descriptors[relative] = (file_hash, artifact_hash)
    return descriptors, cases


def _validate_package_snapshot(
    *, package_root: Path, family: Family
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if package_root.is_symlink():
        _fail(f"same_operator_historical_package_root_symlink:{family.family_id}")
    manifest_path = package_root / family.package_module.MANIFEST_NAME
    manifest = _load_json(
        manifest_path,
        f"same_operator_historical_manifest_unreadable:{family.family_id}",
    )
    descriptors, _cases = _package_descriptors(manifest=manifest, family=family)
    expected = {family.package_module.MANIFEST_NAME, *(path.as_posix() for path in descriptors)}
    if any(path.is_symlink() for path in package_root.rglob("*")):
        _fail(f"same_operator_historical_package_symlink:{family.family_id}")
    actual = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        _fail(f"same_operator_historical_package_file_set_invalid:{family.family_id}")
    files: list[dict[str, str]] = []
    for relative in sorted(descriptors, key=lambda item: item.as_posix()):
        expected_file_hash, expected_artifact_hash = descriptors[relative]
        path = package_root / relative
        if _file_hash(path) != expected_file_hash:
            _fail(
                "same_operator_historical_package_file_hash_invalid:"
                f"{family.family_id}:{relative.as_posix()}"
            )
        if expected_artifact_hash is not None:
            payload = _load_json(
                path,
                "same_operator_historical_package_json_invalid:"
                f"{family.family_id}:{relative.as_posix()}",
            )
            embedded_artifact_hash = payload.get("artifact_hash")
            if expected_artifact_hash != _artifact_hash(payload) or (
                embedded_artifact_hash is not None
                and embedded_artifact_hash != expected_artifact_hash
            ):
                _fail(
                    "same_operator_historical_package_artifact_hash_invalid:"
                    f"{family.family_id}:{relative.as_posix()}"
                )
        files.append(
            {
                "path": relative.as_posix(),
                "file_sha256": expected_file_hash,
            }
        )
    return manifest, files


def _validate_raw_execution_binding(
    *,
    family: Family,
    historical_root: Path,
    historical_manifest: dict[str, Any],
    results_root: Path,
) -> None:
    _descriptors, cases = _package_descriptors(
        manifest=historical_manifest, family=family
    )
    schema_relative, _schema_hash, _artifact_hash_value = _descriptor_path(
        historical_manifest.get("external_result_schema"),
        code=f"same_operator_historical_result_schema_invalid:{family.family_id}",
    )
    result_schema = _load_json(
        historical_root / schema_relative,
        f"same_operator_historical_result_schema_unreadable:{family.family_id}",
    )
    try:
        Draft202012Validator.check_schema(result_schema)
    except SchemaError as exc:
        raise SameOperatorSupplementalExecutionError(
            f"same_operator_historical_result_schema_invalid:{family.family_id}"
        ) from exc
    for case in cases:
        case_id = str(case["case_id"])
        result = _load_json(
            results_root / f"{case_id}.json",
            f"same_operator_historical_result_invalid:{case_id}",
        )
        try:
            Draft202012Validator(
                result_schema, format_checker=FormatChecker()
            ).validate(result)
        except ValidationError as exc:
            raise SameOperatorSupplementalExecutionError(
                f"same_operator_historical_result_schema_mismatch:{case_id}"
            ) from exc
        model_descriptor = case[family.model_descriptor_key]
        runner_descriptor = case[family.runner_descriptor_key]
        model_hash = result.get(
            "source_model_file_sha256",
            result.get("source_model_pair_file_sha256"),
        )
        if (
            result.get("case_id") != case_id
            or result.get("package_id") != family.package_id
            or result.get("artifact_hash") != _artifact_hash(result)
            or result.get("runner_file_sha256")
            != runner_descriptor.get("file_sha256")
            or model_hash != model_descriptor.get("file_sha256")
        ):
            _fail(f"same_operator_historical_result_binding_invalid:{case_id}")
        _parse_timestamp(
            result.get("executed_at"),
            f"same_operator_historical_result_timestamp_invalid:{case_id}",
        )


def _case_semantics(case: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "case_id",
        "requirement_id",
        "metric_ids",
        "analysis_type",
        "case_kind",
        "expected_external_observation",
        "expected_product_reason_code",
        "external_solver",
    )
    return {key: case[key] for key in keys if key in case}


def _validate_current_historical_semantics(
    *,
    family: Family,
    current_manifest: dict[str, Any],
    historical_manifest: dict[str, Any],
) -> None:
    current_descriptors, current_cases = _package_descriptors(
        manifest=current_manifest, family=family
    )
    historical_descriptors, historical_cases = _package_descriptors(
        manifest=historical_manifest, family=family
    )
    current_schema, current_schema_hash, _ = _descriptor_path(
        current_manifest.get("external_result_schema"),
        code=f"same_operator_current_result_schema_invalid:{family.family_id}",
    )
    historical_schema, historical_schema_hash, _ = _descriptor_path(
        historical_manifest.get("external_result_schema"),
        code=f"same_operator_historical_result_schema_invalid:{family.family_id}",
    )
    if (
        current_schema.name != historical_schema.name
        or current_schema_hash != historical_schema_hash
        or [_case_semantics(row) for row in current_cases]
        != [_case_semantics(row) for row in historical_cases]
    ):
        _fail(f"same_operator_metric_semantics_drift:{family.family_id}")
    for current_case, historical_case in zip(current_cases, historical_cases):
        for key in (family.model_descriptor_key, family.runner_descriptor_key):
            current_relative, current_hash, _ = _descriptor_path(
                current_case.get(key),
                code=f"same_operator_current_case_descriptor_invalid:{family.family_id}",
            )
            historical_relative, historical_hash, _ = _descriptor_path(
                historical_case.get(key),
                code=(
                    "same_operator_historical_case_descriptor_invalid:"
                    f"{family.family_id}"
                ),
            )
            if (
                current_relative.name != historical_relative.name
                or current_hash != historical_hash
                or current_descriptors[current_relative][0] != historical_descriptors[
                    historical_relative
                ][0]
            ):
                _fail(f"same_operator_execution_input_drift:{family.family_id}")


def capture_historical_execution_inputs(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> None:
    out_root = _resolved_non_symlink_root(
        repo_root,
        out_dir,
        code="same_operator_execution_bundle_root_symlink",
    )
    historical_base = out_root / HISTORICAL_PACKAGE_DIRNAME
    if historical_base.exists():
        _fail("same_operator_historical_packages_already_attached")
    for family in FAMILIES:
        source_root = _resolved(repo_root, family.package_dir)
        manifest, files = _validate_package_snapshot(
            package_root=source_root, family=family
        )
        _validate_raw_execution_binding(
            family=family,
            historical_root=source_root,
            historical_manifest=manifest,
            results_root=out_root / "results" / family.family_id,
        )
        target_root = historical_base / family.family_id
        target_root.mkdir(parents=True, exist_ok=False)
        relative_paths = [
            Path(family.package_module.MANIFEST_NAME),
            *(Path(row["path"]) for row in files),
        ]
        for relative in relative_paths:
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source_root / relative).read_bytes())


def _historical_package_binding(
    *, repo_root: Path, out_root: Path, family: Family
) -> tuple[dict[str, Any], dict[str, Any]]:
    historical_root = out_root / HISTORICAL_PACKAGE_DIRNAME / family.family_id
    manifest, files = _validate_package_snapshot(
        package_root=historical_root, family=family
    )
    _validate_raw_execution_binding(
        family=family,
        historical_root=historical_root,
        historical_manifest=manifest,
        results_root=out_root / "results" / family.family_id,
    )
    manifest_path = historical_root / family.package_module.MANIFEST_NAME
    binding = {
        "path": _relative(repo_root, historical_root),
        "manifest_file_sha256": _file_hash(manifest_path),
        "manifest_artifact_hash": manifest["artifact_hash"],
        "source_commit_sha": manifest["source_commit_sha"],
        "file_count": len(files) + 1,
        "files": [
            {
                "path": family.package_module.MANIFEST_NAME,
                "file_sha256": _file_hash(manifest_path),
            },
            *files,
        ],
    }
    binding["binding_hash"] = _hash_bytes(_canonical_bytes(binding))
    return binding, manifest


def _build_child_receipt(
    *, repo_root: Path, family: Family, results_dir: Path
) -> dict[str, Any]:
    checker = getattr(family.package_module, "check_package", None)
    if checker is None:
        _fail(f"same_operator_current_package_checker_missing:{family.family_id}")
    current_package_root = _resolved_non_symlink_root(
        repo_root,
        family.package_dir,
        code=f"same_operator_current_package_root_symlink:{family.family_id}",
    )
    if any(path.is_symlink() for path in current_package_root.rglob("*")):
        _fail(f"same_operator_current_package_symlink:{family.family_id}")
    check_key = (
        str(repo_root.resolve()),
        str(current_package_root),
        family.family_id,
    )
    if check_key not in _CURRENT_PACKAGE_CHECK_CACHE:
        package_ok, _message = checker(
            repo_root=repo_root,
            out_dir=current_package_root,
        )
        if not package_ok:
            _fail(f"same_operator_current_package_bytes_stale:{family.family_id}")
        _CURRENT_PACKAGE_CHECK_CACHE.add(check_key)
    builder = getattr(family.ingest_module, family.builder_name)
    receipt = builder(
        repo_root=repo_root,
        package_dir=family.package_dir,
        results_dir=results_dir,
    )
    if receipt.get("technical_contract_pass") is not True:
        _fail(f"same_operator_child_receipt_blocked:{family.family_id}")
    return receipt


def _external_solver(family: Family, result: dict[str, Any]) -> str:
    if family.family_id == "modal_buckling":
        solver = result.get("external_solver")
        if solver not in {"OpenSees", "CalculiX"}:
            _fail("same_operator_result_solver_invalid")
        return str(solver)
    if (
        family.family_id == "negative"
        and result.get("external_engine_invoked") is False
    ):
        return "independent_preflight"
    return "OpenSees"


def _normalised_runtime(
    *, solver: str, runtime: object
) -> dict[str, str]:
    if not isinstance(runtime, dict):
        _fail("same_operator_result_runtime_invalid")
    if solver == "CalculiX":
        version = runtime.get("solver_version")
    elif solver == "OpenSees":
        version = runtime.get("solver_version", runtime.get("opensees_core_version"))
    else:
        version = runtime.get("opensees_core_version")
    platform_value = runtime.get("platform")
    python_version = runtime.get("python_version")
    if not all(isinstance(value, str) and value for value in (version, platform_value, python_version)):
        _fail("same_operator_result_runtime_invalid")
    return {
        "solver": solver,
        "solver_version": str(version),
        "python_version": str(python_version),
        "platform": str(platform_value),
    }


def _child_fresh_external_execution(
    *, family: Family, child_receipt: dict[str, Any]
) -> bool:
    claims = child_receipt.get("claims")
    if not isinstance(claims, dict):
        _fail(f"same_operator_child_claims_invalid:{family.family_id}")
    key = (
        "fresh_external_solver_execution"
        if family.family_id == "modal_buckling"
        else "fresh_current_source_external_execution"
    )
    fresh = claims.get(key)
    if not isinstance(fresh, bool):
        _fail(f"same_operator_child_freshness_invalid:{family.family_id}")
    return fresh


def _family_row(
    *,
    repo_root: Path,
    out_root: Path,
    family: Family,
    child_receipt: dict[str, Any],
) -> tuple[dict[str, Any], list[datetime], list[dict[str, str]]]:
    package_root = (repo_root / family.package_dir).resolve()
    manifest_path = package_root / family.package_module.MANIFEST_NAME
    manifest = _load_json(
        manifest_path, f"same_operator_package_manifest_invalid:{family.family_id}"
    )
    if (
        manifest.get("package_id") != family.package_id
        or manifest.get("source_commit_sha") != child_receipt.get("source_commit_sha")
        or manifest.get("artifact_hash") != _artifact_hash(manifest)
    ):
        _fail(f"same_operator_package_binding_invalid:{family.family_id}")
    historical_binding, historical_manifest = _historical_package_binding(
        repo_root=repo_root,
        out_root=out_root,
        family=family,
    )
    _validate_current_historical_semantics(
        family=family,
        current_manifest=manifest,
        historical_manifest=historical_manifest,
    )
    if _child_fresh_external_execution(
        family=family, child_receipt=child_receipt
    ):
        _fail(f"same_operator_replay_child_freshness_invalid:{family.family_id}")

    result_root = out_root / "results" / family.family_id
    results: list[dict[str, Any]] = []
    timestamps: list[datetime] = []
    runtime_rows: list[dict[str, str]] = []
    for case_id in family.case_ids:
        path = result_root / f"{case_id}.json"
        result = _load_json(path, f"same_operator_result_invalid:{case_id}")
        if result.get("case_id") != case_id or result.get("artifact_hash") != _artifact_hash(result):
            _fail(f"same_operator_result_binding_invalid:{case_id}")
        executed_at = result.get("executed_at")
        timestamps.append(
            _parse_timestamp(executed_at, f"same_operator_result_timestamp_invalid:{case_id}")
        )
        solver = _external_solver(family, result)
        runtime = _normalised_runtime(solver=solver, runtime=result.get("runtime"))
        runtime_rows.append(runtime)
        invoked = (
            bool(result.get("external_engine_invoked"))
            if family.family_id == "negative"
            else True
        )
        results.append(
            {
                "case_id": case_id,
                "path": _relative(repo_root, path),
                "file_sha256": _file_hash(path),
                "artifact_hash": result["artifact_hash"],
                "executed_at": executed_at,
                "external_solver": solver,
                "external_engine_invoked": invoked,
                "runtime": runtime,
            }
        )

    receipt_path = out_root / "receipts" / family.receipt_name
    row = {
        "family_id": family.family_id,
        "package_binding": {
            "package_id": family.package_id,
            "path": _relative(repo_root, manifest_path),
            "file_sha256": _file_hash(manifest_path),
            "artifact_hash": manifest["artifact_hash"],
            "source_commit_sha": manifest["source_commit_sha"],
        },
        "historical_package_binding": historical_binding,
        "technical_receipt": {
            "path": _relative(repo_root, receipt_path),
            "file_sha256": _file_hash(receipt_path),
            "artifact_hash": child_receipt["artifact_hash"],
        },
        "case_ids": list(family.case_ids),
        "results": results,
        "technical_contract_pass": True,
        "actual_external_solver_execution": any(
            result["external_engine_invoked"] for result in results
        ),
        "raw_execution_binding_pass": True,
        "metric_semantics_match": True,
        "current_product_replay_pass": True,
        "external_runtime_executed_in_this_generation": False,
        "external_execution_reused": True,
        "fresh_current_source_external_execution": False,
        "independent_operator_attested": False,
        "verification_matrix_credit": False,
    }
    return row, timestamps, runtime_rows


def _build_receipt_from_existing(
    *,
    repo_root: Path,
    out_root: Path,
    replay_generated_at: str,
    reuse_reason: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    _parse_timestamp(
        replay_generated_at, "same_operator_replay_timestamp_invalid"
    )
    if not isinstance(reuse_reason, str) or not reuse_reason.strip():
        _fail("same_operator_reuse_reason_invalid")
    family_rows: list[dict[str, Any]] = []
    child_receipts: dict[str, dict[str, Any]] = {}
    timestamps: list[datetime] = []
    runtime_rows: list[dict[str, str]] = []
    source_commits: set[str] = set()
    historical_source_commits: set[str] = set()

    for family in FAMILIES:
        results_dir = out_root / "results" / family.family_id
        expected_names = {f"{case_id}.json" for case_id in family.case_ids}
        actual_names = {
            path.name for path in results_dir.iterdir() if path.is_file()
        }
        if actual_names != expected_names:
            _fail(f"same_operator_bundle_result_file_set_invalid:{family.family_id}")
        rebuilt = _build_child_receipt(
            repo_root=repo_root,
            family=family,
            results_dir=results_dir,
        )
        receipt_path = out_root / "receipts" / family.receipt_name
        stored = _load_json(
            receipt_path,
            f"same_operator_child_receipt_invalid:{family.family_id}",
        )
        if stored != rebuilt:
            _fail(f"same_operator_child_receipt_replay_mismatch:{family.family_id}")
        child_receipts[family.family_id] = stored
        source_commits.add(str(stored.get("source_commit_sha") or ""))
        row, family_timestamps, family_runtimes = _family_row(
            repo_root=repo_root,
            out_root=out_root,
            family=family,
            child_receipt=stored,
        )
        family_rows.append(row)
        historical_source_commits.add(
            str(row["historical_package_binding"]["source_commit_sha"])
        )
        timestamps.extend(family_timestamps)
        runtime_rows.extend(family_runtimes)

    if len(source_commits) != 1:
        _fail("same_operator_source_commit_mismatch")
    source_commit = next(iter(source_commits))
    if len(historical_source_commits) != 1:
        _fail("same_operator_historical_source_commit_mismatch")
    historical_source_commit = next(iter(historical_source_commits))
    unique_runtimes = sorted(
        {tuple(sorted(row.items())) for row in runtime_rows},
        key=lambda row: dict(row)["solver"],
    )
    runtime_observations = [dict(row) for row in unique_runtimes]
    if {row["solver"] for row in runtime_observations} != {
        "CalculiX",
        "OpenSees",
        "independent_preflight",
    }:
        _fail("same_operator_runtime_observation_set_invalid")

    historical_execution_binding_hash = _hash_bytes(
        _canonical_bytes(
            {
                "external_execution_source_commit_sha": historical_source_commit,
                "families": [
                    {
                        "family_id": row["family_id"],
                        "historical_package_binding": row[
                            "historical_package_binding"
                        ],
                        "results": row["results"],
                    }
                    for row in family_rows
                ],
                "runtime_assets": RUNTIME_ASSETS,
            }
        )
    )
    current_product_replay_binding_hash = _hash_bytes(
        _canonical_bytes(
            {
                "source_commit_sha": source_commit,
                "families": [
                    {
                        "family_id": row["family_id"],
                        "package_binding": row["package_binding"],
                        "technical_receipt": row["technical_receipt"],
                        "case_ids": row["case_ids"],
                        "current_product_replay_pass": row[
                            "current_product_replay_pass"
                        ],
                    }
                    for row in family_rows
                ],
                "historical_execution_binding_hash": (
                    historical_execution_binding_hash
                ),
            }
        )
    )
    execution_binding_hash = _hash_bytes(
        _canonical_bytes(
            {
                "historical_execution_binding_hash": (
                    historical_execution_binding_hash
                ),
                "current_product_replay_binding_hash": (
                    current_product_replay_binding_hash
                ),
                "execution_mode": "current_product_replay_only",
                "external_execution_reused": True,
                "fresh_current_source_external_execution": False,
            }
        )
    )
    engine_invoked_count = sum(
        result["external_engine_invoked"]
        for family in family_rows
        for result in family["results"]
    )
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit,
        "external_execution_source_commit_sha": historical_source_commit,
        "execution_binding_hash": execution_binding_hash,
        "historical_execution_binding_hash": historical_execution_binding_hash,
        "current_product_replay_binding_hash": (
            current_product_replay_binding_hash
        ),
        "execution_window": {
            "started_at": min(timestamps).isoformat(),
            "completed_at": max(timestamps).isoformat(),
        },
        "operator_context": {
            "operator_class": "same_operator_local_standalone",
            "execution_environment": "local_pinned_venv_and_extracted_debs",
            "container_isolated": False,
            "independently_operated": False,
        },
        "runtime_assets": [dict(row) for row in RUNTIME_ASSETS],
        "runtime_observations": runtime_observations,
        "replay_provenance": {
            "execution_mode": "current_product_replay_only",
            "external_runtime_executed_in_this_generation": False,
            "external_execution_reused": True,
            "historical_execution_input_bytes_attached": True,
            "historical_execution_input_binding_pass": True,
            "metric_semantics_match": True,
            "current_product_replay_generated_at": replay_generated_at,
            "current_product_replay_pass": True,
            "reuse_reason": reuse_reason.strip(),
        },
        "families": family_rows,
        "summary": {
            "family_count": len(family_rows),
            "case_count": sum(len(row["case_ids"]) for row in family_rows),
            "technical_pass_count": sum(len(row["case_ids"]) for row in family_rows),
            "external_engine_invoked_case_count": engine_invoked_count,
        },
        "technical_contract_pass": True,
        "claims": {
            "current_source_package_bytes_authenticated": True,
            "raw_external_results_attached": True,
            "runtime_asset_hashes_recorded": True,
            "runtime_asset_bytes_attached": False,
            "same_operator_local_execution": True,
            "actual_external_solver_execution": True,
            "historical_execution_input_bytes_attached": True,
            "raw_execution_binding_pass": True,
            "metric_semantics_match": True,
            "current_product_replay_pass": True,
            "external_runtime_executed_in_this_generation": False,
            "external_execution_reused": True,
            "fresh_current_source_external_execution": False,
            "container_isolated_reproduction": False,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "formal_promotion_receipt_attached": False,
            "verification_matrix_credit": False,
            "verification_level_2": False,
            "design_authority": False,
            "commercial_equivalence": False,
            "release_readiness": False,
        },
        "blockers": [
            "external_runtime_current_source_rerun_missing",
            "container_isolation_not_attested",
            "independent_operator_attestation_missing",
            "product_legal_license_approval_missing",
            "formal_level2_promotion_receipt_missing",
        ],
        "claim_boundary": (
            "This repository-local replay receipt preserves the historical package "
            "input bytes and sixteen raw result bytes, then compares them with product "
            "results regenerated from the current source. The external runtime was not "
            "executed during this generation, so every row is replay-only and not fresh. "
            "It records historical same-operator OpenSees and CalculiX execution only. "
            "Runtime asset hashes are recorded but the wheel and DEB bytes are not "
            "attached. No container attestation, independent operator identity, legal "
            "approval, formal promotion decision, Verification Level 2, design "
            "authority, commercial equivalence, or release readiness is granted."
        ),
        "artifact_hash": ZERO_HASH,
    }
    receipt["artifact_hash"] = _artifact_hash(receipt)
    return receipt, child_receipts


def _load_schema(repo_root: Path) -> dict[str, Any]:
    return _load_json(
        repo_root / SCHEMA_PATH, "same_operator_execution_schema_unreadable"
    )


def validate_receipt(receipt: dict[str, Any], *, repo_root: Path = ROOT) -> None:
    schema = _load_schema(repo_root)
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).validate(receipt)
    except (SchemaError, ValidationError) as exc:
        raise SameOperatorSupplementalExecutionError(
            "same_operator_execution_receipt_schema_invalid"
        ) from exc
    if receipt.get("artifact_hash") != _artifact_hash(receipt):
        _fail("same_operator_execution_receipt_artifact_hash_invalid")
    summary = receipt.get("summary")
    families = receipt.get("families")
    claims = receipt.get("claims")
    replay = receipt.get("replay_provenance")
    if (
        not isinstance(summary, dict)
        or not isinstance(families, list)
        or [row.get("family_id") for row in families]
        != [family.family_id for family in FAMILIES]
        or summary.get("family_count") != 5
        or summary.get("case_count") != 16
        or summary.get("technical_pass_count") != 16
        or summary.get("external_engine_invoked_case_count") != 15
        or receipt.get("technical_contract_pass") is not True
        or receipt.get("runtime_assets") != list(RUNTIME_ASSETS)
        or not isinstance(claims, dict)
        or not isinstance(replay, dict)
        or replay.get("execution_mode") != "current_product_replay_only"
        or replay.get("external_runtime_executed_in_this_generation") is not False
        or replay.get("external_execution_reused") is not True
        or replay.get("historical_execution_input_bytes_attached") is not True
        or replay.get("historical_execution_input_binding_pass") is not True
        or replay.get("metric_semantics_match") is not True
        or replay.get("current_product_replay_pass") is not True
        or not isinstance(replay.get("reuse_reason"), str)
        or not replay["reuse_reason"].strip()
        or claims.get("historical_execution_input_bytes_attached") is not True
        or claims.get("raw_execution_binding_pass") is not True
        or claims.get("metric_semantics_match") is not True
        or claims.get("current_product_replay_pass") is not True
        or claims.get("external_runtime_executed_in_this_generation") is not False
        or claims.get("external_execution_reused") is not True
        or claims.get("fresh_current_source_external_execution") is not False
        or claims.get("same_operator_local_execution") is not True
        or claims.get("actual_external_solver_execution") is not True
        or claims.get("container_isolated_reproduction") is not False
        or claims.get("independent_operator_attested") is not False
        or claims.get("legal_use_approved") is not False
        or claims.get("verification_matrix_credit") is not False
        or claims.get("verification_level_2") is not False
        or claims.get("design_authority") is not False
        or claims.get("commercial_equivalence") is not False
        or claims.get("release_readiness") is not False
        or any(
            row.get("raw_execution_binding_pass") is not True
            or row.get("metric_semantics_match") is not True
            or row.get("current_product_replay_pass") is not True
            or row.get("external_runtime_executed_in_this_generation") is not False
            or row.get("external_execution_reused") is not True
            or row.get("fresh_current_source_external_execution") is not False
            for row in families
        )
    ):
        _fail("same_operator_execution_receipt_contract_invalid")
    replay_timestamp = _parse_timestamp(
        replay["current_product_replay_generated_at"],
        "same_operator_replay_timestamp_invalid",
    )
    completed_timestamp = _parse_timestamp(
        receipt["execution_window"]["completed_at"],
        "same_operator_execution_window_invalid",
    )
    if replay_timestamp < completed_timestamp:
        _fail("same_operator_replay_precedes_external_execution")


def _expected_file_set(out_root: Path) -> set[str]:
    files = {RECEIPT_NAME}
    for family in FAMILIES:
        files.add(f"receipts/{family.receipt_name}")
        files.update(
            f"results/{family.family_id}/{case_id}.json"
            for case_id in family.case_ids
        )
        historical_root = (
            out_root / HISTORICAL_PACKAGE_DIRNAME / family.family_id
        )
        _manifest, historical_files = _validate_package_snapshot(
            package_root=historical_root, family=family
        )
        files.add(
            f"{HISTORICAL_PACKAGE_DIRNAME}/{family.family_id}/"
            f"{family.package_module.MANIFEST_NAME}"
        )
        files.update(
            f"{HISTORICAL_PACKAGE_DIRNAME}/{family.family_id}/{row['path']}"
            for row in historical_files
        )
    return files


def validate_bundle(
    *, repo_root: Path = ROOT, out_dir: Path = DEFAULT_OUT_DIR
) -> dict[str, Any]:
    out_root = _resolved_non_symlink_root(
        repo_root,
        out_dir,
        code="same_operator_execution_bundle_root_symlink",
    )
    stored = _load_json(
        out_root / RECEIPT_NAME, "same_operator_execution_receipt_unreadable"
    )
    validate_receipt(stored, repo_root=repo_root)
    if any(path.is_symlink() for path in out_root.rglob("*")):
        _fail("same_operator_execution_bundle_symlink")
    actual_files = {
        path.relative_to(out_root).as_posix()
        for path in out_root.rglob("*")
        if path.is_file()
    }
    if actual_files != _expected_file_set(out_root):
        _fail("same_operator_execution_bundle_file_set_invalid")
    replay = stored["replay_provenance"]
    rebuilt, _children = _build_receipt_from_existing(
        repo_root=repo_root,
        out_root=out_root,
        replay_generated_at=replay["current_product_replay_generated_at"],
        reuse_reason=replay["reuse_reason"],
    )
    if stored != rebuilt:
        _fail("same_operator_execution_receipt_replay_mismatch")
    return stored


def build_bundle(
    *,
    input_root: Path,
    runtime_assets_dir: Path,
    repo_root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT_DIR,
    reuse_reason: str = DEFAULT_REUSE_REASON,
) -> dict[str, Any]:
    source_root = input_root.resolve()
    asset_root = runtime_assets_dir.resolve()
    _validate_runtime_assets(asset_root)
    out_root = _resolved_non_symlink_root(
        repo_root,
        out_dir,
        code="same_operator_execution_bundle_root_symlink",
    )
    (out_root / "receipts").mkdir(parents=True, exist_ok=True)

    for family in FAMILIES:
        source = _validate_input_results(source_root, family)
        target = out_root / "results" / family.family_id
        target.mkdir(parents=True, exist_ok=True)
        for case_id in family.case_ids:
            (target / f"{case_id}.json").write_bytes(
                (source / f"{case_id}.json").read_bytes()
            )
        child = _build_child_receipt(
            repo_root=repo_root,
            family=family,
            results_dir=target,
        )
        (out_root / "receipts" / family.receipt_name).write_bytes(
            _json_bytes(child)
        )

    capture_historical_execution_inputs(
        repo_root=repo_root, out_dir=out_root
    )

    receipt, _children = _build_receipt_from_existing(
        repo_root=repo_root,
        out_root=out_root,
        replay_generated_at=datetime.now(timezone.utc).isoformat(),
        reuse_reason=reuse_reason,
    )
    validate_receipt(receipt, repo_root=repo_root)
    (out_root / RECEIPT_NAME).write_bytes(_json_bytes(receipt))
    return validate_bundle(repo_root=repo_root, out_dir=out_root)


def refresh_product_replay(
    *,
    repo_root: Path = ROOT,
    out_dir: Path = DEFAULT_OUT_DIR,
    reuse_reason: str = DEFAULT_REUSE_REASON,
) -> dict[str, Any]:
    out_root = _resolved_non_symlink_root(
        repo_root,
        out_dir,
        code="same_operator_execution_bundle_root_symlink",
    )
    for family in FAMILIES:
        child = _build_child_receipt(
            repo_root=repo_root,
            family=family,
            results_dir=out_root / "results" / family.family_id,
        )
        if _child_fresh_external_execution(
            family=family, child_receipt=child
        ):
            _fail(f"same_operator_replay_child_freshness_invalid:{family.family_id}")
        receipt_path = out_root / "receipts" / family.receipt_name
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(_json_bytes(child))
    receipt, _children = _build_receipt_from_existing(
        repo_root=repo_root,
        out_root=out_root,
        replay_generated_at=datetime.now(timezone.utc).isoformat(),
        reuse_reason=reuse_reason,
    )
    validate_receipt(receipt, repo_root=repo_root)
    (out_root / RECEIPT_NAME).write_bytes(_json_bytes(receipt))
    return validate_bundle(repo_root=repo_root, out_dir=out_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--runtime-assets-dir", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--reuse-reason", default=DEFAULT_REUSE_REASON)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--capture-historical-inputs", action="store_true")
    mode.add_argument("--refresh-product-replay", action="store_true")
    args = parser.parse_args()
    try:
        if args.capture_historical_inputs:
            if args.input_root is not None or args.runtime_assets_dir is not None:
                _fail("same_operator_capture_arguments_invalid")
            capture_historical_execution_inputs(out_dir=args.out_dir)
            print("bounded planar historical execution inputs: attached")
            return 0
        if args.refresh_product_replay:
            if args.input_root is not None or args.runtime_assets_dir is not None:
                _fail("same_operator_refresh_arguments_invalid")
            receipt = refresh_product_replay(
                out_dir=args.out_dir,
                reuse_reason=args.reuse_reason,
            )
        elif args.check:
            if (
                args.input_root is not None
                or args.runtime_assets_dir is not None
                or args.reuse_reason != DEFAULT_REUSE_REASON
            ):
                _fail("same_operator_check_arguments_invalid")
            receipt = validate_bundle(out_dir=args.out_dir)
        else:
            if args.input_root is None or args.runtime_assets_dir is None:
                _fail("same_operator_build_arguments_missing")
            receipt = build_bundle(
                input_root=args.input_root,
                runtime_assets_dir=args.runtime_assets_dir,
                out_dir=args.out_dir,
                reuse_reason=args.reuse_reason,
            )
    except SameOperatorSupplementalExecutionError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    print(
        "bounded planar same-operator supplemental execution: "
        f"technical={receipt['summary']['technical_pass_count']}/"
        f"{receipt['summary']['case_count']} | mode=current_product_replay_only "
        "| matrix_credit=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
