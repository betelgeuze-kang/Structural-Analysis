#!/usr/bin/env python3
"""Build trust coordinates and audit a real portable install/update/rollback replay."""

from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Sequence
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TRUST_SCHEMA = "structural-frame-alpha-portable-transition-trust-input.v1"
RECEIPT_SCHEMA = "structural-frame-alpha-portable-transition-replay.v1"
RECEIPT_SCHEMA_PATH = (
    ROOT / "native/distribution/frame_alpha_portable_transition_replay_v1.schema.json"
)
TRUST_CLAIM = (
    "builder_emitted_coordinates_require_authenticated_transport_and_are_not_"
    "self_authenticated_by_the_archive"
)
RECEIPT_CLAIM = (
    "clean_runner_real_verifier_install_update_and_explicit_rollback_transition_"
    "with_ephemeral_second_generation_not_release_update_signing_or_commercial_"
    "authority"
)
AUTHORITY = {
    "clean_runner_transition_mechanism": "passed",
    "archive_verifier": "real_distribution_verifier_invoked_by_manager",
    "derived_update_generation": "ephemeral_test_only_not_release_candidate",
    "network_update": "not_implemented",
    "os_code_signing": "not_established",
    "engineering_design": "not_authoritative",
    "commercial_use": "not_authoritative",
    "release_readiness": "not_authoritative",
}
CHECKS = {
    "distinct_package_versions": True,
    "distinct_source_identities": True,
    "trusted_archive_sha256_supplied_to_manager": True,
    "real_distribution_verifier_before_each_apply": True,
    "install_update_rollback_lineage": True,
    "rollback_restored_initial_generation": True,
    "both_retained_payloads_verified": True,
}


