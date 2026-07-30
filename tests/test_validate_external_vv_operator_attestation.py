from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_external_vv_operator_attestation.py"
spec = importlib.util.spec_from_file_location(
    "validate_external_vv_operator_attestation_tests", SCRIPT
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_json_artifact(path: Path, body: dict) -> dict:
    payload = deepcopy(body)
    payload["artifact_hash"] = module.artifact_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _descriptor(path: Path, root: Path, payload: dict | None = None) -> dict:
    row = {
        "path": path.relative_to(root).as_posix(),
        "file_sha256": module.file_sha256(path),
    }
    if payload is not None:
        row["artifact_hash"] = payload["artifact_hash"]
    return row


def _build_submission(root: Path, *, fresh: bool = True) -> tuple[dict, Path]:
    root.mkdir(parents=True, exist_ok=True)
    source_root = ROOT / "artifacts/vv/opensees_calculix_clean_runner"
    code = json.loads(
        (source_root / "external_code_to_code_receipt.json").read_text(encoding="utf-8")
    )
    modal = json.loads(
        (source_root / "external_modal_buckling_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    summary = json.loads(
        (source_root / "clean_runner_receipt.json").read_text(encoding="utf-8")
    )
    source_commit = code["source_commit_sha"]
    assert modal["source_commit_sha"] == summary["source_commit_sha"] == source_commit

    mode_descriptors = []
    for row in modal["mode_vector_artifacts"]:
        name = Path(row["artifact_path"]).name
        source_path = source_root / "mode_vectors" / name
        path = root / "mode_vectors" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, path)
        assert module.file_sha256(path) == row["data_hash"]
        mode_descriptors.append(_descriptor(path, root))

    for child in (code, modal):
        child["replay_provenance"].update(
            {
                "external_runtime_executed_in_this_generation": fresh,
                "external_execution_reused": not fresh,
                "reuse_reason": (
                    None if fresh else "retained prior external execution"
                ),
            }
        )
        if fresh:
            child["blockers_remaining"] = [
                blocker
                for blocker in child["blockers_remaining"]
                if blocker != "external_runtime_current_source_rerun_missing"
            ]
        child["artifact_hash"] = module.artifact_hash(child)

    code = _write_json_artifact(
        root / "external_code_to_code_receipt.json",
        code,
    )
    modal = _write_json_artifact(
        root / "external_modal_buckling_receipt.json",
        modal,
    )
    code_path = root / "external_code_to_code_receipt.json"
    modal_path = root / "external_modal_buckling_receipt.json"
    summary["claims"]["same_operator_container_isolated_reproduction"] = fresh
    summary["claims"]["cross_environment_numerical_parity"] = fresh
    summary["product_receipts"]["code_to_code"].update(
        {
            "file_sha256": module.file_sha256(code_path),
            "artifact_hash": code["artifact_hash"],
            "source_set_hash": code["internal_source"]["source_set_hash"],
            "fresh_external_runtime_execution": fresh,
        }
    )
    summary["product_receipts"]["modal_buckling"].update(
        {
            "file_sha256": module.file_sha256(modal_path),
            "artifact_hash": modal["artifact_hash"],
            "source_set_hash": modal["internal_source"]["source_set_hash"],
            "fresh_external_runtime_execution": fresh,
        }
    )
    if fresh:
        summary["blockers_remaining"] = [
            blocker
            for blocker in summary["blockers_remaining"]
            if blocker != "external_runtime_current_source_rerun_missing"
        ]
        summary["claim_boundary"] = (
            "Fresh same-operator container-isolated execution fixture derived from the "
            "complete tracked receipt structure for operator-intake contract testing. "
            "It grants no independent identity, Level 2, legal, design, or release authority."
        )
    summary["artifact_hash"] = module.artifact_hash(summary)
    summary = _write_json_artifact(
        root / "clean_runner_receipt.json",
        summary,
    )

    private_key = root / "operator-private-key.pem"
    public_key = root / "operator-public-key.pem"
    signature_path = root / "operator-attestation.sig"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        capture_output=True,
    )
    public_hash = module.file_sha256(public_key)
    attestation = {
        "schema_version": module.SCHEMA_VERSION,
        "attestation_id": "external-vv-operator-test",
        "signed_at": "2026-07-29T00:00:00Z",
        "source_commit_sha": source_commit,
        "operator": {
            "name": "Independent Operator",
            "organization": "Independent Verification Laboratory",
            "contact": "operator@example.test",
            "independence_basis": (
                "No organizational, financial, or implementation role in the product team."
            ),
            "conflict_check_completed": True,
            "signer_public_key_sha256": public_hash,
        },
        "execution": {
            "started_at": "2026-07-29T00:00:00Z",
            "completed_at": "2026-07-29T00:10:00Z",
            "host_platform": "Linux x86_64",
            "runner_command": "scripts/run_external_vv_clean_runner.sh <external-asset-directory>",
            "repository_mount_read_only": True,
            "runtime_network_disabled": True,
        },
        "bundle": {
            "clean_runner": _descriptor(
                root / "clean_runner_receipt.json", root, summary
            ),
            "code_to_code": _descriptor(code_path, root, code),
            "modal_buckling": _descriptor(modal_path, root, modal),
            "mode_vectors": mode_descriptors,
        },
        "declarations": {
            "independent_from_product_team": True,
            "external_runtimes_executed_by_operator": True,
            "no_external_execution_reuse": True,
            "submitted_bundle_unmodified_after_execution": True,
            "identity_credentials_verified_by_project": False,
        },
        "signature": {
            "algorithm": "rsa-sha256",
            "signed_payload_sha256": "sha256:" + "0" * 64,
            "public_key_path": public_key.name,
            "public_key_sha256": public_hash,
            "signature_path": signature_path.name,
            "signature_sha256": "sha256:" + "0" * 64,
        },
        "contract_pass": True,
        "claim_boundary": (
            "This submission attests only to the exact fresh external clean-runner bundle "
            "and independent execution. It does not grant Level 2, design, commercial, "
            "identity-authentication, legal, or release authority without separate review."
        ),
    }
    payload_path = root / "signed-payload.json"
    payload = module.signed_payload(attestation)
    payload_path.write_bytes(payload)
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature_path),
            str(payload_path),
        ],
        check=True,
        capture_output=True,
    )
    attestation["signature"]["signed_payload_sha256"] = module.sha256_bytes(payload)
    attestation["signature"]["signature_sha256"] = module.file_sha256(signature_path)
    return attestation, root


