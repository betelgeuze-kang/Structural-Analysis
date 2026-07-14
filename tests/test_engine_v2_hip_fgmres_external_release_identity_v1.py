from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_external_release_identity_v1 as release_identity,
)
from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)


def _hash(label: str) -> str:
    return sha256_prefixed(label.encode("utf-8"))


def _recipe_bytes(
    *,
    wheel_filename: str,
    dependency_lock_sha256: str,
    target_environment_hash: str,
    overrides: dict[str, Any] | None = None,
    preserve_hash: bool = False,
) -> bytes:
    payload: dict[str, Any] = {
        "schema_version": (
            release_identity.HIP_FGMRES_EXTERNAL_BUILD_RECIPE_SCHEMA_VERSION_V1
        ),
        "policy_id": "isolated_pep517_verified_source_bundle_v1",
        "build_frontend": "pypa-build",
        "build_backend": "setuptools.build_meta",
        "argv": [
            "python",
            "-m",
            "build",
            "--wheel",
            "--outdir",
            "dist",
            ".",
        ],
        "environment": {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_FIND_LINKS": "dependency-wheelhouse",
            "PIP_NO_INDEX": "1",
            "PYTHONHASHSEED": "0",
            "SOURCE_DATE_EPOCH": "1720915200",
            "TZ": "UTC",
        },
        "source_date_epoch": 1720915200,
        "candidate_wheel_filename": wheel_filename,
        "dependency_lock_sha256": dependency_lock_sha256,
        "target_environment_hash": target_environment_hash,
    }
    payload["recipe_hash"] = canonical_hash(payload)
    if overrides:
        payload.update(overrides)
        if not preserve_hash and "recipe_hash" not in overrides:
            payload.pop("recipe_hash")
            payload["recipe_hash"] = canonical_hash(payload)
    return canonical_json_bytes(payload)


def _material() -> SimpleNamespace:
    wheel_filename = "structural_optimization_workbench-0.2.34-py3-none-any.whl"
    lock_raw = canonical_json_bytes({"fixture": "dependency-lock"})
    lock_sha256 = sha256_prefixed(lock_raw)
    target_environment_hash = _hash("target-environment")
    recipe_raw = _recipe_bytes(
        wheel_filename=wheel_filename,
        dependency_lock_sha256=lock_sha256,
        target_environment_hash=target_environment_hash,
    )
    wheel = SimpleNamespace(
        wheel_filename=wheel_filename,
        canonical_distribution_name="structural-optimization-workbench",
        distribution_version="0.2.34",
        canonical_distribution_version="0.2.34",
        requires_dist=(),
        byte_count=123_456,
        sha256=_hash("wheel"),
        record_sha256=_hash("wheel-record"),
        member_count=5,
        identity_hash=_hash("wheel-identity"),
        console_scripts=(),
        gui_scripts=(),
    )
    installed = SimpleNamespace(
        wheel_identity=wheel,
        replay_hash=_hash("installed-replay"),
        verified_wheel_member_count=4,
        extra_file_count=0,
        script_file_count=0,
        script_manifest_sha256=_hash("installed-script-manifest"),
    )
    source = SimpleNamespace(
        identity_hash=_hash("source-identity"),
        source_commit="a" * 40,
        source_tree_sha256=_hash("source-tree"),
        source_manifest=SimpleNamespace(file_count=7),
        source_bundle_byte_count=65_536,
        source_bundle_sha256=_hash("source-bundle"),
        runner_source_paths=("runner/main.py", "runner/support.py"),
        runner_source_sha256=_hash("runner-sources"),
        build_recipe_sha256=sha256_prefixed(recipe_raw),
        dependency_lock_sha256=lock_sha256,
    )
    dependency = SimpleNamespace(
        receipt_hash=_hash("dependency-receipt"),
        lock_bytes_sha256=lock_sha256,
        target_environment_hash=target_environment_hash,
        root_distribution_name=wheel.canonical_distribution_name,
        root_distribution_version=wheel.canonical_distribution_version,
        root_filename=wheel.wheel_filename,
        root_byte_count=wheel.byte_count,
        root_sha256=wheel.sha256,
        root_requires_dist=wheel.requires_dist,
        root_wheel_identity_hash=wheel.identity_hash,
        artifact_count=3,
        artifact_aggregate_hash=_hash("dependency-artifact-aggregate"),
    )
    binding = SimpleNamespace(
        binding_hash=_hash("release-binding"),
        wheel_filename=wheel.wheel_filename,
        wheel_byte_count=wheel.byte_count,
        wheel_sha256=wheel.sha256,
        wheel_record_sha256=wheel.record_sha256,
        source_commit=source.source_commit,
        source_tree_sha256=source.source_tree_sha256,
        source_bundle_sha256=source.source_bundle_sha256,
        runner_source_sha256=source.runner_source_sha256,
        build_recipe_sha256=source.build_recipe_sha256,
        dependency_lock_sha256=source.dependency_lock_sha256,
    )
    recipe = release_identity._BuildRecipeV1(
        semantic_hash=json.loads(recipe_raw)["recipe_hash"],
        raw_sha256=sha256_prefixed(recipe_raw),
    )
    return SimpleNamespace(
        wheel=wheel,
        installed=installed,
        source=source,
        dependency=dependency,
        binding=binding,
        recipe=recipe,
        recipe_raw=recipe_raw,
        lock_raw=lock_raw,
    )


