from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import textwrap
import zipfile

import pytest

from scripts import build_product_state_provenance_bundle as provenance
from scripts import verify_canonical_actions_artifact as intake
from scripts import verify_tracked_source_tree as source_guard

SHA = "a" * 40
RUN_ID = 123
REPOSITORY = "example/project"
ROOT = Path(__file__).resolve().parents[1]


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _zip(
    files: dict[str, bytes],
    *,
    renamed: str | None = None,
    mode: int | None = None,
    duplicate: bool = False,
) -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for number, (path, raw) in enumerate(sorted(files.items())):
            member = zipfile.ZipInfo(renamed if number == 0 and renamed else path)
            member.compress_type = zipfile.ZIP_DEFLATED
            member.external_attr = (
                mode if number == 0 and mode else stat.S_IFREG | 0o644
            ) << 16
            archive.writestr(member, raw)
        if duplicate:
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(next(iter(files)), b"duplicate")
    return target.getvalue()


@pytest.fixture()
def evidence() -> dict:
    wheel = b"synthetic wheel bytes, not an installed-project replay"
    contract = {
        "source_commit_sha": SHA,
        "wheel": {
            "filename": Path(intake.WHEEL_PATH).name,
            "byte_length": len(wheel),
            "sha256": _digest(wheel),
        },
    }
    receipt = {
        "source_commit_sha": SHA,
        "source_checkout_head_sha": SHA,
        "project_wheel": contract,
    }
    files = {
        intake.WHEEL_PATH: wheel,
        intake.CONTRACT_PATH: json.dumps(contract).encode(),
        intake.RECEIPT_PATH: json.dumps(receipt).encode(),
    }
    archive = _zip(files)
    run = {
        "id": RUN_ID,
        "run_number": 45,
        "run_attempt": 2,
        "name": intake.WORKFLOW_NAME,
        "path": intake.WORKFLOW_PATH,
        "head_branch": "main",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
        "event": "push",
        "repository": {"id": 30, "full_name": REPOSITORY},
        "head_repository": {"id": 30, "full_name": REPOSITORY},
        "run_started_at": "2026-10-02T02:00:00Z",
        "updated_at": "2026-10-02T02:03:00Z",
    }
    artifact = {
        "id": 456,
        "name": intake.artifact_name(SHA, RUN_ID, 2),
        "digest": _digest(archive),
        "size_in_bytes": len(archive),
        "expired": False,
        "archive_download_url": f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/456/zip",
        "workflow_run": {
            "id": RUN_ID,
            "repository_id": 30,
            "head_repository_id": 30,
            "head_branch": "main",
            "head_sha": SHA,
        },
        "created_at": "2026-10-02T02:02:00Z",
        "updated_at": "2026-10-02T02:02:00Z",
    }
    return {
        "run": run,
        "inventory": {"total_count": 1, "artifacts": [deepcopy(artifact)]},
        "artifact": artifact,
        "archive": archive,
    }


def _check(evidence: dict) -> tuple[dict, dict[str, bytes]]:
    return intake.validate_artifact(
        **evidence, repository=REPOSITORY, source_sha=SHA, run_id=RUN_ID
    )


def _sync(evidence: dict) -> None:
    evidence["inventory"]["artifacts"] = [deepcopy(evidence["artifact"])]


def _replace_archive(evidence: dict, raw: bytes) -> None:
    evidence["archive"] = raw
    evidence["artifact"]["digest"] = _digest(raw)
    evidence["artifact"]["size_in_bytes"] = len(raw)
    _sync(evidence)


def test_exact_attempt_archive_and_member_identity(evidence) -> None:
    identity, files = _check(evidence)
    assert set(files) == intake.MEMBERS
    assert identity["workflow_run"]["run_attempt"] == 2
    assert identity["workflow_run"]["updated_at"] == evidence["run"]["updated_at"]
    assert identity["archive_sha256"] == _digest(evidence["archive"])
    assert identity["artifact"]["id"] == 456
    assert identity["contract_pass"] is True