class TransitionEvidenceError(RuntimeError):
    """Raised when transition evidence cannot be proven exactly."""


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise TransitionEvidenceError(f"module_import_failed:{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


distribution = _load_module(
    "build_native_frame_alpha_distribution_transition_evidence",
    ROOT / "scripts/build_native_frame_alpha_distribution.py",
)
portable = _load_module(
    "manage_native_frame_alpha_portable_install_transition_evidence",
    ROOT / "scripts/manage_native_frame_alpha_portable_install.py",
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _load_object(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise TransitionEvidenceError(f"{label}_must_be_regular_file")
    encoded = path.read_bytes()

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TransitionEvidenceError(f"{label}_duplicate_key:{key}")
            result[key] = value
        return result

    try:
        payload = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                TransitionEvidenceError(f"{label}_nonfinite:{token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TransitionEvidenceError(f"{label}_invalid_json") from error
    if not isinstance(payload, dict):
        raise TransitionEvidenceError(f"{label}_must_be_object")
    return payload, encoded


def _schema_type_matches(value: object, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return type(value) is int
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise TransitionEvidenceError(f"receipt_schema_type_unsupported:{expected}")


def _schema_reference(schema: dict[str, Any], reference: object) -> dict[str, Any]:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise TransitionEvidenceError("receipt_schema_reference_invalid")
    current: object = schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise TransitionEvidenceError("receipt_schema_reference_unknown")
        current = current[part]
    if not isinstance(current, dict):
        raise TransitionEvidenceError("receipt_schema_reference_not_object")
    return current


def _json_equal(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right


def _validate_schema_instance(
    value: object,
    node: dict[str, Any],
    schema: dict[str, Any],
    *,
    path: str,
) -> None:
    """Evaluate the closed JSON-Schema subset used by the transition receipt."""

    reference = node.get("$ref")
    if reference is not None:
        _validate_schema_instance(
            value,
            _schema_reference(schema, reference),
            schema,
            path=path,
        )
    all_of = node.get("allOf")
    if all_of is not None:
        if not isinstance(all_of, list) or not all_of:
            raise TransitionEvidenceError("receipt_schema_all_of_invalid")
        for index, child in enumerate(all_of):
            if not isinstance(child, dict):
                raise TransitionEvidenceError("receipt_schema_all_of_child_invalid")
            _validate_schema_instance(
                value,
                child,
                schema,
                path=f"{path}.allOf[{index}]",
            )
    expected_type = node.get("type")
    if expected_type is not None:
        if not isinstance(expected_type, str):
            raise TransitionEvidenceError("receipt_schema_type_invalid")
        if not _schema_type_matches(value, expected_type):
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:type:{expected_type}"
            )
    if "const" in node and not _json_equal(value, node["const"]):
        raise TransitionEvidenceError(f"receipt_schema_validation_failed:{path}:const")
    allowed = node.get("enum")
    if allowed is not None:
        if not isinstance(allowed, list) or not any(
            _json_equal(value, item) for item in allowed
        ):
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:enum"
            )
    pattern = node.get("pattern")
    if pattern is not None:
        if not isinstance(value, str) or not isinstance(pattern, str):
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:pattern_type"
            )
        try:
            matched = re.search(pattern, value)
        except re.error as error:
            raise TransitionEvidenceError("receipt_schema_pattern_invalid") from error
        if matched is None:
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:pattern"
            )
    if type(value) is int:
        minimum = node.get("minimum")
        maximum = node.get("maximum")
        if minimum is not None and value < minimum:
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:minimum"
            )
        if maximum is not None and value > maximum:
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:maximum"
            )
    if isinstance(value, dict):
        required = node.get("required", [])
        properties = node.get("properties", {})
        if not isinstance(required, list) or not isinstance(properties, dict):
            raise TransitionEvidenceError("receipt_schema_object_contract_invalid")
        missing = [key for key in required if key not in value]
        if missing:
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:required:{missing[0]}"
            )
        if node.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise TransitionEvidenceError(
                    f"receipt_schema_validation_failed:{path}:additionalProperties"
                )
        for key, child in properties.items():
            if key in value:
                if not isinstance(child, dict):
                    raise TransitionEvidenceError(
                        "receipt_schema_property_contract_invalid"
                    )
                _validate_schema_instance(
                    value[key], child, schema, path=f"{path}.{key}"
                )
    if isinstance(value, list):
        minimum_items = node.get("minItems")
        maximum_items = node.get("maxItems")
        if minimum_items is not None and len(value) < minimum_items:
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:minItems"
            )
        if maximum_items is not None and len(value) > maximum_items:
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:maxItems"
            )
        prefix_items = node.get("prefixItems", [])
        if not isinstance(prefix_items, list):
            raise TransitionEvidenceError("receipt_schema_prefix_items_invalid")
        for index, child in enumerate(prefix_items):
            if index >= len(value):
                break
            if not isinstance(child, dict):
                raise TransitionEvidenceError("receipt_schema_array_child_invalid")
            _validate_schema_instance(
                value[index], child, schema, path=f"{path}[{index}]"
            )
        if node.get("items") is False and len(value) > len(prefix_items):
            raise TransitionEvidenceError(
                f"receipt_schema_validation_failed:{path}:items"
            )


def _validate_receipt_schema(receipt: dict[str, Any]) -> None:
    schema, _encoded = _load_object(RECEIPT_SCHEMA_PATH, "receipt_schema")
    if (
        schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("type") != "object"
    ):
        raise TransitionEvidenceError("receipt_schema_contract_invalid")
    _validate_schema_instance(receipt, schema, schema, path="receipt")


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise TransitionEvidenceError(f"output_must_not_exist:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def _archive_coordinate(
    archive_path: Path, *, role: str, platform_tag: str
) -> dict[str, Any]:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise TransitionEvidenceError(f"{role}_archive_must_be_regular_file")
    archive_bytes = archive_path.read_bytes()
    if not 0 < len(archive_bytes) <= portable.MAX_ARCHIVE_BYTES:
        raise TransitionEvidenceError(f"{role}_archive_size_invalid")
    try:
        archive = zipfile.ZipFile(archive_path, mode="r")
    except zipfile.BadZipFile as error:
        raise TransitionEvidenceError(f"{role}_archive_invalid") from error
    with archive:
        manifest_names = [
            name for name in archive.namelist() if name.endswith("/manifest.json")
        ]
        if len(manifest_names) != 1:
            raise TransitionEvidenceError(f"{role}_manifest_count_invalid")
        manifest_name = manifest_names[0]
        manifest = distribution._strict_json(
            archive.read(manifest_name), f"{role}_manifest"
        )
        distribution._validate_workstation_manifest(manifest)
    parts = PurePosixPath(manifest_name).parts
    if len(parts) != 2 or parts[0] != manifest["package_id"]:
        raise TransitionEvidenceError(f"{role}_archive_root_invalid")
    if manifest["platform_tag"] != platform_tag:
        raise TransitionEvidenceError(f"{role}_platform_mismatch")
    source = manifest["source"]
    return {
        "role": role,
        "archive_filename": archive_path.name,
        "archive_sha256": portable._sha256_bytes(archive_bytes),
        "archive_byte_length": len(archive_bytes),
        "package_version": manifest["package_version"],
        "source": source,
        "ephemeral_test_generation": role == "ephemeral_update",
        "release_candidate": False,
    }