def _resign(attestation: dict, bundle_root: Path) -> None:
    private_key = bundle_root / "operator-private-key.pem"
    signature_path = bundle_root / attestation["signature"]["signature_path"]
    payload_path = bundle_root / "signed-payload.json"
    payload = module.signed_payload(attestation)
    payload_path.write_bytes(payload)
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature_path),
            str(payload_path),
        ],
        check=True,
        capture_output=True,
    )
    attestation["signature"]["signed_payload_sha256"] = module.sha256_bytes(payload)
    attestation["signature"]["signature_sha256"] = module.file_sha256(signature_path)


def _attach_linear_supplement(attestation: dict, bundle_root: Path) -> dict[str, Path]:
    source_package = ROOT / module.linear_package.DEFAULT_OUT_DIR
    package_root = bundle_root / "bounded-planar-linear-package"
    shutil.copytree(source_package, package_root)
    manifest_path = package_root / module.linear_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_commit_sha"] == attestation["source_commit_sha"]

    results_root = bundle_root / "linear-results"
    results_root.mkdir()
    result_paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        case_id = case["case_id"]
        product = json.loads(
            (package_root / case["product_result"]["path"]).read_text(encoding="utf-8")
        )
        result = {
            "schema_version": "bounded-planar-opensees-linear-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case_id,
            "executed_at": "2026-07-29T00:05:00Z",
            "runner_file_sha256": case["opensees_runner"]["file_sha256"],
            "source_model_file_sha256": case["model_ir"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": attestation["execution"]["host_platform"],
                "openseespy_version": "3.7.1.2",
                "opensees_core_version": "3.7.1",
            },
            "return_codes": [0, 0, 0, 0],
            "metrics": product["metrics"],
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": "sha256:" + "0" * 64,
        }
        result["artifact_hash"] = module.linear_ingest._artifact_hash(result)
        path = results_root / f"{case_id}.json"
        path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_paths[case_id] = path

    receipt = module.linear_ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = results_root / "technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    attestation["execution"]["supplementary_runner_commands"] = [
        "python opensees/bounded_planar_linear_portal.py external-results/bounded_planar_linear_portal.json",
        "python opensees/bounded_planar_linear_multistory.py external-results/bounded_planar_linear_multistory.json",
    ]
    attestation["bundle"]["bounded_planar_linear"] = {
        "execution_package_manifest": _descriptor(manifest_path, bundle_root, manifest),
        "technical_receipt": _descriptor(receipt_path, bundle_root, receipt),
        "external_results": [
            _descriptor(
                result_paths[case["case_id"]],
                bundle_root,
                json.loads(result_paths[case["case_id"]].read_text(encoding="utf-8")),
            )
            for case in manifest["cases"]
        ],
    }
    attestation["declarations"]["supplementary_results_executed_by_operator"] = True
    _resign(attestation, bundle_root)
    return result_paths