@pytest.mark.parametrize(
    "path",
    (
        intake.WORKFLOW_PATH,
        intake.WORKFLOW_PATH + "@main",
        intake.WORKFLOW_PATH + "@refs/heads/main",
    ),
)
def test_rest_optional_ref_preserves_normalized_provenance_location(
    evidence, path: str
) -> None:
    evidence["run"]["path"] = path
    _check(evidence)
    identity = provenance._workflow_identity(
        evidence["run"],
        authority="github_actions_workflow_run_api",
        expected_name=intake.WORKFLOW_NAME,
        expected_path=intake.WORKFLOW_PATH,
        source_sha=SHA,
        allowed_events={"push", "workflow_dispatch"},
        require_success=True,
    )
    assert identity["workflow_path"] == intake.WORKFLOW_PATH


@pytest.mark.parametrize(
    "key,value",
    (
        ("path", intake.WORKFLOW_PATH + "@"),
        ("path", intake.WORKFLOW_PATH + "/other"),
        ("head_sha", "b" * 40),
        ("head_branch", "topic"),
        ("status", "in_progress"),
        ("conclusion", "failure"),
        ("event", "pull_request"),
    ),
)
def test_contradictory_run_identity_rejects(evidence, key, value) -> None:
    evidence["run"][key] = value
    with pytest.raises(intake.CanonicalActionsArtifactError):
        _check(evidence)


@pytest.mark.parametrize("key", ("id", "run_number", "run_attempt"))
@pytest.mark.parametrize("value", (True, "123", 123.0, 0))
def test_run_numeric_identity_has_exact_integer_types(evidence, key, value) -> None:
    evidence["run"][key] = value
    with pytest.raises(intake.CanonicalActionsArtifactError):
        _check(evidence)


@pytest.mark.parametrize(
    "name",
    (
        "canonical-verification-environment-" + SHA,
        intake.artifact_name(SHA, RUN_ID, 1),
        intake.artifact_name(SHA, RUN_ID + 1, 2),
    ),
)
def test_legacy_other_attempt_and_other_run_artifacts_reject(evidence, name) -> None:
    evidence["artifact"]["name"] = name
    _sync(evidence)
    with pytest.raises(
        intake.CanonicalActionsArtifactError, match="inventory_ambiguous"
    ):
        _check(evidence)


@pytest.mark.parametrize(
    "created,updated",
    (
        ("2026-10-02T01:59:59Z", "2026-10-02T01:59:59Z"),
        ("2026-10-02T02:03:01Z", "2026-10-02T02:03:01Z"),
        ("2026-10-02T02:02:00Z", "2026-10-02T02:01:59Z"),
    ),
)
def test_attempt_name_cannot_mask_earlier_or_future_archive(
    evidence, created, updated
) -> None:
    evidence["artifact"].update(created_at=created, updated_at=updated)
    _sync(evidence)
    with pytest.raises(intake.CanonicalActionsArtifactError, match="outside_attempt"):
        _check(evidence)


@pytest.mark.parametrize(
    "value",
    (
        "2026-10-02 02:02:00Z",
        "20261002T020200Z",
        "2026-10-02T02:02:00+00:00",
        "2026-13-02T02:02:00Z",
        True,
    ),
)
def test_timestamp_shape_is_strict_utc_rest_representation(evidence, value) -> None:
    evidence["artifact"]["created_at"] = value
    _sync(evidence)
    with pytest.raises(
        intake.CanonicalActionsArtifactError, match="created_at_invalid"
    ):
        _check(evidence)


@pytest.mark.parametrize(
    "key,value",
    (
        ("id", 457),
        ("name", "different"),
        ("digest", "sha256:" + "f" * 64),
        ("size_in_bytes", 1),
        ("created_at", "2026-10-02T02:01:00Z"),
        ("updated_at", "2026-10-02T02:02:01Z"),
    ),
)
def test_list_direct_api_contradiction_rejects(evidence, key, value) -> None:
    evidence["artifact"][key] = value
    with pytest.raises(intake.CanonicalActionsArtifactError):
        _check(evidence)