def build_trust_input(
    *,
    baseline_archive: Path,
    update_archive: Path,
    platform_tag: str,
) -> dict[str, Any]:
    if platform_tag not in portable.PLATFORMS:
        raise TransitionEvidenceError("platform_tag_invalid")
    generations = [
        _archive_coordinate(
            baseline_archive, role="baseline", platform_tag=platform_tag
        ),
        _archive_coordinate(
            update_archive, role="ephemeral_update", platform_tag=platform_tag
        ),
    ]
    first, second = generations
    if first["package_version"] == second["package_version"]:
        raise TransitionEvidenceError("generation_package_versions_not_distinct")
    if first["source"] == second["source"]:
        raise TransitionEvidenceError("generation_source_identities_not_distinct")
    if first["archive_sha256"] == second["archive_sha256"]:
        raise TransitionEvidenceError("generation_archives_not_distinct")
    return {
        "schema_version": TRUST_SCHEMA,
        "platform_tag": platform_tag,
        "transport_profile": "github_actions_immutable_artifact.v1",
        "generations": generations,
        "claim_boundary": TRUST_CLAIM,
    }


def _validate_trust_input(
    payload: dict[str, Any], platform_tag: str
) -> list[dict[str, Any]]:
    if set(payload) != {
        "schema_version",
        "platform_tag",
        "transport_profile",
        "generations",
        "claim_boundary",
    } or (
        payload.get("schema_version") != TRUST_SCHEMA
        or payload.get("platform_tag") != platform_tag
        or payload.get("transport_profile") != "github_actions_immutable_artifact.v1"
        or payload.get("claim_boundary") != TRUST_CLAIM
    ):
        raise TransitionEvidenceError("trust_input_contract_invalid")
    generations = payload.get("generations")
    if not isinstance(generations, list) or len(generations) != 2:
        raise TransitionEvidenceError("trust_input_generations_invalid")
    expected_roles = ("baseline", "ephemeral_update")
    validated: list[dict[str, Any]] = []
    for role, row in zip(expected_roles, generations, strict=True):
        if not isinstance(row, dict) or set(row) != {
            "role",
            "archive_filename",
            "archive_sha256",
            "archive_byte_length",
            "package_version",
            "source",
            "ephemeral_test_generation",
            "release_candidate",
        }:
            raise TransitionEvidenceError("trust_input_generation_fields_invalid")
        filename = str(row.get("archive_filename"))
        if Path(filename).name != filename or not filename.endswith(".zip"):
            raise TransitionEvidenceError("trust_input_archive_filename_invalid")
        portable._sha256(row.get("archive_sha256"), "trust_input_archive_sha256")
        portable._semantic_version(
            row.get("package_version"), "trust_input_package_version"
        )
        portable._validate_source(row.get("source"), "trust_input_source")
        if (
            row.get("role") != role
            or not isinstance(row.get("archive_byte_length"), int)
            or not 1 <= row["archive_byte_length"] <= portable.MAX_ARCHIVE_BYTES
            or row.get("ephemeral_test_generation") != (role == "ephemeral_update")
            or row.get("release_candidate") is not False
        ):
            raise TransitionEvidenceError("trust_input_generation_contract_invalid")
        validated.append(row)
    if validated[0]["package_version"] == validated[1]["package_version"]:
        raise TransitionEvidenceError("trust_input_package_versions_not_distinct")
    if validated[0]["source"] == validated[1]["source"]:
        raise TransitionEvidenceError("trust_input_sources_not_distinct")
    if validated[0]["archive_sha256"] == validated[1]["archive_sha256"]:
        raise TransitionEvidenceError("trust_input_archives_not_distinct")
    return validated