def _receipt() -> release_identity.HipFgmresExternalReleaseIdentityReceiptV1:
    material = _material()
    return release_identity._compile_receipt(
        binding=material.binding,
        wheel=material.wheel,
        installed=material.installed,
        source=material.source,
        dependency=material.dependency,
        recipe=material.recipe,
    )


def _paths(tmp_path: Path) -> release_identity.HipFgmresExternalReleaseArtifactPathsV1:
    repository = tmp_path / "repository"
    artifacts = tmp_path / "artifacts"
    dependencies = tmp_path / "dependency-wheelhouse"
    repository.mkdir(exist_ok=True)
    artifacts.mkdir(exist_ok=True)
    dependencies.mkdir(exist_ok=True)
    return release_identity.HipFgmresExternalReleaseArtifactPathsV1(
        repository_root=os.fspath(repository),
        artifact_root=os.fspath(artifacts),
        wheel_filename=("structural_optimization_workbench-0.2.34-py3-none-any.whl"),
        source_bundle_filename="source.tar",
        runner_source_paths=("runner/main.py", "runner/support.py"),
        build_recipe_path="release/build-recipe.json",
        dependency_lock_path="release/dependency-lock.json",
        dependency_artifact_root=os.fspath(dependencies),
    )


def _patch_compile_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    material: SimpleNamespace,
    *,
    inspected_wheels: list[SimpleNamespace] | None = None,
    installed: SimpleNamespace | None = None,
    source: SimpleNamespace | None = None,
    dependency: SimpleNamespace | None = None,
) -> dict[str, Any]:
    wheels = iter(inspected_wheels or [material.wheel, material.wheel])
    captured: dict[str, Any] = {
        "wheel_inspection_count": 0,
        "installed_replay_count": 0,
        "source_replay_count": 0,
        "dependency_replay_count": 0,
        "role_reads": [],
        "alias_check_count": 0,
    }

    def inspect_wheel(_path: str) -> SimpleNamespace:
        captured["wheel_inspection_count"] += 1
        return next(wheels)

    monkeypatch.setattr(
        release_identity,
        "inspect_wheel_artifact_v1",
        inspect_wheel,
    )
    monkeypatch.setattr(
        release_identity,
        "validate_wheel_artifact_identity_v1",
        lambda _value: None,
    )
    monkeypatch.setattr(
        release_identity.metadata,
        "version",
        lambda _name: material.wheel.distribution_version,
    )
    monkeypatch.setattr(
        release_identity,
        "_current_installed_distribution_root",
        lambda _wheel: "/installed",
    )

    def replay_installed(**_kwargs: Any) -> SimpleNamespace:
        captured["installed_replay_count"] += 1
        return installed or material.installed

    monkeypatch.setattr(
        release_identity, "replay_installed_wheel_artifact_v1", replay_installed
    )
    monkeypatch.setattr(
        release_identity,
        "validate_installed_wheel_replay_v1",
        lambda _value: None,
    )

    def replay_source(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        captured["source_replay_count"] += 1
        return source or material.source

    monkeypatch.setattr(
        release_identity, "compile_source_artifact_identity_v1", replay_source
    )
    monkeypatch.setattr(
        release_identity,
        "validate_source_artifact_identity_v1",
        lambda _value: None,
    )
    role_bytes = {
        "release/build-recipe.json": material.recipe_raw,
        "release/dependency-lock.json": material.lock_raw,
    }

    def read_role(_root: str, relative: str, *, byte_limit: int) -> bytes:
        captured["role_reads"].append((relative, byte_limit))
        return role_bytes[relative]

    monkeypatch.setattr(release_identity, "_read_source_role_file", read_role)

    def replay_dependency(*_args: Any, **_kwargs: Any) -> SimpleNamespace:
        captured["dependency_replay_count"] += 1
        return dependency or material.dependency

    monkeypatch.setattr(
        release_identity,
        "verify_dependency_artifact_lock_v1",
        replay_dependency,
    )
    monkeypatch.setattr(
        release_identity,
        "validate_dependency_lock_receipt_v1",
        lambda _value: None,
    )

    def compile_binding(**kwargs: Any) -> SimpleNamespace:
        captured["binding_kwargs"] = kwargs
        return material.binding

    monkeypatch.setattr(
        release_identity,
        "compile_hip_fgmres_external_release_binding_v1",
        compile_binding,
    )
    monkeypatch.setattr(
        release_identity,
        "validate_hip_fgmres_external_release_binding_v1",
        lambda _value: None,
    )

    def check_aliases(*_args: Any, **_kwargs: Any) -> None:
        captured["alias_check_count"] += 1

    monkeypatch.setattr(release_identity, "_reject_cross_role_aliases", check_aliases)
    return captured


def _assert_error(
    code: str,
    function: Any,
    /,
    *args: Any,
    **kwargs: Any,
) -> release_identity.HipFgmresExternalReleaseIdentityV1Error:
    with pytest.raises(
        release_identity.HipFgmresExternalReleaseIdentityV1Error
    ) as captured:
        function(*args, **kwargs)
    assert captured.value.code == code
    assert captured.value.path.startswith("/")
    return captured.value


def test_receipt_schema_hash_and_claims_are_exact_and_tamper_evident() -> None:
    receipt = _receipt()

    assert (
        release_identity.validate_hip_fgmres_external_release_identity_receipt_v1(
            receipt
        )
        is receipt
    )
    payload = receipt.to_dict()
    assert payload["receipt_hash"] == canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )
    assert payload["claims"]["wheel_bytes_independently_hashed"] is True
    assert payload["claims"]["declared_build_recipe_policy_matched"] is True
    assert (
        payload["claims"]["declared_target_runtime_dependency_closure_matched"] is True
    )
    assert payload["claims"]["build_recipe_execution_observed"] is False
    assert payload["claims"]["build_system_dependency_closure_verified"] is False
    assert payload["claims"]["runtime_dependency_installation_observed"] is False
    assert (
        payload["claims"]["current_interpreter_wheel_tag_compatibility_verified"]
        is False
    )
    assert payload["claims"]["bounded_source_artifact_memory_verified"] is False
    assert payload["claims"]["hostile_in_process_mint_isolation_verified"] is False
    assert payload["claims"]["atomic_multi_artifact_snapshot_verified"] is False
    assert payload["claims"]["signed_envelope_binds_release_identity_receipt"] is False
    assert payload["claims"]["promotion_eligible"] is False
    assert payload["promotion_eligible"] is False
    assert payload["evidence_scope"] == (
        "local_double_replay_sequential_release_artifact_identity_non_promoting"
    )

    _assert_error(
        "hip_fgmres_external_release_identity_receipt_invalid",
        release_identity.validate_hip_fgmres_external_release_identity_receipt_v1,
        replace(receipt, wheel_sha256=_hash("substituted-wheel")),
    )
    _assert_error(
        "hip_fgmres_external_release_identity_schema_validation_failed",
        release_identity.validate_hip_fgmres_external_release_identity_receipt_v1,
        replace(receipt, wheel_byte_count=True),
    )
    release_identity._validate_schema(payload)
    _assert_error(
        "hip_fgmres_external_release_identity_schema_validation_failed",
        release_identity._validate_schema,
        {**payload, "unexpected": True},
    )


