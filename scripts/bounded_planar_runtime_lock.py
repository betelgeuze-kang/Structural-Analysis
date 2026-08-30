#!/usr/bin/env python3
"""Pre-execution runtime lock for bounded-planar supplemental executions.

The lock deliberately separates acquisition from execution. A producer may use
the network while building a local image or downloading the named assets, but it
must capture the content-addressed image ID, every rootfs diff ID, and every
external asset digest before a no-network solver process is started.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = "bounded-planar-runtime-preexecution-lock.v1"
ZERO_HASH = "sha256:" + "0" * 64
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

OPENSEESPY_VERSION = "3.7.1.2"
OPENSEES_CORE_VERSION = "3.7.1"
OPENSEESPY_WHEEL_SHA256 = (
    "1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65"
)
OPENSEESPY_LINUX_WHEEL_SHA256 = (
    "63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a"
)

BASE_IMAGE = (
    "docker.io/library/python:3.11-slim-bookworm@"
    "sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba"
)
RUNTIME_DOCKERFILE = Path(
    "benchmarks/clean-runners/bounded-planar-supplemental/Dockerfile"
)
RUNTIME_RUNNER = Path(
    "benchmarks/clean-runners/bounded-planar-supplemental/run_family.py"
)
CONTROL_PATHS = (
    RUNTIME_DOCKERFILE,
    RUNTIME_RUNNER,
    Path("scripts/bounded_planar_runtime_lock.py"),
)

REQUIREMENTS_TEXT = f"""\
openseespy=={OPENSEESPY_VERSION} \\
    --hash=sha256:{OPENSEESPY_WHEEL_SHA256}
openseespylinux=={OPENSEESPY_VERSION} \\
    --hash=sha256:{OPENSEESPY_LINUX_WHEEL_SHA256}