def _refresh_linear_supplement(attestation: dict, bundle_root: Path) -> None:
    package_root = bundle_root / "bounded-planar-linear-package"
    manifest_path = package_root / module.linear_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results_root = bundle_root / "linear-results"
    receipt = module.linear_ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = results_root / "technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    supplement = attestation["bundle"]["bounded_planar_linear"]
    supplement["technical_receipt"] = _descriptor(receipt_path, bundle_root, receipt)
    supplement["external_results"] = []
    for case in manifest["cases"]:
        result_path = results_root / f"{case['case_id']}.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        supplement["external_results"].append(
            _descriptor(result_path, bundle_root, result)
        )
    _resign(attestation, bundle_root)


def _modal_buckling_result(
    *,
    case: dict,
    manifest: dict,
    package_root: Path,
    host_platform: str,
) -> dict:
    product = json.loads(
        (package_root / case["product_result"]["path"]).read_text(encoding="utf-8")
    )
    observations = deepcopy(product["observations"])
    if case["requirement_id"] == "modal.rigid_mode":
        observations["eigenvalues"] = [0.0] * 6 + observations["eigenvalues"]
        observations["mode_vectors"] = [[0.0] * 12 for _ in range(12)]
    elif case["requirement_id"] == "modal.repeated_mode":
        first, second = observations["mode_vectors"]
        scale = 2.0**-0.5
        observations["mode_vectors"] = [
            [scale * (left + right) for left, right in zip(first, second)],
            [scale * (left - right) for left, right in zip(first, second)],
        ]
    result = {
        "schema_version": "bounded-planar-external-modal-buckling-result.v1",
        "package_id": manifest["package_id"],
        "case_id": case["case_id"],
        "analysis_type": case["analysis_type"],
        "external_solver": case["external_solver"],
        "executed_at": "2026-07-29T00:05:00Z",
        "runner_file_sha256": case["external_runner"]["file_sha256"],
        "source_model_file_sha256": case["model"]["file_sha256"],
        "runtime": {
            "solver_version": (
                module.modal_buckling_package.PINNED_OPENSEES_CORE_VERSION
                if case["external_solver"] == "OpenSees"
                else module.modal_buckling_package.PINNED_CALCULIX_VERSION
            ),
            "python_version": "3.11.9",
            "platform": host_platform,
        },
        "observations": observations,
        "contract_pass": True,
        "blockers": [],
        "artifact_hash": module.modal_buckling_ingest.ZERO_HASH,
    }
    result["artifact_hash"] = module.modal_buckling_ingest._artifact_hash(result)
    return result


def _attach_modal_buckling_supplement(
    attestation: dict, bundle_root: Path
) -> dict[str, Path]:
    source_package = ROOT / module.modal_buckling_package.DEFAULT_OUT_DIR
    package_root = bundle_root / "bounded-planar-modal-buckling-package"
    shutil.copytree(source_package, package_root)
    manifest_path = package_root / module.modal_buckling_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_commit_sha"] == attestation["source_commit_sha"]

    results_root = bundle_root / "modal-buckling-results"
    results_root.mkdir()
    result_paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        result = _modal_buckling_result(
            case=case,
            manifest=manifest,
            package_root=package_root,
            host_platform=attestation["execution"]["host_platform"],
        )
        path = results_root / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_paths[case["case_id"]] = path
    receipt = module.modal_buckling_ingest.build_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = results_root / "technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    commands = attestation["execution"].setdefault("supplementary_runner_commands", [])
    commands.extend(module.MODAL_BUCKLING_SUPPLEMENT_COMMANDS)
    attestation["bundle"]["bounded_planar_modal_buckling"] = {
        "execution_package_manifest": _descriptor(manifest_path, bundle_root, manifest),
        "technical_receipt": _descriptor(receipt_path, bundle_root, receipt),
        "external_results": [
            _descriptor(
                result_paths[case["case_id"]],
                bundle_root,
                json.loads(result_paths[case["case_id"]].read_text(encoding="utf-8")),
            )
            for case in manifest["cases"]
        ],
    }
    attestation["declarations"]["supplementary_results_executed_by_operator"] = True
    _resign(attestation, bundle_root)
    return result_paths


def _refresh_modal_buckling_supplement(attestation: dict, bundle_root: Path) -> None:
    package_root = bundle_root / "bounded-planar-modal-buckling-package"
    manifest_path = package_root / module.modal_buckling_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results_root = bundle_root / "modal-buckling-results"
    receipt = module.modal_buckling_ingest.build_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = results_root / "technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    supplement = attestation["bundle"]["bounded_planar_modal_buckling"]
    supplement["technical_receipt"] = _descriptor(receipt_path, bundle_root, receipt)
    supplement["external_results"] = [
        _descriptor(
            results_root / f"{case['case_id']}.json",
            bundle_root,
            json.loads(
                (results_root / f"{case['case_id']}.json").read_text(encoding="utf-8")
            ),
        )
        for case in manifest["cases"]
    ]
    _resign(attestation, bundle_root)