def test_paths_reject_malformed_types_and_source_roles(tmp_path: Path) -> None:
    _assert_error(
        "hip_fgmres_external_release_artifact_paths_type_invalid",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths={"repository_root": os.fspath(tmp_path)},
    )
    paths = _paths(tmp_path)
    _assert_error(
        "hip_fgmres_external_release_source_roles_invalid",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=replace(paths, runner_source_paths=["runner.py"]),  # type: ignore[arg-type]
    )
    _assert_error(
        "hip_fgmres_external_release_source_path_invalid",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=replace(paths, runner_source_paths=("../runner.py",)),
    )


def test_paths_reject_cross_role_hardlink_alias_before_verification(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    repository = Path(paths.repository_root)
    for relative in (
        *paths.runner_source_paths,
        paths.build_recipe_path,
        paths.dependency_lock_path,
    ):
        target = repository / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.encode("utf-8"))
    wheel = Path(paths.artifact_root) / paths.wheel_filename
    bundle = Path(paths.artifact_root) / paths.source_bundle_filename
    wheel.write_bytes(b"placeholder wheel")
    os.link(wheel, bundle)

    _assert_error(
        "hip_fgmres_external_release_artifact_alias",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=paths,
    )


def test_exact_build_recipe_policy_and_semantic_hash_are_accepted() -> None:
    material = _material()

    recipe = release_identity._validate_build_recipe(
        material.recipe_raw,
        wheel=material.wheel,
        source=material.source,
        dependency=material.dependency,
    )

    assert recipe.semantic_hash == json.loads(material.recipe_raw)["recipe_hash"]
    assert recipe.raw_sha256 == sha256_prefixed(material.recipe_raw)