def _state(path: Path, label: str, install_root: Path) -> tuple[dict[str, Any], str]:
    payload, encoded = _load_object(path, label)
    portable._validate_state(payload, install_root, verify_payloads=True)
    if encoded != portable._state_bytes(payload):
        raise TransitionEvidenceError(f"{label}_not_canonical")
    return payload, portable._sha256_bytes(encoded)


def _matches_generation(summary: dict[str, Any], generation: dict[str, Any]) -> bool:
    return (
        summary["package"]["package_version"] == generation["package_version"]
        and summary["package"]["archive_sha256"] == generation["archive_sha256"]
        and summary["package"]["archive_byte_length"]
        == generation["archive_byte_length"]
        and summary["source"] == generation["source"]
    )


def _receipt_hash(receipt: dict[str, Any]) -> str:
    body = deepcopy(receipt)
    body.pop("schema_version", None)
    body.pop("receipt_hash", None)
    return portable._sha256_bytes(_canonical_bytes(body))


def _validate_receipt_cross_fields(receipt: dict[str, Any]) -> None:
    generations = receipt["generations"]
    first, second = generations
    if first["package_version"] == second["package_version"]:
        raise TransitionEvidenceError("receipt_package_versions_not_distinct")
    if first["source"] == second["source"]:
        raise TransitionEvidenceError("receipt_source_identities_not_distinct")
    if first["archive_sha256"] == second["archive_sha256"]:
        raise TransitionEvidenceError("receipt_archives_not_distinct")
    platform_tag = str(receipt["platform_tag"])
    expected_initial_key = portable._version_key(
        str(first["package_version"]),
        platform_tag,
        str(first["source"]["commit_sha"]),
    )
    if receipt["state_receipts"]["final_active_version_key"] != expected_initial_key:
        raise TransitionEvidenceError("receipt_final_active_generation_mismatch")
    if not _json_equal(receipt["checks"], CHECKS):
        raise TransitionEvidenceError("receipt_checks_invalid")


def _receipt_payload(
    *,
    trust_input_path: Path,
    install_state_path: Path,
    update_state_path: Path,
    rollback_state_path: Path,
    install_root: Path,
    platform_tag: str,
) -> dict[str, Any]:
    trust_input, trust_encoded = _load_object(trust_input_path, "trust_input")
    generations = _validate_trust_input(trust_input, platform_tag)
    installed, installed_hash = _state(
        install_state_path, "install_state", install_root
    )
    updated, updated_hash = _state(update_state_path, "update_state", install_root)
    rolled_back, rollback_hash = _state(
        rollback_state_path, "rollback_state", install_root
    )
    current = portable.verify_installation(install_root=install_root)
    first, second = generations
    states = (installed, updated, rolled_back)
    if (
        [state["revision"] for state in states] != [1, 2, 3]
        or [len(state["known_versions"]) for state in states] != [1, 2, 2]
        or [row["operation"] for row in rolled_back["history"]]
        != ["install", "update", "rollback"]
        or updated["history"][:1] != installed["history"]
        or rolled_back["history"][:2] != updated["history"]
        or any(
            state["active_version"]["package"]["platform_tag"] != platform_tag
            for state in states
        )
        or not _matches_generation(installed["active_version"], first)
        or not _matches_generation(updated["active_version"], second)
        or not _matches_generation(rolled_back["active_version"], first)
        or rolled_back != current
        or {row["version_key"] for row in rolled_back["known_versions"]}
        != {installed["active_version_key"], updated["active_version_key"]}
    ):
        raise TransitionEvidenceError("transition_lineage_invalid")
    body: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": "pass",
        "platform_tag": platform_tag,
        "trust_input_sha256": portable._sha256_bytes(trust_encoded),
        "generations": generations,
        "state_receipts": {
            "install_sha256": installed_hash,
            "update_sha256": updated_hash,
            "rollback_sha256": rollback_hash,
            "final_revision": 3,
            "final_active_version_key": rolled_back["active_version_key"],
        },
        "checks": deepcopy(CHECKS),
        "authority": deepcopy(AUTHORITY),
        "claim_boundary": RECEIPT_CLAIM,
    }
    receipt = {
        "schema_version": body.pop("schema_version"),
        "receipt_hash": _receipt_hash(body),
        **body,
    }
    _validate_receipt_schema(receipt)
    _validate_receipt_cross_fields(receipt)
    return receipt


