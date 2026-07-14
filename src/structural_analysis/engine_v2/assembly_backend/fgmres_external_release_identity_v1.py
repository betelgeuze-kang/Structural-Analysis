"""Independently replay release artifacts before external FGMRES evidence.

This contract sits in front of the v1 signed-envelope verifier.  It derives the
existing release binding from actual wheel, installed distribution, clean Git
source/archive, runner sources, build recipe, and dependency-wheel closure.  It
double-replays those inputs sequentially; it does not provide an atomic
multi-artifact snapshot.  It also does not claim that the declared recipe was
executed, that two builds are reproducible, that its receipt hash is inside the
signed envelope, or that an external GPU actually ran.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from importlib import import_module, metadata, resources
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sysconfig
from typing import Any, Literal, NoReturn

from jsonschema import Draft202012Validator
from packaging.utils import canonicalize_name

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
    sha256_prefixed,
)
from structural_analysis.engine_v2.evidence.dependency_lock_v1 import (
    DependencyLockReceiptV1,
    validate_dependency_lock_receipt_v1,
    verify_dependency_artifact_lock_v1,
)
from structural_analysis.engine_v2.evidence.source_artifact_v1 import (
    SourceArtifactIdentityV1,
    compile_source_artifact_identity_v1,
    validate_source_artifact_identity_v1,
)
from structural_analysis.engine_v2.evidence.wheel_artifact_v1 import (
    InstalledWheelReplayV1,
    WheelArtifactIdentityV1,
    inspect_wheel_artifact_v1,
    replay_installed_wheel_artifact_v1,
    validate_installed_wheel_replay_v1,
    validate_wheel_artifact_identity_v1,
)

from .fgmres_external_signed_evidence_v1 import (
    HipFgmresExternalChallengeV1,
    HipFgmresExternalReleaseBindingV1,
    HipFgmresExternalSignedEvidenceReceiptV1,
    compile_hip_fgmres_external_release_binding_v1,
    issue_hip_fgmres_external_evidence_challenge_v1,
    validate_hip_fgmres_external_release_binding_v1,
    validate_hip_fgmres_external_signed_evidence_receipt_v1,
    verify_hip_fgmres_external_signed_evidence_v1,
)


HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-release-identity.v1"
)
HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_CAPABILITY_PROFILE_V1 = (
    "phase0_external_release_artifact_identity_replay"
)
HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_EVIDENCE_SCOPE_V1 = (
    "local_double_replay_sequential_release_artifact_identity_non_promoting"
)
HIP_FGMRES_EXTERNAL_BUILD_RECIPE_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-external-build-recipe.v1"
)

_STATUS = "external_release_artifacts_independently_verified"
_DISTRIBUTION_NAME = "structural-optimization-workbench"
_SCHEMA_RESOURCE = "hip_fgmres_external_release_identity_v1.schema.json"
_BUILD_POLICY_ID = "isolated_pep517_verified_source_bundle_v1"
_BUILD_FRONTEND = "pypa-build"
_BUILD_BACKEND = "setuptools.build_meta"
_BUILD_ARGV = (
    "python",
    "-m",
    "build",
    "--wheel",
    "--outdir",
    "dist",
    ".",
)
_BUILD_ENVIRONMENT_FIXED = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PIP_FIND_LINKS": "dependency-wheelhouse",
    "PIP_NO_INDEX": "1",
    "PYTHONHASHSEED": "0",
    "TZ": "UTC",
}
_ZERO_HASH = "sha256:" + "0" * 64
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]{0,254}$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_BUILD_RECIPE_MAX_BYTES = 1024 * 1024
_VERIFIED_RELEASE_MINT = object()
_VERIFIED_SIGNED_EVIDENCE_MINT = object()


class HipFgmresExternalReleaseIdentityV1Error(RuntimeError):
    """Stable fail-closed release-artifact identity error."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReleaseArtifactPathsV1:
    """Non-serialized paths used to replay one candidate release."""

    repository_root: str
    artifact_root: str
    wheel_filename: str
    source_bundle_filename: str
    runner_source_paths: tuple[str, ...]
    build_recipe_path: str
    dependency_lock_path: str
    dependency_artifact_root: str


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReleaseIdentityClaimsV1:
    wheel_bytes_independently_hashed: Literal[True] = True
    wheel_record_fully_replayed: Literal[True] = True
    installed_distribution_record_replayed: Literal[True] = True
    source_commit_and_manifest_replayed: Literal[True] = True
    source_worktree_clean: Literal[True] = True
    source_bundle_matches_manifest: Literal[True] = True
    runner_sources_independently_hashed: Literal[True] = True
    declared_build_recipe_policy_matched: Literal[True] = True
    dependency_artifacts_independently_hashed: Literal[True] = True
    declared_target_runtime_dependency_closure_matched: Literal[True] = True
    release_binding_derived_from_verified_artifacts: Literal[True] = True
    build_recipe_execution_observed: Literal[False] = False
    build_system_dependency_closure_verified: Literal[False] = False
    runtime_dependency_installation_observed: Literal[False] = False
    current_interpreter_wheel_tag_compatibility_verified: Literal[False] = False
    bounded_source_artifact_memory_verified: Literal[False] = False
    reproducible_build_verified: Literal[False] = False
    remote_commit_authenticity_verified: Literal[False] = False
    atomic_multi_artifact_snapshot_verified: Literal[False] = False
    signed_envelope_binds_release_identity_receipt: Literal[False] = False
    hostile_in_process_mint_isolation_verified: Literal[False] = False
    runner_honesty_verified: Literal[False] = False
    durable_replay_ledger_verified: Literal[False] = False
    hardware_root_attested: Literal[False] = False
    external_gpu_observed: Literal[False] = False
    same_artifact_two_architecture_verified: Literal[False] = False
    commercial_ready: Literal[False] = False
    promotion_eligible: Literal[False] = False

    def to_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HipFgmresExternalReleaseIdentityReceiptV1:
    schema_version: str
    capability_profile: str
    status: str
    evidence_scope: str
    release_binding_hash: str
    wheel_identity_hash: str
    installed_replay_hash: str
    source_identity_hash: str
    dependency_lock_receipt_hash: str
    build_recipe_semantic_hash: str
    wheel_filename: str
    wheel_byte_count: int
    wheel_sha256: str
    wheel_record_sha256: str
    wheel_member_count: int
    installed_verified_member_count: int
    installed_extra_file_count: int
    installed_script_file_count: int
    installed_script_manifest_sha256: str
    source_commit: str
    source_tree_sha256: str
    source_tracked_file_count: int
    source_bundle_byte_count: int
    source_bundle_sha256: str
    runner_source_file_count: int
    runner_source_sha256: str
    build_recipe_sha256: str
    dependency_lock_sha256: str
    dependency_artifact_count: int
    dependency_artifact_aggregate_hash: str
    claims: HipFgmresExternalReleaseIdentityClaimsV1
    promotion_eligible: bool
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_external_release_identity_receipt_v1(self)
        return _receipt_payload(self, include_hash=True)