@pytest.mark.parametrize(
    ("raw_factory", "code"),
    [
        (
            lambda material: _recipe_bytes(
                wheel_filename=material.wheel.wheel_filename,
                dependency_lock_sha256=material.source.dependency_lock_sha256,
                target_environment_hash=material.dependency.target_environment_hash,
                overrides={"policy_id": "unverified_local_build"},
            ),
            "hip_fgmres_external_release_build_recipe_invalid",
        ),
        (
            lambda material: _recipe_bytes(
                wheel_filename=material.wheel.wheel_filename,
                dependency_lock_sha256=material.source.dependency_lock_sha256,
                target_environment_hash=material.dependency.target_environment_hash,
                overrides={"recipe_hash": _hash("forged-recipe")},
            ),
            "hip_fgmres_external_release_build_recipe_hash_mismatch",
        ),
        (
            lambda material: material.recipe_raw + b"\n",
            "hip_fgmres_external_release_json_not_canonical",
        ),
    ],
)
def test_build_recipe_policy_hash_and_canonical_bytes_fail_closed(
    raw_factory: Any,
    code: str,
) -> None:
    material = _material()
    _assert_error(
        code,
        release_identity._validate_build_recipe,
        raw_factory(material),
        wheel=material.wheel,
        source=material.source,
        dependency=material.dependency,
    )