def build_receipt(
    *,
    trust_input_path: Path,
    install_state_path: Path,
    update_state_path: Path,
    rollback_state_path: Path,
    install_root: Path,
    platform_tag: str,
) -> dict[str, Any]:
    return _receipt_payload(
        trust_input_path=trust_input_path,
        install_state_path=install_state_path,
        update_state_path=update_state_path,
        rollback_state_path=rollback_state_path,
        install_root=install_root,
        platform_tag=platform_tag,
    )


def verify_receipt(
    *,
    receipt_path: Path,
    trust_input_path: Path,
    install_state_path: Path,
    update_state_path: Path,
    rollback_state_path: Path,
    install_root: Path,
    platform_tag: str,
) -> dict[str, Any]:
    receipt, encoded = _load_object(receipt_path, "transition_receipt")
    _validate_receipt_schema(receipt)
    if encoded != _canonical_bytes(receipt) + b"\n":
        raise TransitionEvidenceError("transition_receipt_not_canonical")
    if receipt.get("receipt_hash") != _receipt_hash(receipt):
        raise TransitionEvidenceError("transition_receipt_hash_mismatch")
    _validate_receipt_cross_fields(receipt)
    expected = _receipt_payload(
        trust_input_path=trust_input_path,
        install_state_path=install_state_path,
        update_state_path=update_state_path,
        rollback_state_path=rollback_state_path,
        install_root=install_root,
        platform_tag=platform_tag,
    )
    if not _json_equal(receipt, expected):
        raise TransitionEvidenceError("transition_receipt_subject_binding_mismatch")
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    trust = commands.add_parser("trust-input")
    trust.add_argument("--baseline-archive", type=Path, required=True)
    trust.add_argument("--update-archive", type=Path, required=True)
    trust.add_argument("--platform-tag", choices=portable.PLATFORMS, required=True)
    trust.add_argument("--output", type=Path, required=True)

    def add_subject_arguments(command: argparse.ArgumentParser) -> None:
        command.add_argument("--trust-input", type=Path, required=True)
        command.add_argument("--install-state", type=Path, required=True)
        command.add_argument("--update-state", type=Path, required=True)
        command.add_argument("--rollback-state", type=Path, required=True)
        command.add_argument("--install-root", type=Path, required=True)
        command.add_argument(
            "--platform-tag", choices=portable.PLATFORMS, required=True
        )

    receipt = commands.add_parser("receipt")
    add_subject_arguments(receipt)
    receipt.add_argument("--output", type=Path, required=True)
    verify = commands.add_parser("verify-receipt")
    verify.add_argument("--receipt", type=Path, required=True)
    add_subject_arguments(verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "trust-input":
            payload = build_trust_input(
                baseline_archive=arguments.baseline_archive,
                update_archive=arguments.update_archive,
                platform_tag=arguments.platform_tag,
            )
            _write_new(arguments.output, payload)
        elif arguments.command == "receipt":
            payload = build_receipt(
                trust_input_path=arguments.trust_input,
                install_state_path=arguments.install_state,
                update_state_path=arguments.update_state,
                rollback_state_path=arguments.rollback_state,
                install_root=arguments.install_root,
                platform_tag=arguments.platform_tag,
            )
            _write_new(arguments.output, payload)
        else:
            payload = verify_receipt(
                receipt_path=arguments.receipt,
                trust_input_path=arguments.trust_input,
                install_state_path=arguments.install_state,
                update_state_path=arguments.update_state,
                rollback_state_path=arguments.rollback_state,
                install_root=arguments.install_root,
                platform_tag=arguments.platform_tag,
            )
    except (
        OSError,
        TransitionEvidenceError,
        portable.PortableInstallError,
        distribution.DistributionError,
        zipfile.BadZipFile,
    ) as error:
        print(
            f"Frame Alpha portable transition evidence failed: {error}", file=sys.stderr
        )
        return 1
    print(_canonical_bytes(payload).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