@pytest.mark.parametrize(
    "key,value",
    (
        ("id", RUN_ID + 1),
        ("id", True),
        ("head_sha", "b" * 40),
        ("head_branch", "topic"),
        ("repository_id", True),
        ("head_repository_id", 31),
    ),
)
def test_artifact_producer_identity_contradiction_rejects(evidence, key, value) -> None:
    evidence["artifact"]["workflow_run"][key] = value
    _sync(evidence)
    with pytest.raises(intake.CanonicalActionsArtifactError, match="producer"):
        _check(evidence)


@pytest.mark.parametrize(
    "side,key",
    (
        ("artifact", "id"),
        ("artifact", "size_in_bytes"),
        ("listed", "id"),
        ("listed", "size_in_bytes"),
    ),
)
def test_list_and_direct_numeric_types_are_checked_separately(
    evidence, side, key
) -> None:
    row = (
        evidence["artifact"]
        if side == "artifact"
        else evidence["inventory"]["artifacts"][0]
    )
    row[key] = True
    with pytest.raises(intake.CanonicalActionsArtifactError):
        _check(evidence)


@pytest.mark.parametrize("count", (True, 0, 2))
def test_incomplete_inventory_cannot_select(evidence, count) -> None:
    evidence["inventory"]["total_count"] = count
    with pytest.raises(
        intake.CanonicalActionsArtifactError, match="inventory_incomplete"
    ):
        _check(evidence)


def test_duplicate_matching_artifacts_cannot_select(evidence) -> None:
    evidence["inventory"]["artifacts"].append(deepcopy(evidence["artifact"]))
    evidence["inventory"]["total_count"] = 2
    with pytest.raises(
        intake.CanonicalActionsArtifactError, match="inventory_ambiguous"
    ):
        _check(evidence)


def test_raw_archive_digest_is_checked_before_member_admission(evidence) -> None:
    evidence["archive"] = evidence["archive"][:-1] + bytes(
        [evidence["archive"][-1] ^ 1]
    )
    with pytest.raises(
        intake.CanonicalActionsArtifactError, match="archive_digest_mismatch"
    ):
        _check(evidence)


@pytest.mark.parametrize(
    "mutation",
    ("traversal", "basename", "absolute", "duplicate", "extra", "symlink", "directory"),
)
def test_exact_archive_member_paths_set_and_types(evidence, mutation: str) -> None:
    _, files = _check(evidence)
    options = {}
    if mutation == "extra":
        files["extra.txt"] = b"extra"
    elif mutation == "duplicate":
        options["duplicate"] = True
    elif mutation == "symlink":
        options["mode"] = stat.S_IFLNK | 0o777
    elif mutation == "directory":
        options["mode"] = stat.S_IFDIR | 0o755
    else:
        options["renamed"] = {
            "traversal": "../outside",
            "basename": "canonical-project-wheel-contract.json",
            "absolute": "/.ci/canonical-project-wheel-contract.json",
        }[mutation]
    _replace_archive(evidence, _zip(files, **options))
    with pytest.raises(intake.CanonicalActionsArtifactError, match="archive_member"):
        _check(evidence)