def test_compile_wires_only_verified_artifact_identities_into_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    captured = _patch_compile_pipeline(monkeypatch, material)

    verified = release_identity.compile_hip_fgmres_external_release_identity_v1(
        paths=_paths(tmp_path)
    )

    assert type(verified) is release_identity.HipFgmresExternalVerifiedReleaseV1
    assert verified.release_binding is material.binding
    assert (
        verified.identity_receipt.release_binding_hash == material.binding.binding_hash
    )
    assert captured["binding_kwargs"] == {
        "wheel_filename": material.wheel.wheel_filename,
        "wheel_byte_count": material.wheel.byte_count,
        "wheel_sha256": material.wheel.sha256,
        "wheel_record_sha256": material.wheel.record_sha256,
        "source_commit": material.source.source_commit,
        "source_tree_sha256": material.source.source_tree_sha256,
        "source_bundle_sha256": material.source.source_bundle_sha256,
        "runner_source_sha256": material.source.runner_source_sha256,
        "build_recipe_sha256": material.source.build_recipe_sha256,
        "dependency_lock_sha256": material.source.dependency_lock_sha256,
    }
    assert captured["wheel_inspection_count"] == 2
    assert captured["installed_replay_count"] == 2
    assert captured["source_replay_count"] == 2
    assert captured["dependency_replay_count"] == 2
    assert captured["alias_check_count"] == 2
    assert [relative for relative, _limit in captured["role_reads"]] == [
        "release/build-recipe.json",
        "release/dependency-lock.json",
        "release/build-recipe.json",
        "release/dependency-lock.json",
    ]


def test_compile_rejects_cross_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    mismatched_dependency = SimpleNamespace(
        **{
            **vars(material.dependency),
            "root_sha256": _hash("different-root-wheel"),
        }
    )
    _patch_compile_pipeline(
        monkeypatch,
        material,
        dependency=mismatched_dependency,
    )

    _assert_error(
        "hip_fgmres_external_release_component_binding_mismatch",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=_paths(tmp_path),
    )


def test_compile_rejects_installed_wheel_identity_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    other_wheel = SimpleNamespace(
        **{**vars(material.wheel), "sha256": _hash("installed-other-wheel")}
    )
    installed = SimpleNamespace(
        **{**vars(material.installed), "wheel_identity": other_wheel}
    )
    _patch_compile_pipeline(monkeypatch, material, installed=installed)

    _assert_error(
        "hip_fgmres_external_release_wheel_changed",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=_paths(tmp_path),
    )


def test_compile_rejects_wheel_drift_during_postflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    drifted = SimpleNamespace(
        **{**vars(material.wheel), "sha256": _hash("postflight-wheel")}
    )
    _patch_compile_pipeline(
        monkeypatch,
        material,
        inspected_wheels=[material.wheel, drifted],
    )

    _assert_error(
        "hip_fgmres_external_release_wheel_changed",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=_paths(tmp_path),
    )