class HipFgmresExternalVerifiedReleaseV1:
    """Process-local authority for paths whose artifacts were freshly replayed."""

    __slots__ = ("_paths", "_release_binding", "_identity_receipt", "_mint")

    def __init__(
        self,
        *,
        paths: HipFgmresExternalReleaseArtifactPathsV1,
        release_binding: HipFgmresExternalReleaseBindingV1,
        identity_receipt: HipFgmresExternalReleaseIdentityReceiptV1,
        mint: object,
    ) -> None:
        if mint is not _VERIFIED_RELEASE_MINT:
            _fail("hip_fgmres_external_verified_release_construction_forbidden", "/")
        self._paths = paths
        self._release_binding = release_binding
        self._identity_receipt = identity_receipt
        self._mint = mint

    @property
    def release_binding(self) -> HipFgmresExternalReleaseBindingV1:
        return self._release_binding

    @property
    def identity_receipt(self) -> HipFgmresExternalReleaseIdentityReceiptV1:
        return self._identity_receipt


class HipFgmresExternalVerifiedSignedEvidenceV1:
    """Process-local capability joining signed evidence to a replayed release."""

    __slots__ = ("_identity_receipt", "_signed_receipt", "_mint")

    def __init__(
        self,
        *,
        identity_receipt: HipFgmresExternalReleaseIdentityReceiptV1,
        signed_receipt: HipFgmresExternalSignedEvidenceReceiptV1,
        mint: object,
    ) -> None:
        if mint is not _VERIFIED_SIGNED_EVIDENCE_MINT:
            _fail(
                "hip_fgmres_external_verified_signed_evidence_construction_forbidden",
                "/",
            )
        validate_hip_fgmres_external_release_identity_receipt_v1(identity_receipt)
        validate_hip_fgmres_external_signed_evidence_receipt_v1(signed_receipt)
        if identity_receipt.release_binding_hash != signed_receipt.release_binding_hash:
            _fail(
                "hip_fgmres_external_verified_signed_evidence_binding_mismatch",
                "/",
            )
        self._identity_receipt = identity_receipt
        self._signed_receipt = signed_receipt
        self._mint = mint

    @property
    def identity_receipt(self) -> HipFgmresExternalReleaseIdentityReceiptV1:
        return self._identity_receipt

    @property
    def signed_receipt(self) -> HipFgmresExternalSignedEvidenceReceiptV1:
        return self._signed_receipt


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class _BuildRecipeV1:
    semantic_hash: str
    raw_sha256: str