@pytest.mark.parametrize("dos_attributes", (0x10, 0x20))
def test_explicit_dos_directory_metadata_rejects_and_mode_zero_regular_accepts(
    evidence, dos_attributes: int
) -> None:
    _, files = _check(evidence)
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        for path, raw in sorted(files.items()):
            member = zipfile.ZipInfo(path)
            member.create_system = 0
            member.external_attr = dos_attributes
            archive.writestr(member, raw)
    _replace_archive(evidence, target.getvalue())
    if dos_attributes == 0x10:
        with pytest.raises(
            intake.CanonicalActionsArtifactError, match="member_type_invalid"
        ):
            _check(evidence)
    else:
        assert _check(evidence)[0]["contract_pass"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "receipt_source",
        "receipt_contract",
        "wheel_bytes",
        "contract_source",
        "duplicate_json_key",
    ),
)
def test_archive_receipt_contract_and_wheel_identity_remain_bound(
    evidence, mutation: str
) -> None:
    _, files = _check(evidence)
    if mutation == "wheel_bytes":
        files[intake.WHEEL_PATH] += b"changed"
    elif mutation == "duplicate_json_key":
        files[intake.RECEIPT_PATH] = (
            b'{"source_commit_sha":"a","source_commit_sha":"b"}'
        )
    else:
        path = (
            intake.CONTRACT_PATH
            if mutation == "contract_source"
            else intake.RECEIPT_PATH
        )
        obj = json.loads(files[path])
        obj[
            "project_wheel" if mutation == "receipt_contract" else "source_commit_sha"
        ] = "different"
        files[path] = json.dumps(obj).encode()
    _replace_archive(evidence, _zip(files))
    with pytest.raises(intake.CanonicalActionsArtifactError):
        _check(evidence)


def _cli_args(evidence: dict, tmp_path: Path) -> list[str]:
    for name in ("run", "inventory", "artifact"):
        (tmp_path / f"{name}.json").write_text(json.dumps(evidence[name]))
    (tmp_path / "archive.zip").write_bytes(evidence["archive"])
    root = tmp_path / "materialized"
    root.mkdir()
    return [
        "--run",
        str(tmp_path / "run.json"),
        "--inventory",
        str(tmp_path / "inventory.json"),
        "--artifact",
        str(tmp_path / "artifact.json"),
        "--archive",
        str(tmp_path / "archive.zip"),
        "--repository",
        REPOSITORY,
        "--source-sha",
        SHA,
        "--run-id",
        str(RUN_ID),
        "--materialize-root",
        str(root),
        "--identity-out",
        str(root / ".ci/product-state-inputs/canonical-actions-artifact-identity.json"),
    ]


def test_actual_admit_and_sealed_materialized_replay_then_drift_reject(
    evidence, tmp_path: Path
) -> None:
    args = _cli_args(evidence, tmp_path)
    assert intake.main(["admit", *args]) == 0
    assert intake.main(["replay", *args]) == 0
    target = tmp_path / "materialized" / intake.RECEIPT_PATH
    target.write_bytes(target.read_bytes() + b" ")
    assert intake.main(["replay", *args]) == 1


def test_rejected_archive_does_not_materialize_inputs(evidence, tmp_path: Path) -> None:
    evidence["archive"] += b"tampered"
    args = _cli_args(evidence, tmp_path)
    assert intake.main(["admit", *args]) == 1
    assert list((tmp_path / "materialized").iterdir()) == []


def test_oversized_sparse_archive_is_rejected_before_payload_read(
    evidence, tmp_path: Path, monkeypatch
) -> None:
    args = _cli_args(evidence, tmp_path)
    oversized = tmp_path / "archive.zip"
    with oversized.open("r+b") as handle:
        handle.truncate(intake.MAX_ARCHIVE_BYTES + 1)
    original = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        assert path != oversized, "oversized archive payload must not be read"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert intake.main(["admit", *args]) == 1
    assert list((tmp_path / "materialized").iterdir()) == []


def test_oversized_sparse_replay_member_is_rejected_before_payload_read(
    evidence, tmp_path: Path, monkeypatch
) -> None:
    args = _cli_args(evidence, tmp_path)
    assert intake.main(["admit", *args]) == 0
    oversized = tmp_path / "materialized" / intake.RECEIPT_PATH
    with oversized.open("r+b") as handle:
        handle.truncate(intake.MAX_MEMBER_BYTES + 1)
    original = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        assert path != oversized, "oversized replay member payload must not be read"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    assert intake.main(["replay", *args]) == 1