@pytest.mark.parametrize(
    ("component", "code"),
    [
        (
            "installed",
            "hip_fgmres_external_release_installed_distribution_changed",
        ),
        ("source", "hip_fgmres_external_release_source_changed"),
        ("source_role", "hip_fgmres_external_release_source_role_drift"),
        ("dependency", "hip_fgmres_external_release_dependency_changed"),
        ("recipe", "hip_fgmres_external_release_build_recipe_changed"),
    ],
)
def test_compile_rejects_each_second_replay_drift(
    component: str,
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    _patch_compile_pipeline(monkeypatch, material)

    if component == "installed":
        drifted = SimpleNamespace(
            **{**vars(material.installed), "replay_hash": _hash("installed-drift")}
        )
        values = iter((material.installed, drifted))
        monkeypatch.setattr(
            release_identity,
            "replay_installed_wheel_artifact_v1",
            lambda **_kwargs: next(values),
        )
    elif component == "source":
        drifted = SimpleNamespace(
            **{**vars(material.source), "identity_hash": _hash("source-drift")}
        )
        values = iter((material.source, drifted))
        monkeypatch.setattr(
            release_identity,
            "compile_source_artifact_identity_v1",
            lambda *_args, **_kwargs: next(values),
        )
    elif component == "source_role":
        values = iter(
            (
                material.recipe_raw,
                material.lock_raw,
                material.recipe_raw + b" ",
                material.lock_raw,
            )
        )
        monkeypatch.setattr(
            release_identity,
            "_read_source_role_file",
            lambda *_args, **_kwargs: next(values),
        )
    elif component == "dependency":
        drifted = SimpleNamespace(
            **{
                **vars(material.dependency),
                "receipt_hash": _hash("dependency-drift"),
            }
        )
        values = iter((material.dependency, drifted))
        monkeypatch.setattr(
            release_identity,
            "verify_dependency_artifact_lock_v1",
            lambda *_args, **_kwargs: next(values),
        )
    else:
        drifted = replace(
            material.recipe,
            semantic_hash=_hash("build-recipe-drift"),
        )
        values = iter((material.recipe, drifted))
        monkeypatch.setattr(
            release_identity,
            "_validate_build_recipe",
            lambda *_args, **_kwargs: next(values),
        )

    _assert_error(
        code,
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=_paths(tmp_path),
    )


def test_compile_maps_missing_distribution_metadata_to_stable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    _patch_compile_pipeline(monkeypatch, material)

    def missing(_name: str) -> str:
        raise release_identity.metadata.PackageNotFoundError("missing")

    monkeypatch.setattr(release_identity.metadata, "version", missing)
    _assert_error(
        "hip_fgmres_external_release_distribution_missing",
        release_identity.compile_hip_fgmres_external_release_identity_v1,
        paths=_paths(tmp_path),
    )


def test_process_local_capabilities_reject_direct_and_object_new_forgery(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    receipt = _receipt()
    binding = SimpleNamespace(binding_hash=receipt.release_binding_hash)

    _assert_error(
        "hip_fgmres_external_verified_release_construction_forbidden",
        release_identity.HipFgmresExternalVerifiedReleaseV1,
        paths=paths,
        release_binding=binding,
        identity_receipt=receipt,
        mint=object(),
    )
    _assert_error(
        "hip_fgmres_external_verified_signed_evidence_construction_forbidden",
        release_identity.HipFgmresExternalVerifiedSignedEvidenceV1,
        identity_receipt=receipt,
        signed_receipt=SimpleNamespace(
            release_binding_hash=receipt.release_binding_hash
        ),
        mint=object(),
    )

    forged = object.__new__(release_identity.HipFgmresExternalVerifiedReleaseV1)
    object.__setattr__(forged, "_paths", paths)
    object.__setattr__(forged, "_release_binding", binding)
    object.__setattr__(forged, "_identity_receipt", receipt)
    object.__setattr__(forged, "_mint", object())
    _assert_error(
        "hip_fgmres_external_verified_release_invalid",
        release_identity._validate_verified_release,
        forged,
    )


def test_signed_wrapper_binds_identity_and_signed_receipts_to_same_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material = _material()
    _patch_compile_pipeline(monkeypatch, material)
    verified = release_identity.compile_hip_fgmres_external_release_identity_v1(
        paths=_paths(tmp_path)
    )
    signed = SimpleNamespace(release_binding_hash=material.binding.binding_hash)
    captured: dict[str, Any] = {}

    def replay(value: Any) -> Any:
        captured["replayed"] = value
        return value

    def verify_signed(
        raw: bytes,
        *,
        challenge: Any,
        release_binding: Any,
    ) -> Any:
        captured.update(
            raw=raw,
            challenge=challenge,
            release_binding=release_binding,
        )
        return signed

    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_release_artifacts_v1",
        replay,
    )
    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_signed_evidence_v1",
        verify_signed,
    )
    monkeypatch.setattr(
        release_identity,
        "validate_hip_fgmres_external_signed_evidence_receipt_v1",
        lambda _value: None,
    )
    challenge = object()

    result = release_identity.verify_hip_fgmres_external_signed_evidence_for_verified_release_v1(
        b"signed-envelope",
        challenge=challenge,  # type: ignore[arg-type]
        verified_release=verified,
    )

    assert result.identity_receipt is verified.identity_receipt
    assert result.signed_receipt is signed
    assert captured == {
        "replayed": verified,
        "raw": b"signed-envelope",
        "challenge": challenge,
        "release_binding": verified.release_binding,
    }

    mismatched = SimpleNamespace(release_binding_hash=_hash("other-release"))
    monkeypatch.setattr(
        release_identity,
        "verify_hip_fgmres_external_signed_evidence_v1",
        lambda *_args, **_kwargs: mismatched,
    )
    _assert_error(
        "hip_fgmres_external_verified_signed_evidence_binding_mismatch",
        release_identity.verify_hip_fgmres_external_signed_evidence_for_verified_release_v1,
        b"signed-envelope",
        challenge=challenge,
        verified_release=verified,
    )
