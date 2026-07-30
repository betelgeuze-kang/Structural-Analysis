#!/usr/bin/env python3
"""Run the pinned OpenSees/CalculiX V&V candidate in an isolated container.

The runtime consumes pre-downloaded, checksum-pinned assets. It never downloads a
solver package. The repository must be mounted read-only, with only the selected
output directory over-mounted read-write. Runtime networking must be disabled.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_VERSION = "structural-analysis-external-vv-clean-runner-receipt.v1"
BASE_IMAGE = (
    "docker.io/library/python:3.11-slim-bookworm@"
    "sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba"
)
SCHEMA_RELATIVE_PATH = Path(
    "src/structural_analysis/schemas/external_vv_clean_runner_receipt_v1.schema.json"
)
DOCKERFILE_RELATIVE_PATH = Path(
    "benchmarks/clean-runners/opensees-calculix/Dockerfile"
)
WRAPPER_RELATIVE_PATH = Path("scripts/run_external_vv_clean_runner.sh")
CODE_RECEIPT_RELATIVE_PATH = Path("external_code_to_code_receipt.json")
MODAL_RECEIPT_RELATIVE_PATH = Path("external_modal_buckling_receipt.json")
MODE_VECTOR_RELATIVE_DIR = Path("mode_vectors")
SUMMARY_RELATIVE_PATH = Path("clean_runner_receipt.json")
HOST_CODE_REFERENCE_RELATIVE_PATH = Path(
    "implementation/phase1/release_evidence/productization/"
    "external_code_to_code_technical_execution_receipt.json"
)
HOST_MODAL_REFERENCE_RELATIVE_PATH = Path(
    "implementation/phase1/release_evidence/productization/"
    "external_modal_buckling_technical_execution_receipt.json"
)
CROSS_ENVIRONMENT_ABSOLUTE_TOLERANCE = 1.0e-12
CROSS_ENVIRONMENT_RELATIVE_TOLERANCE = 1.0e-12

ASSET_POLICY = {
    "openseespy-3.7.1.2-py3-none-any.whl": (
        "1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65"
    ),
    "openseespylinux-3.7.1.2-py3-none-any.whl": (
        "63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a"
    ),
    "calculix-ccx_2.17-3_amd64.deb": (
        "3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e"
    ),
    "libarpack2_3.8.0-1_amd64.deb": (
        "07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a"
    ),
    "libspooles2.2_2.2-14_amd64.deb": (
        "34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917"
    ),
}

BLOCKERS_REMAINING = (
    "independent_operator_attestation_missing",
    "product_legal_license_approval_missing",
    "external_runtime_redistribution_approval_missing",
    "public_corotational_material_nonlinear_external_family_missing",
    "verification_hierarchy_operator_manifest_missing",
    "verification_level_2_not_achieved",
    "release_readiness_not_established",
)
SEMANTIC_HASH_MISMATCH_BLOCKER = (
    "exact_cross_environment_buckling_semantic_hash_mismatch_within_tolerance"
)
REUSED_EXECUTION_BLOCKER = "external_runtime_current_source_rerun_missing"
CROSS_ENVIRONMENT_PARITY_BLOCKER = (
    "current_source_container_cross_environment_parity_missing"
)

CLAIM_BOUNDARY = (
    "This receipt proves a same-operator, container-isolated reproduction of the "
    "narrow non-promoting OpenSees/CalculiX technical comparisons, including the "
    "public one-bay corotational portal's four-step elastic-state load path and "
    "the bounded planar rigid-offset, RZ-release, uniform-member-load path, plus "
    "a bounded OpenSees 3D elastic Timoshenko cantilever under combined transverse "
    "forces and torsion, and the six-member CalculiX spatial-truss comparison. The "
    "source mount was read-only, runtime networking had no default route, and every "
    "external asset matched its pinned SHA-256 before execution. The source bytes "
    "are checksum-bound over the recorded base commit; this is not an independent "
    "operator attestation, material-nonlinear or cyclic family validation, legal "
    "approval, Verification Level 2 promotion, broad structural-family validation, "
    "commercial equivalence, design authority, or release readiness."
)
REUSED_CLAIM_BOUNDARY = (
    "This receipt preserves an earlier same-operator, container-isolated actual "
    "OpenSees/CalculiX execution and binds current candidate source bytes through "
    "current-product-only replays against the checksum-bound stored external "
    "values. The current generation did not execute either external runtime, so "
    "same-operator container reproduction of the current source is not claimed "
    "and external_runtime_current_source_rerun_missing remains explicit. The "
    "recorded isolation and runtime inventory describe the earlier execution. "
    "This remains a narrow non-promoting technical candidate, not an independent "
    "operator attestation, material-nonlinear or cyclic family validation, legal "
    "approval, Verification Level 2 promotion, broad structural-family validation, "
    "commercial equivalence, design authority, or release readiness."
)


class CleanRunnerError(RuntimeError):
    """Raised when an isolation, asset, execution, or receipt invariant fails."""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _artifact_hash(payload: dict[str, Any]) -> str:
    material = dict(payload)
    material.pop("artifact_hash", None)
    return "sha256:" + hashlib.sha256(_canonical_bytes(material)).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CleanRunnerError(f"json_object_required:{path}")
    return payload


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        raise CleanRunnerError(
            "command_failed:"
            + command[0]
            + f":return_code={completed.returncode}:stderr={completed.stderr[-2000:]}"
        )


def _source_mount_is_read_only(repo_root: Path) -> bool:
    return bool(os.statvfs(repo_root).f_flag & os.ST_RDONLY)


def _network_default_route_present() -> bool:
    route_path = Path("/proc/net/route")
    if not route_path.is_file():
        return True
    for line in route_path.read_text(encoding="utf-8").splitlines()[1:]:
        columns = line.split()
        if len(columns) >= 2 and columns[1] == "00000000":
            return True
    return False


def _validate_assets(asset_dir: Path) -> list[Path]:
    actual_names = {path.name for path in asset_dir.iterdir() if path.is_file()}
    missing = sorted(set(ASSET_POLICY) - actual_names)
    if missing:
        raise CleanRunnerError("external_assets_missing:" + ",".join(missing))
    assets = [asset_dir / name for name in sorted(ASSET_POLICY)]
    mismatches = [
        path.name
        for path in assets
        if _file_hash(path) != "sha256:" + ASSET_POLICY[path.name]
    ]
    if mismatches:
        raise CleanRunnerError(
            "external_asset_checksum_mismatch:" + ",".join(mismatches)
        )
    return assets


def _relative_to_repo(path: Path, repo_root: Path) -> Path:
    try:
        return path.relative_to(repo_root)
    except ValueError as exc:
        raise CleanRunnerError("output_directory_must_be_inside_repo") from exc


def _runtime_package_versions() -> dict[str, str]:
    names = (
        "numpy",
        "scipy",
        "jsonschema",
        "attrs",
        "jsonschema-specifications",
        "referencing",
        "rpds-py",
        "typing-extensions",
    )
    return {name: version(name) for name in names}


def _debian_package_versions() -> dict[str, str]:
    names = (
        "git",
        "libblas3",
        "libgfortran5",
        "liblapack3",
        "libopenmpi3",
        "libquadmath0",
    )
    completed = subprocess.run(
        ["dpkg-query", "--show", "--showformat=${Package}=${Version}\n", *names],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CleanRunnerError("debian_package_inventory_failed")
    return dict(
        line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line
    )


def _case_summary(receipt: dict[str, Any]) -> list[dict[str, object]]:
    return [
        {
            "case_id": str(row["case_id"]),
            "contract_pass": bool(row["contract_pass"]),
            "metric_count": len(row["metrics"]),
        }
        for row in receipt["comparisons"]
    ]


def _metric_scalar_map(receipt: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for case in receipt["comparisons"]:
        case_id = str(case["case_id"])
        for metric in case["metrics"]:
            quantity = str(metric["quantity"])
            for field in ("product_value", "reference_value", "observed_value"):
                if field in metric:
                    values[f"{case_id}/{quantity}/{field}"] = float(metric[field])
    return values


def _cross_environment_parity(
    *,
    repo_root: Path,
    code_receipt: dict[str, Any],
    modal_receipt: dict[str, Any],
    host_code_reference: dict[str, Any],
    host_modal_reference: dict[str, Any],
    require_contract_pass: bool = True,
) -> dict[str, Any]:
    source_set_match = bool(
        code_receipt["internal_source"]["source_set_hash"]
        != host_code_reference["internal_source"]["source_set_hash"]
        or modal_receipt["internal_source"]["source_set_hash"]
        != host_modal_reference["internal_source"]["source_set_hash"]
    ) is False
    if require_contract_pass and not source_set_match:
        raise CleanRunnerError("cross_environment_source_set_mismatch")
    container_values = {
        **{
            f"code_to_code/{key}": value
            for key, value in _metric_scalar_map(code_receipt).items()
        },
        **{
            f"modal_buckling/{key}": value
            for key, value in _metric_scalar_map(modal_receipt).items()
        },
    }
    host_values = {
        **{
            f"code_to_code/{key}": value
            for key, value in _metric_scalar_map(host_code_reference).items()
        },
        **{
            f"modal_buckling/{key}": value
            for key, value in _metric_scalar_map(host_modal_reference).items()
        },
    }
    container_keys = set(container_values)
    host_keys = set(host_values)
    metric_set_match = container_keys == host_keys
    if require_contract_pass and not metric_set_match:
        raise CleanRunnerError("cross_environment_metric_set_mismatch")
    shared_keys = sorted(container_keys & host_keys)
    container_only_metric_keys = sorted(container_keys - host_keys)
    host_only_metric_keys = sorted(host_keys - container_keys)
    absolute_deltas: list[float] = []
    relative_deltas: list[float] = []
    contract_rows: list[bool] = []
    for key in shared_keys:
        container_value = container_values[key]
        host_value = host_values[key]
        delta = abs(container_value - host_value)
        scale = max(abs(container_value), abs(host_value), 1.0)
        absolute_deltas.append(delta)
        relative_deltas.append(delta / scale)
        contract_rows.append(
            delta
            <= CROSS_ENVIRONMENT_ABSOLUTE_TOLERANCE
            + CROSS_ENVIRONMENT_RELATIVE_TOLERANCE * scale
        )

    container_evidence = modal_receipt["product_evidence"]
    host_evidence = host_modal_reference["product_evidence"]
    semantic_hash_matches = {
        key: container_evidence[key] == host_evidence[key]
        for key in (
            "modal_model_hash",
            "modal_semantic_result_hash",
            "buckling_model_hash",
            "buckling_semantic_result_hash",
        )
    }
    model_hashes_match = bool(
        semantic_hash_matches["modal_model_hash"]
        and semantic_hash_matches["buckling_model_hash"]
    )
    numerical_contract_pass = bool(
        source_set_match
        and metric_set_match
        and all(contract_rows)
        and model_hashes_match
    )
    if require_contract_pass and not numerical_contract_pass:
        raise CleanRunnerError("cross_environment_numerical_parity_failed")
    return {
        "host_reference_receipts": {
            "code_to_code": {
                "path": HOST_CODE_REFERENCE_RELATIVE_PATH.as_posix(),
                "file_sha256": _file_hash(
                    repo_root / HOST_CODE_REFERENCE_RELATIVE_PATH
                ),
                "artifact_hash": host_code_reference["artifact_hash"],
            },
            "modal_buckling": {
                "path": HOST_MODAL_REFERENCE_RELATIVE_PATH.as_posix(),
                "file_sha256": _file_hash(
                    repo_root / HOST_MODAL_REFERENCE_RELATIVE_PATH
                ),
                "artifact_hash": host_modal_reference["artifact_hash"],
            },
        },
        "absolute_tolerance": CROSS_ENVIRONMENT_ABSOLUTE_TOLERANCE,
        "relative_tolerance": CROSS_ENVIRONMENT_RELATIVE_TOLERANCE,
        "source_set_match": source_set_match,
        "metric_set_match": metric_set_match,
        "scalar_comparison_count": len(shared_keys),
        "container_scalar_count": len(container_values),
        "host_scalar_count": len(host_values),
        "container_only_metric_keys": container_only_metric_keys,
        "host_only_metric_keys": host_only_metric_keys,
        "nonzero_delta_count": sum(delta > 0.0 for delta in absolute_deltas),
        "maximum_absolute_delta": max(absolute_deltas, default=0.0),
        "maximum_relative_delta": max(relative_deltas, default=0.0),
        "semantic_hash_matches": semantic_hash_matches,
        "exact_semantic_hash_parity": all(semantic_hash_matches.values()),
        "numerical_contract_pass": numerical_contract_pass,
    }


def _validate_product_receipt(
    receipt: dict[str, Any], *, expected_fresh_execution: bool = True
) -> None:
    if receipt.get("technical_contract_pass") is not True:
        raise CleanRunnerError("product_receipt_technical_contract_failed")
    if receipt.get("verification_hierarchy_credit") is not False:
        raise CleanRunnerError("product_receipt_hierarchy_promotion_forbidden")
    if receipt.get("claims", {}).get("verification_level_2") is not False:
        raise CleanRunnerError("product_receipt_level2_promotion_forbidden")
    replay = receipt.get("replay_provenance", {})
    fresh_execution = (
        replay.get("external_runtime_executed_in_this_generation") is True
        and replay.get("external_execution_reused") is False
    )
    reused_execution = (
        replay.get("external_runtime_executed_in_this_generation") is False
        and replay.get("external_execution_reused") is True
        and isinstance(replay.get("reuse_reason"), str)
        and bool(replay["reuse_reason"].strip())
    )
    if not fresh_execution and not reused_execution:
        raise CleanRunnerError("product_receipt_replay_state_invalid")
    if expected_fresh_execution and not fresh_execution:
        raise CleanRunnerError("product_receipt_fresh_execution_required")
    if not all(row.get("contract_pass") is True for row in receipt["comparisons"]):
        raise CleanRunnerError("product_receipt_case_failed")


def _receipt_fresh_execution(receipt: dict[str, Any]) -> bool:
    replay = receipt["replay_provenance"]
    return bool(
        replay["external_runtime_executed_in_this_generation"] is True
        and replay["external_execution_reused"] is False
    )


def _summary_blockers(
    *,
    fresh_execution: bool,
    exact_semantic_hash_parity: bool,
    cross_environment_pass: bool,
) -> list[str]:
    blockers = list(BLOCKERS_REMAINING)
    if not exact_semantic_hash_parity:
        blockers.insert(-1, SEMANTIC_HASH_MISMATCH_BLOCKER)
    if not cross_environment_pass:
        blockers.insert(-1, CROSS_ENVIRONMENT_PARITY_BLOCKER)
    if not fresh_execution:
        blockers.append(REUSED_EXECUTION_BLOCKER)
    return blockers


def _summary_claims(
    *,
    technical_pass: bool,
    fresh_execution: bool,
    cross_environment_pass: bool,
) -> dict[str, bool]:
    return {
        "same_operator_container_isolated_reproduction": (
            technical_pass and fresh_execution
        ),
        "current_candidate_source_bytes_checksum_bound": technical_pass,
        "actual_external_solver_execution": technical_pass,
        "cross_environment_numerical_parity": cross_environment_pass,
        "independent_operator_attestation": False,
        "product_legal_license_approval": False,
        "external_runtime_redistribution_approval": False,
        "verification_level_2": False,
        "commercial_equivalence": False,
        "design_authority": False,
        "release_readiness": False,
    }


def _summary_claim_boundary(*, fresh_execution: bool) -> str:
    return CLAIM_BOUNDARY if fresh_execution else REUSED_CLAIM_BOUNDARY


def _product_receipt_descriptor(
    *,
    repo_root: Path,
    path: Path,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "file_sha256": _file_hash(path),
        "artifact_hash": receipt["artifact_hash"],
        "source_set_hash": receipt["internal_source"]["source_set_hash"],
        "technical_contract_pass": receipt["technical_contract_pass"],
        "fresh_external_runtime_execution": _receipt_fresh_execution(receipt),
        "cases": _case_summary(receipt),
    }


def _build_summary(
    *,
    repo_root: Path,
    output_dir: Path,
    assets: list[Path],
    code_receipt: dict[str, Any],
    modal_receipt: dict[str, Any],
    host_code_reference: dict[str, Any],
    host_modal_reference: dict[str, Any],
    derived_image_id: str,
    source_read_only: bool,
    default_route_present: bool,
) -> dict[str, Any]:
    code_path = output_dir / CODE_RECEIPT_RELATIVE_PATH
    modal_path = output_dir / MODAL_RECEIPT_RELATIVE_PATH
    source_commits = {
        str(code_receipt["source_commit_sha"]),
        str(modal_receipt["source_commit_sha"]),
    }
    if len(source_commits) != 1:
        raise CleanRunnerError("product_receipt_source_commit_mismatch")
    isolation_pass = source_read_only and not default_route_present
    technical_pass = bool(
        isolation_pass
        and code_receipt["technical_contract_pass"] is True
        and modal_receipt["technical_contract_pass"] is True
    )
    fresh_execution = bool(
        _receipt_fresh_execution(code_receipt)
        and _receipt_fresh_execution(modal_receipt)
    )
    cross_environment = _cross_environment_parity(
        repo_root=repo_root,
        code_receipt=code_receipt,
        modal_receipt=modal_receipt,
        host_code_reference=host_code_reference,
        host_modal_reference=host_modal_reference,
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commits.pop(),
        "status": "partial" if technical_pass else "blocked",
        "truth_class": "container_isolated_external_vv_technical_candidate",
        "runner": {
            "base_image": BASE_IMAGE,
            "derived_image_id": derived_image_id,
            "runner_source_sha256": _file_hash(Path(__file__)),
            "schema_sha256": _file_hash(repo_root / SCHEMA_RELATIVE_PATH),
            "dockerfile_sha256": _file_hash(
                repo_root / DOCKERFILE_RELATIVE_PATH
            ),
            "wrapper_sha256": _file_hash(repo_root / WRAPPER_RELATIVE_PATH),
            "system": platform.system(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable_sha256": _file_hash(Path(sys.executable)),
            "python_packages": _runtime_package_versions(),
            "debian_packages": _debian_package_versions(),
        },
        "isolation": {
            "repository_mount_read_only": source_read_only,
            "runtime_default_network_route_present": default_route_present,
            "designated_output_mount_writable": os.access(output_dir, os.W_OK),
            "isolation_contract_pass": isolation_pass,
        },
        "external_assets": [
            {
                "filename": path.name,
                "sha256": _file_hash(path),
                "bundled_in_repository": False,
            }
            for path in assets
        ],
        "product_receipts": {
            "code_to_code": _product_receipt_descriptor(
                repo_root=repo_root,
                path=code_path,
                receipt=code_receipt,
            ),
            "modal_buckling": _product_receipt_descriptor(
                repo_root=repo_root,
                path=modal_path,
                receipt=modal_receipt,
            ),
        },
        "cross_environment_parity": cross_environment,
        "technical_contract_pass": technical_pass,
        "claims": _summary_claims(
            technical_pass=technical_pass,
            fresh_execution=fresh_execution,
            cross_environment_pass=cross_environment[
                "numerical_contract_pass"
            ],
        ),
        "blockers_remaining": _summary_blockers(
            fresh_execution=fresh_execution,
            exact_semantic_hash_parity=cross_environment[
                "exact_semantic_hash_parity"
            ],
            cross_environment_pass=cross_environment[
                "numerical_contract_pass"
            ],
        ),
        "claim_boundary": _summary_claim_boundary(
            fresh_execution=fresh_execution,
        ),
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def validate_summary(payload: dict[str, Any], *, repo_root: Path) -> None:
    schema = _read_json(repo_root / SCHEMA_RELATIVE_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["artifact_hash"] != _artifact_hash(payload):
        raise CleanRunnerError("summary_artifact_hash_invalid")
    runner = payload["runner"]
    expected_runner_hashes = {
        "runner_source_sha256": _file_hash(Path(__file__)),
        "schema_sha256": _file_hash(repo_root / SCHEMA_RELATIVE_PATH),
        "dockerfile_sha256": _file_hash(repo_root / DOCKERFILE_RELATIVE_PATH),
        "wrapper_sha256": _file_hash(repo_root / WRAPPER_RELATIVE_PATH),
    }
    if any(runner[name] != value for name, value in expected_runner_hashes.items()):
        raise CleanRunnerError("summary_runner_source_hash_invalid")

    child_receipts = {
        name: _read_json(repo_root / descriptor["path"])
        for name, descriptor in payload["product_receipts"].items()
    }
    for name, receipt in child_receipts.items():
        descriptor = payload["product_receipts"][name]
        path = repo_root / descriptor["path"]
        if (
            descriptor["file_sha256"] != _file_hash(path)
            or descriptor["artifact_hash"] != receipt["artifact_hash"]
            or descriptor["source_set_hash"]
            != receipt["internal_source"]["source_set_hash"]
        ):
            raise CleanRunnerError("summary_child_receipt_descriptor_invalid")
        _validate_product_receipt(receipt, expected_fresh_execution=False)
        if descriptor["fresh_external_runtime_execution"] is not (
            _receipt_fresh_execution(receipt)
        ):
            raise CleanRunnerError("summary_child_replay_descriptor_invalid")
    fresh_execution = all(
        descriptor["fresh_external_runtime_execution"] is True
        for descriptor in payload["product_receipts"].values()
    )
    if payload["claim_boundary"] != _summary_claim_boundary(
        fresh_execution=fresh_execution
    ):
        raise CleanRunnerError("summary_claim_boundary_invalid")
    if payload["blockers_remaining"] != _summary_blockers(
        fresh_execution=fresh_execution,
        exact_semantic_hash_parity=payload["cross_environment_parity"][
            "exact_semantic_hash_parity"
        ],
        cross_environment_pass=payload["cross_environment_parity"][
            "numerical_contract_pass"
        ],
    ):
        raise CleanRunnerError("summary_blockers_invalid")
    if {
        str(receipt["source_commit_sha"])
        for receipt in child_receipts.values()
    } != {str(payload["source_commit_sha"])}:
        raise CleanRunnerError("summary_source_commit_invalid")

    expected_parity = _cross_environment_parity(
        repo_root=repo_root,
        code_receipt=child_receipts["code_to_code"],
        modal_receipt=child_receipts["modal_buckling"],
        host_code_reference=_read_json(
            repo_root / HOST_CODE_REFERENCE_RELATIVE_PATH
        ),
        host_modal_reference=_read_json(
            repo_root / HOST_MODAL_REFERENCE_RELATIVE_PATH
        ),
        require_contract_pass=False,
    )
    if payload["cross_environment_parity"] != expected_parity:
        raise CleanRunnerError("summary_cross_environment_parity_invalid")
    expected_claims = _summary_claims(
        technical_pass=payload["technical_contract_pass"],
        fresh_execution=fresh_execution,
        cross_environment_pass=expected_parity["numerical_contract_pass"],
    )
    if payload["claims"] != expected_claims:
        raise CleanRunnerError("summary_claims_invalid")
    if payload["status"] != (
        "partial" if payload["technical_contract_pass"] else "blocked"
    ):
        raise CleanRunnerError("summary_status_invalid")


def refresh_product_replay_summary(
    *,
    repo_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    summary_path = output_dir / SUMMARY_RELATIVE_PATH
    refreshed = deepcopy(_read_json(summary_path))
    code_path = output_dir / CODE_RECEIPT_RELATIVE_PATH
    modal_path = output_dir / MODAL_RECEIPT_RELATIVE_PATH
    code_receipt = _read_json(code_path)
    modal_receipt = _read_json(modal_path)
    _validate_product_receipt(code_receipt, expected_fresh_execution=False)
    _validate_product_receipt(modal_receipt, expected_fresh_execution=False)
    source_commits = {
        str(code_receipt["source_commit_sha"]),
        str(modal_receipt["source_commit_sha"]),
    }
    if len(source_commits) != 1:
        raise CleanRunnerError("product_receipt_source_commit_mismatch")

    cross_environment = _cross_environment_parity(
        repo_root=repo_root,
        code_receipt=code_receipt,
        modal_receipt=modal_receipt,
        host_code_reference=_read_json(
            repo_root / HOST_CODE_REFERENCE_RELATIVE_PATH
        ),
        host_modal_reference=_read_json(
            repo_root / HOST_MODAL_REFERENCE_RELATIVE_PATH
        ),
        require_contract_pass=False,
    )
    fresh_execution = bool(
        _receipt_fresh_execution(code_receipt)
        and _receipt_fresh_execution(modal_receipt)
    )
    technical_pass = bool(
        refreshed["isolation"]["isolation_contract_pass"] is True
        and code_receipt["technical_contract_pass"] is True
        and modal_receipt["technical_contract_pass"] is True
    )
    refreshed.update(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_commit_sha": source_commits.pop(),
            "status": "partial" if technical_pass else "blocked",
            "product_receipts": {
                "code_to_code": _product_receipt_descriptor(
                    repo_root=repo_root,
                    path=code_path,
                    receipt=code_receipt,
                ),
                "modal_buckling": _product_receipt_descriptor(
                    repo_root=repo_root,
                    path=modal_path,
                    receipt=modal_receipt,
                ),
            },
            "cross_environment_parity": cross_environment,
            "technical_contract_pass": technical_pass,
            "claims": _summary_claims(
                technical_pass=technical_pass,
                fresh_execution=fresh_execution,
                cross_environment_pass=cross_environment[
                    "numerical_contract_pass"
                ],
            ),
            "blockers_remaining": _summary_blockers(
                fresh_execution=fresh_execution,
                exact_semantic_hash_parity=cross_environment[
                    "exact_semantic_hash_parity"
                ],
                cross_environment_pass=cross_environment[
                    "numerical_contract_pass"
                ],
            ),
            "claim_boundary": _summary_claim_boundary(
                fresh_execution=fresh_execution,
            ),
        }
    )
    refreshed["runner"].update(
        {
            "runner_source_sha256": _file_hash(Path(__file__)),
            "schema_sha256": _file_hash(repo_root / SCHEMA_RELATIVE_PATH),
            "dockerfile_sha256": _file_hash(
                repo_root / DOCKERFILE_RELATIVE_PATH
            ),
            "wrapper_sha256": _file_hash(repo_root / WRAPPER_RELATIVE_PATH),
        }
    )
    refreshed["artifact_hash"] = _artifact_hash(refreshed)
    validate_summary(refreshed, repo_root=repo_root)
    return refreshed


def _write_summary(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--derived-image-id")
    parser.add_argument("--refresh-product-replay-summary", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    if not repo_root.is_dir() or not output_dir.is_dir():
        raise CleanRunnerError("runner_directory_missing")
    if args.refresh_product_replay_summary:
        summary = refresh_product_replay_summary(
            repo_root=repo_root,
            output_dir=output_dir,
        )
        _write_summary(output_dir / SUMMARY_RELATIVE_PATH, summary)
        print("external_vv_clean_runner_product_replay_summary_refreshed")
        return 0
    if args.asset_dir is None or args.derived_image_id is None:
        parser.error("--asset-dir and --derived-image-id are required")
    asset_dir = args.asset_dir.resolve()
    if not asset_dir.is_dir():
        raise CleanRunnerError("runner_directory_missing")
    output_relative = _relative_to_repo(output_dir, repo_root)
    source_read_only = _source_mount_is_read_only(repo_root)
    default_route_present = _network_default_route_present()
    if not source_read_only:
        raise CleanRunnerError("repository_mount_must_be_read_only")
    if default_route_present:
        raise CleanRunnerError("runtime_network_must_be_disabled")

    assets = _validate_assets(asset_dir)
    code_script = repo_root / "scripts/run_external_code_to_code_technical_receipt.py"
    modal_script = (
        repo_root / "scripts/run_external_modal_buckling_technical_receipt.py"
    )
    code_out = output_dir / CODE_RECEIPT_RELATIVE_PATH
    modal_out = output_dir / MODAL_RECEIPT_RELATIVE_PATH
    vector_relative = output_relative / MODE_VECTOR_RELATIVE_DIR

    with TemporaryDirectory(prefix="structural-analysis-clean-runner-") as temporary:
        scratch = Path(temporary)
        opensees_runtime = scratch / "opensees-runtime"
        calculix_root = scratch / "calculix-root"
        opensees_runtime.mkdir()
        calculix_root.mkdir()
        _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(opensees_runtime),
                str(asset_dir / "openseespy-3.7.1.2-py3-none-any.whl"),
                str(asset_dir / "openseespylinux-3.7.1.2-py3-none-any.whl"),
            ],
            cwd=scratch,
        )
        for name in (
            "calculix-ccx_2.17-3_amd64.deb",
            "libarpack2_3.8.0-1_amd64.deb",
            "libspooles2.2_2.2-14_amd64.deb",
        ):
            _run(
                ["dpkg-deb", "--extract", str(asset_dir / name), str(calculix_root)],
                cwd=scratch,
            )

        opensees_license = opensees_runtime / "openseespy-3.7.1.2.dist-info/METADATA"
        calculix_binary = calculix_root / "usr/bin/ccx"
        calculix_library_dir = calculix_root / "usr/lib/x86_64-linux-gnu"
        calculix_license = calculix_root / "usr/share/doc/calculix-ccx/copyright"
        shared = [
            "--python-executable",
            sys.executable,
            "--opensees-python-path",
            str(opensees_runtime),
            "--opensees-license",
            str(opensees_license),
            "--calculix-binary",
            str(calculix_binary),
            "--calculix-library-dir",
            str(calculix_library_dir),
            "--calculix-license",
            str(calculix_license),
        ]
        for asset in assets:
            shared.extend(("--external-asset", str(asset)))

        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root / "src")
        _run(
            [sys.executable, str(code_script), "--out", str(code_out), *shared],
            cwd=repo_root,
            env=env,
        )
        _run(
            [
                sys.executable,
                str(modal_script),
                "--out",
                str(modal_out),
                "--vector-dir",
                vector_relative.as_posix(),
                *shared,
            ],
            cwd=repo_root,
            env=env,
        )
        _run(
            [sys.executable, str(code_script), "--out", str(code_out), "--check"],
            cwd=repo_root,
            env=env,
        )
        _run(
            [sys.executable, str(modal_script), "--out", str(modal_out), "--check"],
            cwd=repo_root,
            env=env,
        )

    code_receipt = _read_json(code_out)
    modal_receipt = _read_json(modal_out)
    host_code_reference = _read_json(repo_root / HOST_CODE_REFERENCE_RELATIVE_PATH)
    host_modal_reference = _read_json(repo_root / HOST_MODAL_REFERENCE_RELATIVE_PATH)
    _validate_product_receipt(code_receipt)
    _validate_product_receipt(modal_receipt)
    summary = _build_summary(
        repo_root=repo_root,
        output_dir=output_dir,
        assets=assets,
        code_receipt=code_receipt,
        modal_receipt=modal_receipt,
        host_code_reference=host_code_reference,
        host_modal_reference=host_modal_reference,
        derived_image_id=args.derived_image_id,
        source_read_only=source_read_only,
        default_route_present=default_route_present,
    )
    validate_summary(summary, repo_root=repo_root)
    _write_summary(output_dir / SUMMARY_RELATIVE_PATH, summary)
    print(
        f"{summary['status']} | technical={summary['technical_contract_pass']} | "
        f"level2={summary['claims']['verification_level_2']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