def test_materialization_rejects_symlink_ancestor_before_any_writes(
    evidence, tmp_path: Path
) -> None:
    args = _cli_args(evidence, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "materialized" / ".ci").symlink_to(outside, target_is_directory=True)
    assert intake.main(["admit", *args]) == 1
    assert list(outside.iterdir()) == []
    assert not (tmp_path / "materialized" / "artifacts").exists()


def test_producer_staging_and_consumer_admission_replay_wiring(
    evidence, tmp_path: Path
) -> None:
    producer = (ROOT / ".github/workflows/p0-canonical-contract.yml").read_text()
    stage = producer.split("      - name: Stage exact canonical archive members\n", 1)[
        1
    ].split("      - name:", 1)[0]
    stage_run = textwrap.dedent(stage.split("        run: |\n", 1)[1])
    _, files = _check(evidence)
    for relative, raw in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    # Execute the actual staging script, with only its full-source prerequisite
    # removed: this synthetic package directory is not a repository checkout.
    stage_run = stage_run.split("python - <<'PY'\n", 2)[-1]
    stage_run = f"{sys.executable} - <<'PY'\n" + stage_run
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", stage_run],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT)},
        check=True,
    )
    package = tmp_path / ".ci/canonical-artifact-package"
    staged = {
        p.relative_to(package).as_posix(): p.read_bytes()
        for p in package.rglob("*")
        if p.is_file()
    }
    assert staged == files
    upload = producer.split("      - name: Upload canonical environment identity\n", 1)[
        1
    ].split("      - name:", 1)[0]
    assert "path: .ci/canonical-artifact-package" in upload
    assert "include-hidden-files: true" in upload
    assert (
        "name: canonical-verification-environment-${{ github.run_id }}-${{ github.run_attempt }}-${{ github.sha }}"
        in upload
    )
    assert producer.index("Verify pristine canonical source") < producer.index(
        "Materialize and install exact hashed canonical dependencies"
    )
    assert 'source_profile_paths("producer")' in stage
    assert "allowed_untracked_paths=untracked | {CANONICAL_RECEIPT}" in stage
    consumer = (ROOT / ".github/workflows/product-state-current.yml").read_text()
    intake_step = consumer.split(
        "      - name: Materialize exact-SHA canonical verification receipt", 1
    )[-1].split("      - name: Materialize exact current-source", 1)[0]
    assert "verify_canonical_actions_artifact.py admit" in intake_step
    assert "gh run download" not in intake_step
    assert intake_step.count('actions/runs/$canonical_run_id"') == 2
    replay = consumer.split(
        "      - name: Replay exact-source overlay, full DAG, and provenance\n", 1
    )[1].split("      - name:", 1)[0]
    assert "verify_canonical_actions_artifact.py replay" in replay


def test_pre_stage_guard_composes_exact_named_receipt_and_existing_producer_paths(
    tmp_path: Path,
) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q")
    git("config", "user.name", "synthetic")
    git("config", "user.email", "synthetic@example.invalid")
    (tmp_path / "source.py").write_bytes(b"source = 1\n")
    git("add", "source.py")
    git("commit", "-qm", "synthetic source")
    sha = git("rev-parse", "HEAD")
    receipt = tmp_path / intake.RECEIPT_PATH
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b"synthetic receipt\n")
    modified, untracked = source_guard.source_profile_paths("producer")
    assert len(modified) == 22 and not untracked

    def check() -> dict:
        return source_guard.verify_tracked_source_tree(
            repo_root=tmp_path,
            source_sha=sha,
            allowed_modified_paths=modified,
            allowed_untracked_paths=untracked | {source_guard.CANONICAL_RECEIPT},
        )

    assert check()["contract_pass"] is True
    (tmp_path / "source.py").write_bytes(b"source = 2\n")
    with pytest.raises(source_guard.TrackedSourceTreeError, match="content_mismatch"):
        check()