def _attach_negative_supplement(
    attestation: dict, bundle_root: Path
) -> dict[str, Path]:
    source_package = ROOT / module.negative_package.DEFAULT_OUT_DIR
    package_root = bundle_root / "bounded-planar-negative-package"
    shutil.copytree(source_package, package_root)
    manifest_path = package_root / module.negative_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_commit_sha"] == attestation["source_commit_sha"]

    results_root = bundle_root / "negative-results"
    results_root.mkdir()
    result_paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        invalid_geometry = case["requirement_id"] == "negative.invalid_geometry"
        singular = case["requirement_id"] == "negative.singular"
        tangent_rank_check = (
            {
                "equation_count": 10,
                "matrix_value_count": 100,
                "maximum_absolute_entry": 1000.0,
                "relative_pivot_tolerance": 1.0e-12,
                "absolute_pivot_tolerance": 1.0e-8,
                "numerical_rank": 9,
                "rank_deficient": True,
            }
            if singular
            else None
        )
        result = {
            "schema_version": "bounded-planar-opensees-negative-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case["case_id"],
            "executed_at": "2026-07-29T00:05:00Z",
            "runner_file_sha256": case["opensees_runner"]["file_sha256"],
            "source_model_file_sha256": case["model_ir"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": attestation["execution"]["host_platform"],
                "openseespy_version": "3.7.1.2",
                "opensees_core_version": "3.7.1",
            },
            "external_engine_invoked": not invalid_geometry,
            "model_construction_succeeded": not invalid_geometry,
            "analysis_return_code": (
                None if invalid_geometry else (0 if singular else -3)
            ),
            "exception_type": None,
            "tangent_rank_check": tangent_rank_check,
            "observation": case["expected_external_observation"],
            "classification_match": True,
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": "sha256:" + "0" * 64,
        }
        result["artifact_hash"] = module.negative_ingest._artifact_hash(result)
        path = results_root / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_paths[case["case_id"]] = path
    receipt = module.negative_ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = bundle_root / "negative-technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    commands = attestation["execution"].setdefault("supplementary_runner_commands", [])
    commands.extend(module.NEGATIVE_SUPPLEMENT_COMMANDS)
    attestation["bundle"]["bounded_planar_negative"] = {
        "execution_package_manifest": _descriptor(manifest_path, bundle_root, manifest),
        "technical_receipt": _descriptor(receipt_path, bundle_root, receipt),
        "external_results": [
            _descriptor(
                result_paths[case["case_id"]],
                bundle_root,
                json.loads(result_paths[case["case_id"]].read_text(encoding="utf-8")),
            )
            for case in manifest["cases"]
        ],
    }
    attestation["declarations"]["supplementary_results_executed_by_operator"] = True
    _resign(attestation, bundle_root)
    return result_paths


def _refresh_negative_supplement(attestation: dict, bundle_root: Path) -> None:
    package_root = bundle_root / "bounded-planar-negative-package"
    manifest_path = package_root / module.negative_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results_root = bundle_root / "negative-results"
    receipt = module.negative_ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = bundle_root / "negative-technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    supplement = attestation["bundle"]["bounded_planar_negative"]
    supplement["technical_receipt"] = _descriptor(receipt_path, bundle_root, receipt)
    supplement["external_results"] = [
        _descriptor(
            results_root / f"{case['case_id']}.json",
            bundle_root,
            json.loads(
                (results_root / f"{case['case_id']}.json").read_text(encoding="utf-8")
            ),
        )
        for case in manifest["cases"]
    ]
    _resign(attestation, bundle_root)


def _attach_scaling_supplement(attestation: dict, bundle_root: Path) -> dict[str, Path]:
    source_package = ROOT / module.scaling_package.DEFAULT_OUT_DIR
    package_root = bundle_root / "bounded-planar-scaling-package"
    shutil.copytree(source_package, package_root)
    manifest_path = package_root / module.scaling_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_commit_sha"] == attestation["source_commit_sha"]

    results_root = bundle_root / "scaling-results"
    results_root.mkdir()
    result_paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        product = json.loads(
            (package_root / case["product_result"]["path"]).read_text(encoding="utf-8")
        )
        result = {
            "schema_version": "bounded-planar-opensees-scaling-result.v1",
            "package_id": manifest["package_id"],
            "case_id": case["case_id"],
            "executed_at": "2026-07-29T00:05:00Z",
            "runner_file_sha256": case["opensees_runner"]["file_sha256"],
            "source_model_pair_file_sha256": case["model_pair"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": attestation["execution"]["host_platform"],
                "openseespy_version": "3.7.1.2",
                "opensees_core_version": "3.7.1",
            },
            "variants": [
                {
                    "variant_id": variant["variant_id"],
                    "raw_metrics_si": dict(variant["normalized_metrics"]),
                    "normalized_metrics": dict(variant["normalized_metrics"]),
                }
                for variant in product["variants"]
            ],
            "relative_differences": dict(product["relative_differences"]),
            "maximum_relative_difference": product["maximum_relative_difference"],
            "relative_tolerance": product["relative_tolerance"],
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": "sha256:" + "0" * 64,
        }
        result["artifact_hash"] = module.scaling_ingest._artifact_hash(result)
        path = results_root / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_paths[case["case_id"]] = path
    receipt = module.scaling_ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = results_root / "technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    commands = attestation["execution"].setdefault("supplementary_runner_commands", [])
    commands.extend(module.SCALING_SUPPLEMENT_COMMANDS)
    attestation["bundle"]["bounded_planar_scaling"] = {
        "execution_package_manifest": _descriptor(manifest_path, bundle_root, manifest),
        "technical_receipt": _descriptor(receipt_path, bundle_root, receipt),
        "external_results": [
            _descriptor(
                result_paths[case["case_id"]],
                bundle_root,
                json.loads(result_paths[case["case_id"]].read_text(encoding="utf-8")),
            )
            for case in manifest["cases"]
        ],
    }
    attestation["declarations"]["supplementary_results_executed_by_operator"] = True
    _resign(attestation, bundle_root)
    return result_paths