def compile_hip_fgmres_external_release_identity_v1(
    *,
    paths: HipFgmresExternalReleaseArtifactPathsV1,
) -> HipFgmresExternalVerifiedReleaseV1:
    """Replay actual artifacts and mint a process-local verified release."""

    checked_paths = _validate_paths(paths)
    wheel_path = _join_artifact(
        checked_paths.artifact_root,
        checked_paths.wheel_filename,
        path="/paths/wheel_filename",
    )
    source_bundle_path = _join_artifact(
        checked_paths.artifact_root,
        checked_paths.source_bundle_filename,
        path="/paths/source_bundle_filename",
    )
    _reject_cross_role_aliases(checked_paths, wheel_path, source_bundle_path)

    wheel = inspect_wheel_artifact_v1(wheel_path)
    validate_wheel_artifact_identity_v1(wheel)
    try:
        installed_version = metadata.version(_DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError as exc:
        _fail(
            "hip_fgmres_external_release_distribution_missing",
            "/distribution",
            str(exc),
        )
    if (
        wheel.canonical_distribution_name != canonicalize_name(_DISTRIBUTION_NAME)
        or installed_version != wheel.distribution_version
    ):
        _fail("hip_fgmres_external_release_wheel_distribution_mismatch", "/wheel")

    installed_root = _current_installed_distribution_root(wheel)
    installed_scripts_root: str | None = None
    if wheel.console_scripts or wheel.gui_scripts:
        scripts_path = sysconfig.get_path("scripts")
        if type(scripts_path) is not str or not scripts_path:
            _fail(
                "hip_fgmres_external_release_installed_scripts_root_invalid",
                "/installed_scripts_root",
            )
        installed_scripts_root = scripts_path
    installed = replay_installed_wheel_artifact_v1(
        wheel_path=wheel_path,
        installed_root=installed_root,
        installed_scripts_root=installed_scripts_root,
    )
    validate_installed_wheel_replay_v1(installed)
    if installed.wheel_identity != wheel:
        _fail("hip_fgmres_external_release_wheel_changed", "/wheel")

    source = compile_source_artifact_identity_v1(
        checked_paths.repository_root,
        source_bundle_path,
        runner_source_paths=checked_paths.runner_source_paths,
        build_recipe_path=checked_paths.build_recipe_path,
        dependency_lock_path=checked_paths.dependency_lock_path,
    )
    validate_source_artifact_identity_v1(source)

    build_recipe_raw = _read_source_role_file(
        checked_paths.repository_root,
        checked_paths.build_recipe_path,
        byte_limit=_BUILD_RECIPE_MAX_BYTES,
    )
    lock_raw = _read_source_role_file(
        checked_paths.repository_root,
        checked_paths.dependency_lock_path,
        byte_limit=8 * 1024 * 1024,
    )
    if (
        sha256_prefixed(build_recipe_raw) != source.build_recipe_sha256
        or sha256_prefixed(lock_raw) != source.dependency_lock_sha256
    ):
        _fail("hip_fgmres_external_release_source_role_drift", "/source")

    dependency = verify_dependency_artifact_lock_v1(
        lock_raw,
        artifact_root=checked_paths.dependency_artifact_root,
        root_wheel_identity=wheel,
    )
    validate_dependency_lock_receipt_v1(dependency)
    recipe = _validate_build_recipe(
        build_recipe_raw,
        wheel=wheel,
        source=source,
        dependency=dependency,
    )
    _validate_component_bindings(
        wheel=wheel,
        source=source,
        dependency=dependency,
        recipe=recipe,
    )

    binding = compile_hip_fgmres_external_release_binding_v1(
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
    validate_hip_fgmres_external_release_binding_v1(binding)

    final_installed = replay_installed_wheel_artifact_v1(
        wheel_path=wheel_path,
        installed_root=installed_root,
        installed_scripts_root=installed_scripts_root,
    )
    if final_installed != installed:
        _fail(
            "hip_fgmres_external_release_installed_distribution_changed", "/installed"
        )
    final_source = compile_source_artifact_identity_v1(
        checked_paths.repository_root,
        source_bundle_path,
        runner_source_paths=checked_paths.runner_source_paths,
        build_recipe_path=checked_paths.build_recipe_path,
        dependency_lock_path=checked_paths.dependency_lock_path,
    )
    if final_source != source:
        _fail("hip_fgmres_external_release_source_changed", "/source")
    final_build_recipe_raw = _read_source_role_file(
        checked_paths.repository_root,
        checked_paths.build_recipe_path,
        byte_limit=_BUILD_RECIPE_MAX_BYTES,
    )
    final_lock_raw = _read_source_role_file(
        checked_paths.repository_root,
        checked_paths.dependency_lock_path,
        byte_limit=8 * 1024 * 1024,
    )
    if final_build_recipe_raw != build_recipe_raw or final_lock_raw != lock_raw:
        _fail("hip_fgmres_external_release_source_role_drift", "/source")
    final_dependency = verify_dependency_artifact_lock_v1(
        final_lock_raw,
        artifact_root=checked_paths.dependency_artifact_root,
        root_wheel_identity=wheel,
    )
    if final_dependency != dependency:
        _fail("hip_fgmres_external_release_dependency_changed", "/dependency")
    final_recipe = _validate_build_recipe(
        final_build_recipe_raw,
        wheel=wheel,
        source=final_source,
        dependency=final_dependency,
    )
    if final_recipe != recipe:
        _fail("hip_fgmres_external_release_build_recipe_changed", "/build_recipe")
    _validate_component_bindings(
        wheel=wheel,
        source=final_source,
        dependency=final_dependency,
        recipe=final_recipe,
    )
    final_wheel = inspect_wheel_artifact_v1(wheel_path)
    if final_wheel != wheel:
        _fail("hip_fgmres_external_release_wheel_changed", "/wheel")
    _reject_cross_role_aliases(checked_paths, wheel_path, source_bundle_path)
    receipt = _compile_receipt(
        binding=binding,
        wheel=wheel,
        installed=installed,
        source=source,
        dependency=dependency,
        recipe=recipe,
    )
    return HipFgmresExternalVerifiedReleaseV1(
        paths=checked_paths,
        release_binding=binding,
        identity_receipt=receipt,
        mint=_VERIFIED_RELEASE_MINT,
    )


def validate_hip_fgmres_external_release_identity_receipt_v1(
    receipt: HipFgmresExternalReleaseIdentityReceiptV1,
) -> HipFgmresExternalReleaseIdentityReceiptV1:
    """Validate serialized identity semantics without claiming fresh I/O."""

    if (
        type(receipt) is not HipFgmresExternalReleaseIdentityReceiptV1
        or type(receipt.claims) is not HipFgmresExternalReleaseIdentityClaimsV1
    ):
        _fail("hip_fgmres_external_release_identity_receipt_type_invalid", "/")
    payload = _receipt_payload(receipt, include_hash=True)
    _validate_schema(payload)
    hashes = (
        receipt.release_binding_hash,
        receipt.wheel_identity_hash,
        receipt.installed_replay_hash,
        receipt.source_identity_hash,
        receipt.dependency_lock_receipt_hash,
        receipt.build_recipe_semantic_hash,
        receipt.wheel_sha256,
        receipt.wheel_record_sha256,
        receipt.source_tree_sha256,
        receipt.source_bundle_sha256,
        receipt.runner_source_sha256,
        receipt.build_recipe_sha256,
        receipt.dependency_lock_sha256,
        receipt.dependency_artifact_aggregate_hash,
        receipt.installed_script_manifest_sha256,
        receipt.receipt_hash,
    )
    counts = (
        receipt.wheel_byte_count,
        receipt.wheel_member_count,
        receipt.installed_verified_member_count,
        receipt.installed_extra_file_count,
        receipt.installed_script_file_count,
        receipt.source_tracked_file_count,
        receipt.source_bundle_byte_count,
        receipt.runner_source_file_count,
        receipt.dependency_artifact_count,
    )
    if (
        receipt.schema_version != HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1
        or receipt.capability_profile
        != HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_CAPABILITY_PROFILE_V1
        or receipt.status != _STATUS
        or receipt.evidence_scope
        != HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_EVIDENCE_SCOPE_V1
        or any(_HASH_RE.fullmatch(value) is None for value in hashes)
        or any(type(value) is not int or value < 0 for value in counts)
        or receipt.wheel_byte_count <= 0
        or receipt.wheel_member_count <= 0
        or receipt.installed_verified_member_count != receipt.wheel_member_count - 1
        or receipt.source_tracked_file_count <= 0
        or receipt.source_bundle_byte_count <= 0
        or receipt.runner_source_file_count <= 0
        or _SAFE_FILE_RE.fullmatch(receipt.wheel_filename) is None
        or _COMMIT_RE.fullmatch(receipt.source_commit) is None
        or receipt.claims != HipFgmresExternalReleaseIdentityClaimsV1()
        or receipt.promotion_eligible is not False
        or receipt.receipt_hash
        != canonical_hash(_receipt_payload(receipt, include_hash=False))
    ):
        _fail("hip_fgmres_external_release_identity_receipt_invalid", "/")
    return receipt


def verify_hip_fgmres_external_release_artifacts_v1(
    verified_release: HipFgmresExternalVerifiedReleaseV1,
) -> HipFgmresExternalVerifiedReleaseV1:
    """Freshly replay every retained path and reject any identity drift."""

    _validate_verified_release(verified_release)
    replay = compile_hip_fgmres_external_release_identity_v1(
        paths=verified_release._paths
    )
    if (
        replay.release_binding != verified_release.release_binding
        or replay.identity_receipt != verified_release.identity_receipt
    ):
        _fail("hip_fgmres_external_release_artifact_replay_mismatch", "/")
    return verified_release


def issue_hip_fgmres_external_evidence_challenge_for_verified_release_v1(
    *,
    verified_release: HipFgmresExternalVerifiedReleaseV1,
    key_id: str,
    runner_id: str,
    run_sequence: int,
    request_id: str,
    campaign_id: str,
    ttl_seconds: int = 900,
) -> HipFgmresExternalChallengeV1:
    """Issue a challenge only after a fresh artifact replay."""

    verify_hip_fgmres_external_release_artifacts_v1(verified_release)
    return issue_hip_fgmres_external_evidence_challenge_v1(
        release_binding=verified_release.release_binding,
        key_id=key_id,
        runner_id=runner_id,
        run_sequence=run_sequence,
        request_id=request_id,
        campaign_id=campaign_id,
        ttl_seconds=ttl_seconds,
    )


def verify_hip_fgmres_external_signed_evidence_for_verified_release_v1(
    envelope_bytes: bytes,
    *,
    challenge: HipFgmresExternalChallengeV1,
    verified_release: HipFgmresExternalVerifiedReleaseV1,
) -> HipFgmresExternalVerifiedSignedEvidenceV1:
    """Freshly replay artifacts before invoking the signed-envelope verifier."""

    verify_hip_fgmres_external_release_artifacts_v1(verified_release)
    signed_receipt = verify_hip_fgmres_external_signed_evidence_v1(
        envelope_bytes,
        challenge=challenge,
        release_binding=verified_release.release_binding,
    )
    return HipFgmresExternalVerifiedSignedEvidenceV1(
        identity_receipt=verified_release.identity_receipt,
        signed_receipt=signed_receipt,
        mint=_VERIFIED_SIGNED_EVIDENCE_MINT,
    )


def _validate_component_bindings(
    *,
    wheel: WheelArtifactIdentityV1,
    source: SourceArtifactIdentityV1,
    dependency: DependencyLockReceiptV1,
    recipe: _BuildRecipeV1,
) -> None:
    if (
        dependency.root_distribution_name != wheel.canonical_distribution_name
        or dependency.root_distribution_version != wheel.canonical_distribution_version
        or dependency.root_filename != wheel.wheel_filename
        or dependency.root_byte_count != wheel.byte_count
        or dependency.root_sha256 != wheel.sha256
        or dependency.root_requires_dist != wheel.requires_dist
        or dependency.root_wheel_identity_hash != wheel.identity_hash
        or dependency.lock_bytes_sha256 != source.dependency_lock_sha256
        or recipe.raw_sha256 != source.build_recipe_sha256
    ):
        _fail("hip_fgmres_external_release_component_binding_mismatch", "/")


def _validate_binding_receipt_consistency(
    binding: HipFgmresExternalReleaseBindingV1,
    receipt: HipFgmresExternalReleaseIdentityReceiptV1,
) -> None:
    if (
        binding.binding_hash != receipt.release_binding_hash
        or binding.wheel_filename != receipt.wheel_filename
        or binding.wheel_byte_count != receipt.wheel_byte_count
        or binding.wheel_sha256 != receipt.wheel_sha256
        or binding.wheel_record_sha256 != receipt.wheel_record_sha256
        or binding.source_commit != receipt.source_commit
        or binding.source_tree_sha256 != receipt.source_tree_sha256
        or binding.source_bundle_sha256 != receipt.source_bundle_sha256
        or binding.runner_source_sha256 != receipt.runner_source_sha256
        or binding.build_recipe_sha256 != receipt.build_recipe_sha256
        or binding.dependency_lock_sha256 != receipt.dependency_lock_sha256
    ):
        _fail("hip_fgmres_external_verified_release_binding_mismatch", "/")


def _compile_receipt(
    *,
    binding: HipFgmresExternalReleaseBindingV1,
    wheel: WheelArtifactIdentityV1,
    installed: InstalledWheelReplayV1,
    source: SourceArtifactIdentityV1,
    dependency: DependencyLockReceiptV1,
    recipe: _BuildRecipeV1,
) -> HipFgmresExternalReleaseIdentityReceiptV1:
    draft = HipFgmresExternalReleaseIdentityReceiptV1(
        schema_version=HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1,
        capability_profile=HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_CAPABILITY_PROFILE_V1,
        status=_STATUS,
        evidence_scope=HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_EVIDENCE_SCOPE_V1,
        release_binding_hash=binding.binding_hash,
        wheel_identity_hash=wheel.identity_hash,
        installed_replay_hash=installed.replay_hash,
        source_identity_hash=source.identity_hash,
        dependency_lock_receipt_hash=dependency.receipt_hash,
        build_recipe_semantic_hash=recipe.semantic_hash,
        wheel_filename=wheel.wheel_filename,
        wheel_byte_count=wheel.byte_count,
        wheel_sha256=wheel.sha256,
        wheel_record_sha256=wheel.record_sha256,
        wheel_member_count=wheel.member_count,
        installed_verified_member_count=installed.verified_wheel_member_count,
        installed_extra_file_count=installed.extra_file_count,
        installed_script_file_count=installed.script_file_count,
        installed_script_manifest_sha256=installed.script_manifest_sha256,
        source_commit=source.source_commit,
        source_tree_sha256=source.source_tree_sha256,
        source_tracked_file_count=source.source_manifest.file_count,
        source_bundle_byte_count=source.source_bundle_byte_count,
        source_bundle_sha256=source.source_bundle_sha256,
        runner_source_file_count=len(source.runner_source_paths),
        runner_source_sha256=source.runner_source_sha256,
        build_recipe_sha256=source.build_recipe_sha256,
        dependency_lock_sha256=source.dependency_lock_sha256,
        dependency_artifact_count=dependency.artifact_count,
        dependency_artifact_aggregate_hash=dependency.artifact_aggregate_hash,
        claims=HipFgmresExternalReleaseIdentityClaimsV1(),
        promotion_eligible=False,
        receipt_hash=_ZERO_HASH,
    )
    receipt = replace(
        draft,
        receipt_hash=canonical_hash(_receipt_payload(draft, include_hash=False)),
    )
    validated = validate_hip_fgmres_external_release_identity_receipt_v1(receipt)
    _validate_binding_receipt_consistency(binding, validated)
    return validated


def _validate_verified_release(
    value: HipFgmresExternalVerifiedReleaseV1,
) -> None:
    if (
        type(value) is not HipFgmresExternalVerifiedReleaseV1
        or value._mint is not _VERIFIED_RELEASE_MINT
        or type(value._paths) is not HipFgmresExternalReleaseArtifactPathsV1
    ):
        _fail("hip_fgmres_external_verified_release_invalid", "/")
    validate_hip_fgmres_external_release_binding_v1(value.release_binding)
    validate_hip_fgmres_external_release_identity_receipt_v1(value.identity_receipt)
    _validate_binding_receipt_consistency(
        value.release_binding,
        value.identity_receipt,
    )


def _validate_paths(
    paths: HipFgmresExternalReleaseArtifactPathsV1,
) -> HipFgmresExternalReleaseArtifactPathsV1:
    if type(paths) is not HipFgmresExternalReleaseArtifactPathsV1:
        _fail("hip_fgmres_external_release_artifact_paths_type_invalid", "/paths")
    scalar_paths = (
        (paths.repository_root, "/paths/repository_root"),
        (paths.artifact_root, "/paths/artifact_root"),
        (paths.dependency_artifact_root, "/paths/dependency_artifact_root"),
    )
    for value, pointer in scalar_paths:
        if type(value) is not str or not value or "\x00" in value:
            _fail("hip_fgmres_external_release_artifact_path_invalid", pointer)
    resolved_roots: list[str] = []
    root_identities: set[tuple[int, int]] = set()
    for value, pointer in scalar_paths:
        try:
            resolved = Path(value).resolve(strict=True)
            info = resolved.stat()
        except (OSError, RuntimeError) as exc:
            _fail(
                "hip_fgmres_external_release_artifact_root_invalid",
                pointer,
                str(exc),
            )
        if not stat.S_ISDIR(info.st_mode):
            _fail("hip_fgmres_external_release_artifact_root_invalid", pointer)
        identity = (info.st_dev, info.st_ino)
        if identity in root_identities:
            _fail("hip_fgmres_external_release_artifact_root_alias", pointer)
        root_identities.add(identity)
        resolved_roots.append(os.fspath(resolved))
    _validate_filename(paths.wheel_filename, "/paths/wheel_filename", suffix=".whl")
    _validate_filename(
        paths.source_bundle_filename,
        "/paths/source_bundle_filename",
        suffix=".tar",
    )
    if type(paths.runner_source_paths) is not tuple or not paths.runner_source_paths:
        _fail("hip_fgmres_external_release_source_roles_invalid", "/paths")
    role_paths = (
        *paths.runner_source_paths,
        paths.build_recipe_path,
        paths.dependency_lock_path,
    )
    if any(type(value) is not str for value in role_paths) or len(
        set(role_paths)
    ) != len(role_paths):
        _fail("hip_fgmres_external_release_source_roles_invalid", "/paths")
    for index, value in enumerate(role_paths):
        _validate_relative_source_path(value, f"/paths/source_roles/{index}")
    return replace(
        paths,
        repository_root=resolved_roots[0],
        artifact_root=resolved_roots[1],
        dependency_artifact_root=resolved_roots[2],
    )


def _join_artifact(root: str, filename: str, *, path: str) -> str:
    _validate_filename(filename, path)
    root_path = Path(root)
    try:
        checked_root = root_path.resolve(strict=True)
    except OSError as exc:
        _fail("hip_fgmres_external_release_artifact_root_invalid", path, str(exc))
    candidate = checked_root / filename
    if candidate.parent != checked_root:
        _fail("hip_fgmres_external_release_artifact_path_invalid", path)
    return os.fspath(candidate)


def _validate_filename(value: str, path: str, suffix: str | None = None) -> None:
    if (
        type(value) is not str
        or _SAFE_FILE_RE.fullmatch(value) is None
        or "/" in value
        or "\\" in value
        or (suffix is not None and not value.endswith(suffix))
    ):
        _fail("hip_fgmres_external_release_artifact_filename_invalid", path)


def _validate_relative_source_path(value: str, path: str) -> None:
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or any(part in ("", ".", "..") for part in value.split("/"))
        or str(PurePosixPath(value)) != value
    ):
        _fail("hip_fgmres_external_release_source_path_invalid", path)


def _reject_cross_role_aliases(
    paths: HipFgmresExternalReleaseArtifactPathsV1,
    wheel_path: str,
    source_bundle_path: str,
) -> None:
    candidates = [wheel_path, source_bundle_path]
    candidates.extend(
        os.fspath(Path(paths.repository_root) / value)
        for value in (
            *paths.runner_source_paths,
            paths.build_recipe_path,
            paths.dependency_lock_path,
        )
    )
    identities: set[tuple[int, int]] = set()
    for index, candidate in enumerate(candidates):
        try:
            info = os.lstat(candidate)
        except OSError as exc:
            _fail(
                "hip_fgmres_external_release_artifact_missing",
                f"/artifact_roles/{index}",
                str(exc),
            )
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            _fail(
                "hip_fgmres_external_release_artifact_type_invalid",
                f"/artifact_roles/{index}",
            )
        identity = (info.st_dev, info.st_ino)
        if identity in identities:
            _fail("hip_fgmres_external_release_artifact_alias", "/artifact_roles")
        identities.add(identity)


def _current_installed_distribution_root(wheel: WheelArtifactIdentityV1) -> str:
    candidates = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name and canonicalize_name(name) == wheel.canonical_distribution_name:
            candidates.append(distribution)
    if len(candidates) != 1:
        _fail(
            "hip_fgmres_external_release_installed_distribution_ambiguous",
            "/installed_distribution",
        )
    distribution = candidates[0]
    dist_info = Path(distribution.locate_file(wheel.dist_info_directory))
    try:
        dist_info = dist_info.resolve(strict=True)
    except OSError as exc:
        _fail(
            "hip_fgmres_external_release_installed_distribution_missing",
            "/installed_distribution",
            str(exc),
        )
    if not dist_info.is_dir() or dist_info.name != wheel.dist_info_directory:
        _fail(
            "hip_fgmres_external_release_installed_distribution_not_wheel",
            "/installed_distribution",
        )
    root = dist_info.parent.resolve(strict=True)
    package = import_module("structural_analysis")
    package_file = getattr(package, "__file__", None)
    expected = root / "structural_analysis" / "__init__.py"
    try:
        package_path = Path(package_file).resolve(strict=True)
        expected_path = expected.resolve(strict=True)
    except (OSError, TypeError) as exc:
        _fail(
            "hip_fgmres_external_release_installed_shadowing_detected",
            "/installed_distribution",
            str(exc),
        )
    if package_path != expected_path:
        _fail(
            "hip_fgmres_external_release_installed_shadowing_detected",
            "/installed_distribution",
        )
    return os.fspath(root)


def _read_source_role_file(root: str, relative: str, *, byte_limit: int) -> bytes:
    _validate_relative_source_path(relative, "/source_role")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    directory_flags = flags | os.O_DIRECTORY
    file_flags = flags | os.O_NONBLOCK
    root_descriptor = -1
    descriptor = -1
    file_descriptor = -1
    try:
        root_descriptor = os.open(root, directory_flags)
        root_start_fd = os.fstat(root_descriptor)
        root_start_path = os.lstat(root)
        if (
            not stat.S_ISDIR(root_start_fd.st_mode)
            or stat.S_ISLNK(root_start_path.st_mode)
            or (root_start_fd.st_dev, root_start_fd.st_ino)
            != (root_start_path.st_dev, root_start_path.st_ino)
        ):
            os.close(root_descriptor)
            root_descriptor = -1
            _fail("hip_fgmres_external_release_source_root_invalid", "/source")
        descriptor = os.dup(root_descriptor)
    except OSError as exc:
        if root_descriptor >= 0:
            os.close(root_descriptor)
            root_descriptor = -1
        _fail("hip_fgmres_external_release_source_root_invalid", "/source", str(exc))
    try:
        components = relative.split("/")
        for component in components[:-1]:
            try:
                next_descriptor = os.open(
                    component,
                    directory_flags,
                    dir_fd=descriptor,
                )
            except OSError as exc:
                _fail(
                    "hip_fgmres_external_release_source_role_open_failed",
                    "/source_role",
                    str(exc),
                )
            os.close(descriptor)
            descriptor = next_descriptor
        try:
            file_descriptor = os.open(components[-1], file_flags, dir_fd=descriptor)
        except OSError as exc:
            _fail(
                "hip_fgmres_external_release_source_role_open_failed",
                "/source_role",
                str(exc),
            )
        try:
            start = os.fstat(file_descriptor)
            start_path = os.stat(
                components[-1],
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(start.st_mode)
                or stat.S_ISLNK(start_path.st_mode)
                or (start.st_dev, start.st_ino)
                != (start_path.st_dev, start_path.st_ino)
                or start.st_size > byte_limit
            ):
                _fail(
                    "hip_fgmres_external_release_source_role_invalid",
                    "/source_role",
                )
            chunks: list[bytes] = []
            count = 0
            while True:
                chunk = os.read(
                    file_descriptor, min(1024 * 1024, byte_limit + 1 - count)
                )
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                if count > byte_limit:
                    _fail(
                        "hip_fgmres_external_release_source_role_invalid",
                        "/source_role",
                    )
            end = os.fstat(file_descriptor)
            end_path = os.stat(
                components[-1],
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if (
                start.st_dev,
                start.st_ino,
                start.st_size,
                start.st_mtime_ns,
                start.st_ctime_ns,
            ) != (
                end.st_dev,
                end.st_ino,
                end.st_size,
                end.st_mtime_ns,
                end.st_ctime_ns,
            ) or (
                end.st_dev,
                end.st_ino,
                stat.S_IFMT(end.st_mode),
                end.st_size,
                end.st_mtime_ns,
                end.st_ctime_ns,
            ) != (
                end_path.st_dev,
                end_path.st_ino,
                stat.S_IFMT(end_path.st_mode),
                end_path.st_size,
                end_path.st_mtime_ns,
                end_path.st_ctime_ns,
            ):
                _fail(
                    "hip_fgmres_external_release_source_role_changed",
                    "/source_role",
                )
            root_end_fd = os.fstat(root_descriptor)
            root_end_path = os.lstat(root)
            if (
                root_start_fd.st_dev,
                root_start_fd.st_ino,
                stat.S_IFMT(root_start_fd.st_mode),
                root_start_fd.st_mtime_ns,
                root_start_fd.st_ctime_ns,
            ) != (
                root_end_fd.st_dev,
                root_end_fd.st_ino,
                stat.S_IFMT(root_end_fd.st_mode),
                root_end_fd.st_mtime_ns,
                root_end_fd.st_ctime_ns,
            ) or (
                root_end_fd.st_dev,
                root_end_fd.st_ino,
                stat.S_IFMT(root_end_fd.st_mode),
            ) != (
                root_end_path.st_dev,
                root_end_path.st_ino,
                stat.S_IFMT(root_end_path.st_mode),
            ):
                _fail(
                    "hip_fgmres_external_release_source_root_changed",
                    "/source",
                )
            return b"".join(chunks)
        except OSError as exc:
            _fail(
                "hip_fgmres_external_release_source_role_read_failed",
                "/source_role",
                str(exc),
            )
        finally:
            if file_descriptor >= 0:
                os.close(file_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)


def _validate_build_recipe(
    raw: bytes,
    *,
    wheel: WheelArtifactIdentityV1,
    source: SourceArtifactIdentityV1,
    dependency: DependencyLockReceiptV1,
) -> _BuildRecipeV1:
    payload = _parse_canonical_json(raw, path="/build_recipe")
    expected_keys = {
        "schema_version",
        "policy_id",
        "build_frontend",
        "build_backend",
        "argv",
        "environment",
        "source_date_epoch",
        "candidate_wheel_filename",
        "dependency_lock_sha256",
        "target_environment_hash",
        "recipe_hash",
    }
    if set(payload) != expected_keys:
        _fail("hip_fgmres_external_release_build_recipe_invalid", "/build_recipe")
    environment = payload["environment"]
    argv = payload["argv"]
    if (
        payload["schema_version"] != HIP_FGMRES_EXTERNAL_BUILD_RECIPE_SCHEMA_VERSION_V1
        or payload["policy_id"] != _BUILD_POLICY_ID
        or payload["build_frontend"] != _BUILD_FRONTEND
        or payload["build_backend"] != _BUILD_BACKEND
        or type(argv) is not list
        or tuple(argv) != _BUILD_ARGV
        or type(environment) is not dict
        or set(environment) != {*_BUILD_ENVIRONMENT_FIXED, "SOURCE_DATE_EPOCH"}
        or any(
            _ENV_NAME_RE.fullmatch(key) is None
            or type(value) is not str
            or "\x00" in value
            or any(
                word in key for word in ("TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
            )
            for key, value in environment.items()
        )
        or any(
            environment.get(key) != value
            for key, value in _BUILD_ENVIRONMENT_FIXED.items()
        )
        or not environment.get("SOURCE_DATE_EPOCH", "").isdigit()
        or type(payload["source_date_epoch"]) is not int
        or not 0 <= payload["source_date_epoch"] <= 253402300799
        or str(payload["source_date_epoch"]) != environment["SOURCE_DATE_EPOCH"]
        or payload["candidate_wheel_filename"] != wheel.wheel_filename
        or payload["dependency_lock_sha256"] != source.dependency_lock_sha256
        or payload["dependency_lock_sha256"] != dependency.lock_bytes_sha256
        or payload["target_environment_hash"] != dependency.target_environment_hash
    ):
        _fail("hip_fgmres_external_release_build_recipe_invalid", "/build_recipe")
    semantic = dict(payload)
    del semantic["recipe_hash"]
    semantic_hash = canonical_hash(semantic)
    if payload["recipe_hash"] != semantic_hash:
        _fail(
            "hip_fgmres_external_release_build_recipe_hash_mismatch",
            "/build_recipe/recipe_hash",
        )
    return _BuildRecipeV1(
        semantic_hash=semantic_hash,
        raw_sha256=sha256_prefixed(raw),
    )


def _parse_canonical_json(raw: bytes, *, path: str) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > _BUILD_RECIPE_MAX_BYTES:
        _fail("hip_fgmres_external_release_json_extent_invalid", path)
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("hip_fgmres_external_release_json_bom_forbidden", path)

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise _DuplicateJsonKey(key)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        raise ValueError(value)

    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
        _reject_nonfinite(payload, path=path)
        canonical = canonical_json_bytes(payload)
    except (
        _DuplicateJsonKey,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        _fail(
            "hip_fgmres_external_release_json_invalid",
            path,
            f"{type(exc).__name__}: {exc}",
        )
    if type(payload) is not dict or raw != canonical:
        _fail("hip_fgmres_external_release_json_not_canonical", path)
    return payload


def _reject_nonfinite(value: Any, *, path: str) -> None:
    if type(value) is float and not math.isfinite(value):
        _fail("hip_fgmres_external_release_json_nonfinite", path)
    if type(value) is dict:
        for key, item in value.items():
            _reject_nonfinite(item, path=f"{path}/{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_nonfinite(item, path=f"{path}/{index}")


def _receipt_payload(
    receipt: HipFgmresExternalReleaseIdentityReceiptV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        name: getattr(receipt, name)
        for name in receipt.__dataclass_fields__
        if name not in {"claims", "receipt_hash"}
    }
    payload["claims"] = receipt.claims.to_dict()
    if include_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _validate_schema(payload: dict[str, Any]) -> None:
    try:
        raw = (
            resources.files("structural_analysis.schemas")
            .joinpath(_SCHEMA_RESOURCE)
            .read_bytes()
        )
        schema = json.loads(raw.decode("utf-8"))
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        _fail(
            "hip_fgmres_external_release_identity_schema_invalid",
            "/schema",
            f"{type(exc).__name__}: {exc}",
        )
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        location = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(
            "hip_fgmres_external_release_identity_schema_validation_failed",
            location,
            error.message,
        )


def _fail(code: str, path: str, message: str = "") -> NoReturn:
    raise HipFgmresExternalReleaseIdentityV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_EXTERNAL_BUILD_RECIPE_SCHEMA_VERSION_V1",
    "HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_EVIDENCE_SCOPE_V1",
    "HIP_FGMRES_EXTERNAL_RELEASE_IDENTITY_SCHEMA_VERSION_V1",
    "HipFgmresExternalReleaseArtifactPathsV1",
    "HipFgmresExternalReleaseIdentityClaimsV1",
    "HipFgmresExternalReleaseIdentityReceiptV1",
    "HipFgmresExternalReleaseIdentityV1Error",
    "HipFgmresExternalVerifiedReleaseV1",
    "HipFgmresExternalVerifiedSignedEvidenceV1",
    "compile_hip_fgmres_external_release_identity_v1",
    "issue_hip_fgmres_external_evidence_challenge_for_verified_release_v1",
    "validate_hip_fgmres_external_release_identity_receipt_v1",
    "verify_hip_fgmres_external_release_artifacts_v1",
    "verify_hip_fgmres_external_signed_evidence_for_verified_release_v1",
]