"""

EXPECTED_WHEEL_HASHES = {
    "openseespy": OPENSEESPY_WHEEL_SHA256,
    "openseespylinux": OPENSEESPY_LINUX_WHEEL_SHA256,
}
EXPECTED_WHEEL_SOURCES = {
    "openseespy": "https://pypi.org/project/openseespy/3.7.1.2/",
    "openseespylinux": "https://pypi.org/project/openseespylinux/3.7.1.2/",
}

EXTERNAL_ASSET_POLICY: dict[str, dict[str, str]] = {
    "openseespy": {
        "filename": "openseespy-3.7.1.2-py3-none-any.whl",
        "file_sha256": "sha256:" + OPENSEESPY_WHEEL_SHA256,
        "kind": "python_wheel",
        "version": OPENSEESPY_VERSION,
        "source": EXPECTED_WHEEL_SOURCES["openseespy"],
    },
    "openseespylinux": {
        "filename": "openseespylinux-3.7.1.2-py3-none-any.whl",
        "file_sha256": "sha256:" + OPENSEESPY_LINUX_WHEEL_SHA256,
        "kind": "python_wheel",
        "version": OPENSEESPY_VERSION,
        "source": EXPECTED_WHEEL_SOURCES["openseespylinux"],
    },
    "calculix-ccx": {
        "filename": "calculix-ccx_2.17-3_amd64.deb",
        "file_sha256": "sha256:3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e",
        "kind": "debian_package",
        "version": "2.17-3",
        "source": "https://packages.ubuntu.com/jammy/calculix-ccx",
    },
    "libarpack2": {
        "filename": "libarpack2_3.8.0-1_amd64.deb",
        "file_sha256": "sha256:07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a",
        "kind": "debian_package",
        "version": "3.8.0-1",
        "source": "https://packages.ubuntu.com/jammy/libarpack2",
    },
    "libspooles2.2": {
        "filename": "libspooles2.2_2.2-14_amd64.deb",
        "file_sha256": "sha256:34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917",
        "kind": "debian_package",
        "version": "2.2-14",
        "source": "https://packages.ubuntu.com/jammy/libspooles2.2",
    },
}

OPENSEES_ASSET_IDS = ("openseespy", "openseespylinux")
FAMILY_ASSET_IDS = {
    "linear": OPENSEES_ASSET_IDS,
    "negative": OPENSEES_ASSET_IDS,
    "scaling": OPENSEES_ASSET_IDS,
    "modal_buckling": (
        *OPENSEES_ASSET_IDS,
        "calculix-ccx",
        "libarpack2",
        "libspooles2.2",
    ),
    "nonlinear_material_recovery": OPENSEES_ASSET_IDS,
}

EXECUTION_POLICY = {
    "image_selected_by_content_address": True,
    "network_disabled": True,
    "root_filesystem_read_only": True,
    "repository_mount_read_only": True,
    "asset_mount_read_only": True,
    "capabilities_dropped": True,
    "no_new_privileges": True,
    "docker_socket_mounted": False,
    "only_persistent_result_mount_writable": True,
}

CLAIM_BOUNDARY = (
    "The local OCI image and named external assets were content-addressed "
    "before a no-network execution. This supports same-operator technical "
    "freshness only; it is not redistribution or legal-use approval, independent "
    "reproduction, Verification Level 2, or release authority."
)

TOP_LEVEL_KEYS = {
    "schema_version",
    "family_id",
    "source_commit_sha",
    "source_tree_sha",
    "prepared_at",
    "lock_mode",
    "prepared_before_external_execution",
    "networked_acquisition_completed_before_lock",
    "control_files",
    "container_image",
    "external_assets",
    "execution_policy",
    "runtime_asset_bytes_attached",
    "runtime_asset_metadata_sealed",
    "same_operator_technical_credit_only",
    "claim_boundary",
    "artifact_hash",
}

CONTAINER_IMAGE_KEYS = {
    "base_image",
    "derived_image_id",
    "rootfs_layer_diff_ids",
    "os",
    "architecture",
    "content_addressed_before_execution",
    "published",
}


class RuntimeLockError(ValueError):
    """Stable fail-closed runtime-lock error."""


def _fail(code: str) -> NoReturn:
    raise RuntimeLockError(code)


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


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            _fail(f"runtime_lock_duplicate_json_key:{key}")
        payload[key] = value
    return payload


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        _fail("runtime_lock_nonfinite_json_number")
    return value


def _load_json(path: Path, code: str) -> object:
    try:
        return json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _token: _fail("runtime_lock_nonfinite_json_number"),
            parse_float=_finite_float,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeLockError(code) from exc


def load_preexecution_lock(path: Path) -> object:
    """Load one runtime lock through the strict JSON byte boundary."""

    return _load_json(path, "runtime_lock_invalid")


def _binding(repo_root: Path, relative: Path) -> dict[str, Any]:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("runtime_lock_control_path_invalid")
    path = repo_root / relative
    if path.is_symlink() or not path.is_file():
        _fail("runtime_lock_control_path_invalid")
    raw = path.read_bytes()
    return {
        "path": relative.as_posix(),
        "file_sha256": _hash_bytes(raw),
        "size": len(raw),
    }


def requirements_bytes() -> bytes:
    return REQUIREMENTS_TEXT.encode("utf-8")


def validate_requirements_text(value: str) -> None:
    observed = {
        package: digest
        for package, digest in re.findall(
            r"(?m)^(openseespy|openseespylinux)==3\.7\.1\.2\s+\\\n"
            r"\s+--hash=sha256:([0-9a-f]{64})$",
            value,
        )
    }
    if observed != EXPECTED_WHEEL_HASHES or value != REQUIREMENTS_TEXT:
        raise ValueError("bounded_planar_openseespy_lock_invalid")


def expected_assets(family_id: str) -> list[dict[str, str]]:
    asset_ids = FAMILY_ASSET_IDS.get(family_id)
    if asset_ids is None:
        _fail("runtime_lock_family_invalid")
    return [
        {"asset_id": asset_id, **EXTERNAL_ASSET_POLICY[asset_id]}
        for asset_id in asset_ids
    ]


def bind_external_assets(*, family_id: str, asset_dir: Path) -> list[dict[str, Any]]:
    try:
        resolved = asset_dir.resolve(strict=True)
    except OSError as exc:
        raise RuntimeLockError("runtime_lock_asset_directory_invalid") from exc
    if not resolved.is_dir() or asset_dir.is_symlink():
        _fail("runtime_lock_asset_directory_invalid")
    expected = expected_assets(family_id)
    expected_names = {row["filename"] for row in expected}
    actual_names = {path.name for path in resolved.iterdir() if path.is_file()}
    if actual_names != expected_names:
        _fail("runtime_lock_asset_set_invalid")
    bindings: list[dict[str, Any]] = []
    for row in expected:
        path = resolved / row["filename"]
        if path.is_symlink() or not path.is_file():
            _fail("runtime_lock_asset_invalid")
        if _file_hash(path) != row["file_sha256"]:
            _fail(f"runtime_lock_asset_hash_invalid:{row['asset_id']}")
        bindings.append({**row, "size": path.stat().st_size})
    return bindings


def _validate_control_files(
    *, payload: object, repo_root: Path
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        _fail("runtime_lock_control_binding_invalid")
    expected = [_binding(repo_root, path) for path in CONTROL_PATHS]
    if payload != expected:
        _fail("runtime_lock_control_binding_invalid")
    dockerfile = (repo_root / RUNTIME_DOCKERFILE).read_text(encoding="utf-8")
    if dockerfile.splitlines()[0] != f"FROM {BASE_IMAGE}":
        _fail("runtime_lock_base_image_declaration_invalid")
    return expected


def validate_preexecution_lock_payload(
    payload: object,
    *,
    repo_root: Path,
    family_id: str,
    source_commit_sha: str | None = None,
    source_tree_sha: str | None = None,
    asset_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate a lock; asset bytes are required at the producer boundary only."""

    if not isinstance(payload, dict):
        _fail("runtime_lock_invalid")
    image = payload.get("container_image")
    execution = payload.get("execution_policy")
    assets = payload.get("external_assets")
    expected = expected_assets(family_id)
    if (
        set(payload) != TOP_LEVEL_KEYS
        or payload.get("schema_version") != SCHEMA_VERSION
        or payload.get("artifact_hash") != _artifact_hash(payload)
        or payload.get("family_id") != family_id
        or not SHA1.fullmatch(str(payload.get("source_commit_sha")))
        or not SHA1.fullmatch(str(payload.get("source_tree_sha")))
        or payload.get("lock_mode")
        != "local_content_addressed_oci_image_plus_hash_locked_assets"
        or payload.get("prepared_before_external_execution") is not True
        or payload.get("networked_acquisition_completed_before_lock") is not True
        or payload.get("runtime_asset_bytes_attached") is not False
        or payload.get("runtime_asset_metadata_sealed") is not True
        or payload.get("same_operator_technical_credit_only") is not True
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
        or not isinstance(image, dict)
        or set(image) != CONTAINER_IMAGE_KEYS
        or image.get("base_image") != BASE_IMAGE
        or not SHA256.fullmatch(str(image.get("derived_image_id")))
        or image.get("os") != "linux"
        or image.get("architecture") != "amd64"
        or image.get("content_addressed_before_execution") is not True
        or image.get("published") is not False
        or not isinstance(image.get("rootfs_layer_diff_ids"), list)
        or not image["rootfs_layer_diff_ids"]
        or any(
            not SHA256.fullmatch(str(row)) for row in image["rootfs_layer_diff_ids"]
        )
        or execution != EXECUTION_POLICY
        or not isinstance(assets, list)
        or len(assets) != len(expected)
    ):
        _fail("runtime_lock_invalid")
    if source_commit_sha is not None and payload["source_commit_sha"] != source_commit_sha:
        _fail("runtime_lock_source_commit_mismatch")
    if source_tree_sha is not None and payload["source_tree_sha"] != source_tree_sha:
        _fail("runtime_lock_source_tree_mismatch")
    try:
        prepared = datetime.fromisoformat(
            str(payload["prepared_at"]).replace("Z", "+00:00")
        )
    except (KeyError, ValueError) as exc:
        raise RuntimeLockError("runtime_lock_prepared_at_invalid") from exc
    if prepared.tzinfo is None or prepared.utcoffset() is None:
        _fail("runtime_lock_prepared_at_invalid")
    _validate_control_files(payload=payload.get("control_files"), repo_root=repo_root)
    for observed, policy in zip(assets, expected, strict=True):
        if (
            not isinstance(observed, dict)
            or set(observed) != {*policy, "size"}
            or any(observed.get(key) != value for key, value in policy.items())
            or type(observed.get("size")) is not int
            or observed.get("size", 0) < 1
        ):
            _fail("runtime_lock_asset_metadata_invalid")
    if asset_dir is not None and assets != bind_external_assets(
        family_id=family_id, asset_dir=asset_dir
    ):
        _fail("runtime_lock_asset_binding_invalid")
    return payload