def _refresh_scaling_supplement(attestation: dict, bundle_root: Path) -> None:
    package_root = bundle_root / "bounded-planar-scaling-package"
    manifest_path = package_root / module.scaling_package.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results_root = bundle_root / "scaling-results"
    receipt = module.scaling_ingest.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = results_root / "technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    supplement = attestation["bundle"]["bounded_planar_scaling"]
    supplement["technical_receipt"] = _descriptor(receipt_path, bundle_root, receipt)
    supplement["external_results"] = [
        _descriptor(
            results_root / f"{case['case_id']}.json",
            bundle_root,
            json.loads(
                (results_root / f"{case['case_id']}.json").read_text(encoding="utf-8")
            ),
        )
        for case in manifest["cases"]
    ]
    _resign(attestation, bundle_root)


def _attach_nonlinear_material_recovery_supplement(
    attestation: dict, bundle_root: Path
) -> dict[str, Path]:
    package_module = module.nonlinear_material_recovery_package
    ingest_module = module.nonlinear_material_recovery_ingest
    source_package = ROOT / package_module.DEFAULT_OUT_DIR
    package_root = bundle_root / "bounded-planar-nonlinear-material-recovery-package"
    shutil.copytree(source_package, package_root)
    manifest_path = package_root / package_module.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_commit_sha"] == attestation["source_commit_sha"]

    results_root = bundle_root / "nonlinear-material-recovery-results"
    results_root.mkdir()
    result_paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        product = json.loads(
            (package_root / case["product_result"]["path"]).read_text(
                encoding="utf-8"
            )
        )
        result = {
            "schema_version": (
                "bounded-planar-opensees-nonlinear-material-recovery-result.v1"
            ),
            "package_id": manifest["package_id"],
            "case_id": case["case_id"],
            "executed_at": "2026-07-29T00:05:00Z",
            "runner_file_sha256": case["external_runner"]["file_sha256"],
            "source_model_file_sha256": case["model"]["file_sha256"],
            "runtime": {
                "python_version": "3.10.19",
                "platform": attestation["execution"]["host_platform"],
                "openseespy_version": package_module.PINNED_OPENSEESPY_VERSION,
                "opensees_core_version": package_module.PINNED_OPENSEES_CORE_VERSION,
            },
            "return_codes": [0],
            "metrics": product["metrics"],
            "contract_pass": True,
            "blockers": [],
            "artifact_hash": ingest_module.ZERO_HASH,
        }
        result["artifact_hash"] = ingest_module._artifact_hash(result)
        path = results_root / f"{case['case_id']}.json"
        path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_paths[case["case_id"]] = path
    receipt = ingest_module.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = bundle_root / "nonlinear-material-recovery-technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    commands = attestation["execution"].setdefault(
        "supplementary_runner_commands", []
    )
    commands.extend(module.NONLINEAR_MATERIAL_RECOVERY_SUPPLEMENT_COMMANDS)
    attestation["bundle"]["bounded_planar_nonlinear_material_recovery"] = {
        "execution_package_manifest": _descriptor(manifest_path, bundle_root, manifest),
        "technical_receipt": _descriptor(receipt_path, bundle_root, receipt),
        "external_results": [
            _descriptor(
                result_paths[case["case_id"]],
                bundle_root,
                json.loads(
                    result_paths[case["case_id"]].read_text(encoding="utf-8")
                ),
            )
            for case in manifest["cases"]
        ],
    }
    attestation["declarations"]["supplementary_results_executed_by_operator"] = True
    _resign(attestation, bundle_root)
    return result_paths


def _refresh_nonlinear_material_recovery_supplement(
    attestation: dict, bundle_root: Path
) -> None:
    package_module = module.nonlinear_material_recovery_package
    ingest_module = module.nonlinear_material_recovery_ingest
    package_root = bundle_root / "bounded-planar-nonlinear-material-recovery-package"
    manifest_path = package_root / package_module.MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results_root = bundle_root / "nonlinear-material-recovery-results"
    receipt = ingest_module.build_execution_receipt(
        repo_root=ROOT,
        package_dir=package_root,
        results_dir=results_root,
    )
    receipt_path = bundle_root / "nonlinear-material-recovery-technical-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    supplement = attestation["bundle"][
        "bounded_planar_nonlinear_material_recovery"
    ]
    supplement["technical_receipt"] = _descriptor(
        receipt_path, bundle_root, receipt
    )
    supplement["external_results"] = [
        _descriptor(
            results_root / f"{case['case_id']}.json",
            bundle_root,
            json.loads(
                (results_root / f"{case['case_id']}.json").read_text(
                    encoding="utf-8"
                )
            ),
        )
        for case in manifest["cases"]
    ]
    _resign(attestation, bundle_root)


def test_operator_attestation_schema_is_valid() -> None:
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_signed_fresh_bundle_is_integrity_valid_but_not_level2(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert result["intake_contract_pass"] is True
    assert result["fresh_external_runtime_execution"] is True
    assert result["two_external_solver_slots_bound"] is True
    assert result["signature"]["cryptographic_signature_verified"] is True
    assert result["operator_identity_credentials_verified"] is False
    assert result["claims"]["verification_hierarchy_level_2"] is False
    assert "operator_identity_authentication_missing" in result["blockers_remaining"]


def test_signed_linear_supplement_is_bound_but_not_promoted(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_linear_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert result["intake_contract_pass"] is True
    assert result["bounded_planar_linear_supplement_attached"] is True
    assert result["bounded_planar_linear_fresh_execution_declared"] is True
    assert result["claims"]["supplementary_linear_execution_signed"] is True
    linear = result["bundle_binding"]["bounded_planar_linear"]
    assert linear["case_ids"] == [
        "bounded_planar_linear_portal",
        "bounded_planar_linear_multistory",
    ]
    assert linear["fresh_execution_declared_by_signer"] is True
    assert linear["verification_matrix_credit"] is False
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_signed_modal_buckling_supplement_is_bound_but_not_promoted(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_modal_buckling_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert result["intake_contract_pass"] is True
    assert result["bounded_planar_modal_buckling_supplement_attached"] is True
    assert result["bounded_planar_modal_buckling_fresh_execution_declared"] is True
    assert result["claims"]["supplementary_modal_buckling_execution_signed"] is True
    binding = result["bundle_binding"]["bounded_planar_modal_buckling"]
    assert binding["case_ids"] == [
        "bounded_planar_modal_rigid_mode",
        "bounded_planar_modal_repeated_mode",
        "bounded_planar_buckling_portal",
    ]
    assert binding["fresh_execution_declared_by_signer"] is True
    assert binding["verification_matrix_credit"] is False
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_signed_negative_supplement_is_bound_but_not_promoted(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_negative_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert result["intake_contract_pass"] is True
    assert result["bounded_planar_negative_supplement_attached"] is True
    assert result["bounded_planar_negative_fresh_execution_declared"] is True
    assert result["claims"]["supplementary_negative_execution_signed"] is True
    binding = result["bundle_binding"]["bounded_planar_negative"]
    assert binding["case_ids"] == [
        "bounded_planar_negative_mechanism",
        "bounded_planar_negative_singular",
        "bounded_planar_negative_invalid_geometry",
    ]
    assert binding["external_solver_execution_case_count"] == 2
    assert binding["independent_preflight_case_count"] == 1
    assert binding["verification_matrix_credit"] is False
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_signed_scaling_supplement_is_bound_but_not_promoted(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_scaling_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert result["intake_contract_pass"] is True
    assert result["bounded_planar_scaling_supplement_attached"] is True
    assert result["bounded_planar_scaling_fresh_execution_declared"] is True
    assert result["claims"]["supplementary_scaling_execution_signed"] is True
    binding = result["bundle_binding"]["bounded_planar_scaling"]
    assert binding["case_ids"] == [
        "bounded_planar_scaling_unit_invariance",
        "bounded_planar_scaling_characteristic_length_invariance",
    ]
    assert binding["fresh_execution_declared_by_signer"] is True
    assert binding["verification_matrix_credit"] is False
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_signed_nonlinear_material_recovery_supplement_is_bound_but_not_promoted(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_nonlinear_material_recovery_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert result["intake_contract_pass"] is True
    assert (
        result["bounded_planar_nonlinear_material_recovery_supplement_attached"]
        is True
    )
    assert (
        result[
            "bounded_planar_nonlinear_material_recovery_fresh_execution_declared"
        ]
        is True
    )
    assert (
        result["claims"][
            "supplementary_nonlinear_material_recovery_execution_signed"
        ]
        is True
    )
    binding = result["bundle_binding"][
        "bounded_planar_nonlinear_material_recovery"
    ]
    assert binding["case_ids"] == [
        "bounded_planar_p_delta",
        "bounded_planar_snap_through",
        "bounded_planar_steel_yield",
        "bounded_planar_rc_fiber",
        "bounded_planar_section_recovery",
        "bounded_planar_fiber_recovery",
    ]
    assert binding["external_solver_execution_case_count"] == 6
    assert binding["fresh_execution_declared_by_signer"] is True
    assert binding["verification_matrix_credit"] is False
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_signed_linear_and_modal_buckling_supplements_share_exact_command_set(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_linear_supplement(attestation, bundle_root)
    _attach_modal_buckling_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert attestation["execution"]["supplementary_runner_commands"] == [
        *module.LINEAR_SUPPLEMENT_COMMANDS,
        *module.MODAL_BUCKLING_SUPPLEMENT_COMMANDS,
    ]
    assert result["bounded_planar_linear_supplement_attached"] is True
    assert result["bounded_planar_modal_buckling_supplement_attached"] is True
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_all_dedicated_supplements_share_exact_sixteen_command_union(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_linear_supplement(attestation, bundle_root)
    _attach_modal_buckling_supplement(attestation, bundle_root)
    _attach_negative_supplement(attestation, bundle_root)
    _attach_scaling_supplement(attestation, bundle_root)
    _attach_nonlinear_material_recovery_supplement(attestation, bundle_root)

    result = module.validate_external_vv_operator_attestation(
        attestation,
        bundle_root=bundle_root,
        repo_root=ROOT,
    )

    assert attestation["execution"]["supplementary_runner_commands"] == [
        *module.LINEAR_SUPPLEMENT_COMMANDS,
        *module.MODAL_BUCKLING_SUPPLEMENT_COMMANDS,
        *module.NEGATIVE_SUPPLEMENT_COMMANDS,
        *module.SCALING_SUPPLEMENT_COMMANDS,
        *module.NONLINEAR_MATERIAL_RECOVERY_SUPPLEMENT_COMMANDS,
    ]
    assert result["claims"]["supplementary_negative_execution_signed"] is True
    assert result["claims"]["supplementary_scaling_execution_signed"] is True
    assert (
        result["claims"][
            "supplementary_nonlinear_material_recovery_execution_signed"
        ]
        is True
    )
    assert result["claims"]["verification_hierarchy_level_2"] is False


def test_negative_supplement_result_tamper_fails_closed(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_negative_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_negative_mechanism"]
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="bundle_file_hash_mismatch",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_scaling_supplement_result_tamper_fails_closed(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_scaling_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_scaling_unit_invariance"]
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="bundle_file_hash_mismatch",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_nonlinear_material_recovery_result_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_nonlinear_material_recovery_supplement(
        attestation, bundle_root
    )
    path = result_paths["bounded_planar_p_delta"]
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="bundle_file_hash_mismatch",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_negative_result_must_be_inside_signed_execution_window(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_negative_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_negative_singular"]
    result = json.loads(path.read_text(encoding="utf-8"))
    result["executed_at"] = "2026-07-29T00:20:00Z"
    result["artifact_hash"] = module.negative_ingest._artifact_hash(result)
    path.write_text(json.dumps(result), encoding="utf-8")
    _refresh_negative_supplement(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="operator_attestation_negative_result_outside_execution_window",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_scaling_result_must_be_inside_signed_execution_window(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_scaling_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_scaling_characteristic_length_invariance"]
    result = json.loads(path.read_text(encoding="utf-8"))
    result["executed_at"] = "2026-07-29T00:20:00Z"
    result["artifact_hash"] = module.scaling_ingest._artifact_hash(result)
    path.write_text(json.dumps(result), encoding="utf-8")
    _refresh_scaling_supplement(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="operator_attestation_scaling_result_outside_execution_window",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_nonlinear_material_recovery_result_must_be_inside_signed_execution_window(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_nonlinear_material_recovery_supplement(
        attestation, bundle_root
    )
    path = result_paths["bounded_planar_snap_through"]
    result = json.loads(path.read_text(encoding="utf-8"))
    result["executed_at"] = "2026-07-29T00:20:00Z"
    result["artifact_hash"] = (
        module.nonlinear_material_recovery_ingest._artifact_hash(result)
    )
    path.write_text(json.dumps(result), encoding="utf-8")
    _refresh_nonlinear_material_recovery_supplement(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match=(
            "operator_attestation_nonlinear_material_recovery_result_"
            "outside_execution_window"
        ),
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_modal_buckling_supplement_result_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_modal_buckling_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_modal_rigid_mode"]
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="bundle_file_hash_mismatch",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_modal_buckling_result_must_be_inside_signed_execution_window(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_modal_buckling_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_buckling_portal"]
    result = json.loads(path.read_text(encoding="utf-8"))
    result["executed_at"] = "2026-07-29T00:20:00Z"
    result["artifact_hash"] = module.modal_buckling_ingest._artifact_hash(result)
    path.write_text(json.dumps(result), encoding="utf-8")
    _refresh_modal_buckling_supplement(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match=("operator_attestation_modal_buckling_result_outside_execution_window"),
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_linear_supplement_result_tamper_fails_closed(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_linear_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_linear_portal"]
    path.write_bytes(path.read_bytes() + b"tamper")

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="bundle_file_hash_mismatch",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_linear_supplement_requires_exact_runner_commands(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    _attach_linear_supplement(attestation, bundle_root)
    del attestation["execution"]["supplementary_runner_commands"]
    _resign(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="operator_attestation_schema_invalid:/execution",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


@pytest.mark.parametrize(
    "case_id",
    ["bounded_planar_negative_mechanism", "bounded_planar_p_delta"],
)
def test_additional_receipt_cannot_bypass_dedicated_supplement_validation(
    tmp_path: Path, case_id: str
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    receipt = {
        "schema_version": "untyped-additional-technical-receipt.v1",
        "source_commit_sha": attestation["source_commit_sha"],
        "cases": [
            {
                "case_id": case_id,
                "technical_comparison_pass": True,
            }
        ],
        "technical_contract_pass": True,
        "artifact_hash": "sha256:" + "0" * 64,
    }
    receipt["artifact_hash"] = module.artifact_hash(receipt)
    receipt_path = bundle_root / "loose-negative-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    attestation["bundle"]["additional_receipts"] = [
        _descriptor(receipt_path, bundle_root, receipt)
    ]
    _resign(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="operator_attestation_additional_receipt_dedicated_case_forbidden",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_linear_supplement_result_must_be_inside_signed_execution_window(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    result_paths = _attach_linear_supplement(attestation, bundle_root)
    path = result_paths["bounded_planar_linear_portal"]
    result = json.loads(path.read_text(encoding="utf-8"))
    result["executed_at"] = "2026-07-29T00:20:00Z"
    result["artifact_hash"] = module.linear_ingest._artifact_hash(result)
    path.write_text(json.dumps(result), encoding="utf-8")
    _refresh_linear_supplement(attestation, bundle_root)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="operator_attestation_linear_result_outside_execution_window",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_signature_or_placeholder_tamper_fails_closed(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    signature_path = bundle_root / attestation["signature"]["signature_path"]
    signature_path.write_bytes(signature_path.read_bytes() + b"tamper")
    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="signature_artifact_hash_mismatch",
    ):
        module.validate_external_vv_operator_attestation(
            attestation, bundle_root=bundle_root, repo_root=ROOT
        )

    placeholder, placeholder_root = _build_submission(tmp_path / "placeholder")
    placeholder["operator"]["name"] = "PLACEHOLDER"
    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="operator_attestation_placeholder_rejected",
    ):
        module.validate_external_vv_operator_attestation(
            placeholder, bundle_root=placeholder_root, repo_root=ROOT
        )


def test_reused_external_execution_cannot_be_attested_as_fresh(tmp_path: Path) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle", fresh=False)

    with pytest.raises(
        module.ExternalVVOperatorAttestationError,
        match="fresh_external_runtime_required",
    ):
        module.validate_external_vv_operator_attestation(
            attestation,
            bundle_root=bundle_root,
            repo_root=ROOT,
        )


def test_cli_emits_exact_signing_payload_and_validation_receipt(
    tmp_path: Path,
) -> None:
    attestation, bundle_root = _build_submission(tmp_path / "bundle")
    attestation_path = bundle_root / "operator-attestation.json"
    payload_path = tmp_path / "operator-payload.json"
    validation_path = tmp_path / "operator-validation.json"
    attestation_path.write_text(
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    emitted = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--attestation",
            str(attestation_path),
            "--emit-signing-payload",
            str(payload_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert emitted.returncode == 0, emitted.stderr + emitted.stdout
    assert payload_path.read_bytes() == module.signed_payload(attestation)
    assert emitted.stdout.strip() == module.sha256_bytes(payload_path.read_bytes())

    validated = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--attestation",
            str(attestation_path),
            "--bundle-root",
            str(bundle_root),
            "--out",
            str(validation_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert validated.returncode == 0, validated.stderr + validated.stdout
    result = json.loads(validation_path.read_text(encoding="utf-8"))
    assert result["intake_contract_pass"] is True
    assert result["claims"]["verification_hierarchy_level_2"] is False