def build_preexecution_lock(
    *,
    repo_root: Path,
    family_id: str,
    source_commit_sha: str,
    source_tree_sha: str,
    asset_dir: Path,
    image_inspect_path: Path,
    prepared_at: str | None = None,
) -> dict[str, Any]:
    if not SHA1.fullmatch(source_commit_sha) or not SHA1.fullmatch(source_tree_sha):
        _fail("runtime_lock_source_identity_invalid")
    inspected = _load_json(image_inspect_path, "runtime_lock_image_inspect_invalid")
    if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(
        inspected[0], dict
    ):
        _fail("runtime_lock_image_inspect_invalid")
    image = inspected[0]
    rootfs = image.get("RootFS")
    image_id = image.get("Id")
    layers = rootfs.get("Layers") if isinstance(rootfs, dict) else None
    if (
        not SHA256.fullmatch(str(image_id))
        or image.get("Os") != "linux"
        or image.get("Architecture") != "amd64"
        or not isinstance(layers, list)
        or not layers
        or any(not SHA256.fullmatch(str(row)) for row in layers)
    ):
        _fail("runtime_lock_image_inspect_invalid")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "family_id": family_id,
        "source_commit_sha": source_commit_sha,
        "source_tree_sha": source_tree_sha,
        "prepared_at": prepared_at or datetime.now(timezone.utc).isoformat(),
        "lock_mode": "local_content_addressed_oci_image_plus_hash_locked_assets",
        "prepared_before_external_execution": True,
        "networked_acquisition_completed_before_lock": True,
        "control_files": [_binding(repo_root, path) for path in CONTROL_PATHS],
        "container_image": {
            "base_image": BASE_IMAGE,
            "derived_image_id": image_id,
            "rootfs_layer_diff_ids": layers,
            "os": "linux",
            "architecture": "amd64",
            "content_addressed_before_execution": True,
            "published": False,
        },
        "external_assets": bind_external_assets(
            family_id=family_id, asset_dir=asset_dir
        ),
        "execution_policy": dict(EXECUTION_POLICY),
        "runtime_asset_bytes_attached": False,
        "runtime_asset_metadata_sealed": True,
        "same_operator_technical_credit_only": True,
        "claim_boundary": CLAIM_BOUNDARY,
        "artifact_hash": ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return validate_preexecution_lock_payload(
        payload,
        repo_root=repo_root,
        family_id=family_id,
        source_commit_sha=source_commit_sha,
        source_tree_sha=source_tree_sha,
        asset_dir=asset_dir,
    )


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--family-id", choices=sorted(FAMILY_ASSET_IDS), required=True)
    prepare.add_argument("--source-sha", required=True)
    prepare.add_argument("--source-tree-sha", required=True)
    prepare.add_argument("--asset-dir", type=Path, required=True)
    prepare.add_argument("--image-inspect", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    image_id = subparsers.add_parser("image-id")
    image_id.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "prepare":
            payload = build_preexecution_lock(
                repo_root=ROOT,
                family_id=args.family_id,
                source_commit_sha=args.source_sha,
                source_tree_sha=args.source_tree_sha,
                asset_dir=args.asset_dir,
                image_inspect_path=args.image_inspect,
            )
            _write(ROOT / args.out, payload)
            print(payload["artifact_hash"])
            return 0
        payload = load_preexecution_lock(ROOT / args.manifest)
        if not isinstance(payload, dict):
            _fail("runtime_lock_invalid")
        validated = validate_preexecution_lock_payload(
            payload,
            repo_root=ROOT,
            family_id=str(payload.get("family_id")),
        )
        print(validated["container_image"]["derived_image_id"])
        return 0
    except RuntimeLockError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
