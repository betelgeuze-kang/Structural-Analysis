from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import bounded_planar_runtime_lock as runtime_lock  # noqa: E402
from bounded_planar_runtime_lock import requirements_bytes  # noqa: E402


SCRIPT = SCRIPTS / "build_bounded_planar_technical_producer_seal.py"
SPEC = importlib.util.spec_from_file_location(
    "bounded_planar_producer_seal_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
seal = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = seal
SPEC.loader.exec_module(seal)


def _run(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _fixture_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text(".ci/\nartifacts/\n", encoding="utf-8")
    source_paths = {
        *seal.COMMON_SOURCE_PATHS,
        str(seal.FAMILY_PATHS["linear"]["workflow"]),
        str(seal.FAMILY_PATHS["linear"]["builder"]),
        str(seal.FAMILY_PATHS["linear"]["ingest"]),
        *(str(path) for path in seal.FAMILY_PATHS["linear"].get("runners", ())),
        *(str(path) for path in seal.FAMILY_PATHS["linear"]["schemas"]),
    }
    for relative in source_paths:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".json":
            content = "{}\n"
        elif relative == runtime_lock.RUNTIME_DOCKERFILE.as_posix():
            content = f"FROM {runtime_lock.BASE_IMAGE}\n"
        elif relative.endswith("requirements-cp312-manylinux2014-x86_64.lock"):
            content = "demo==1 --hash=sha256:" + "1" * 64 + "\n"
        else:
            content = f"# {relative}\n"
        path.write_text(content, encoding="utf-8")
    _run(repo, "init", "-q")
    _run(repo, "add", ".")
    _run(
        repo,
        "-c",
        "user.name=Codex Test",
        "-c",
        "user.email=codex@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    source_sha = _run(repo, "rev-parse", "HEAD")
    tree_sha = _run(repo, "rev-parse", "HEAD^{tree}")

    package = repo / "artifacts/package"
    package.mkdir(parents=True)
    (package / "requirements.txt").write_bytes(requirements_bytes())
    (package / "manifest.json").write_text("{}\n", encoding="utf-8")
    receipt = repo / ".ci/test/technical-receipt.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "source_commit_sha": source_sha,
                "technical_contract_pass": True,
                "claims": seal.TECHNICAL_RECEIPT_CLAIMS["linear"],
                "cases": [
                    {
                        "case_id": "case-1",
                        "external_result": {
                            "path": ".ci/test/results/case-1.json"
                        },
                    }
                ],
            },
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    wheel_dir = tmp_path / "external-runtime" / "wheels"
    wheel_dir.mkdir(parents=True)
    wheel_bytes = {
        "openseespy": b"openseespy-wheel",
        "openseespylinux": b"openseespylinux-wheel",
    }
    (wheel_dir / "openseespy-3.7.1.2-py3-none-any.whl").write_bytes(
        wheel_bytes["openseespy"]
    )
    (wheel_dir / "openseespylinux-3.7.1.2-py3-none-any.whl").write_bytes(
        wheel_bytes["openseespylinux"]
    )
    monkeypatch.setattr(
        seal,
        "EXPECTED_WHEEL_HASHES",
        {
            name: hashlib.sha256(content).hexdigest()
            for name, content in wheel_bytes.items()
        },
    )
    for asset_id, content in wheel_bytes.items():
        policy = dict(runtime_lock.EXTERNAL_ASSET_POLICY[asset_id])
        policy["file_sha256"] = "sha256:" + hashlib.sha256(content).hexdigest()
        monkeypatch.setitem(runtime_lock.EXTERNAL_ASSET_POLICY, asset_id, policy)
    now = datetime.now(timezone.utc)
    prepared_at = (now - timedelta(minutes=2)).isoformat()
    executed_at = (now - timedelta(minutes=1)).isoformat()
    result = repo / ".ci/test/results/case-1.json"
    result.parent.mkdir(parents=True)
    result.write_text(
        json.dumps({"executed_at": executed_at}) + "\n",
        encoding="utf-8",
    )
    image_inspect = tmp_path / "image-inspect.json"
    image_inspect.write_text(
        json.dumps(
            [
                {
                    "Id": "sha256:" + "a" * 64,
                    "Os": "linux",
                    "Architecture": "amd64",
                    "RootFS": {"Layers": ["sha256:" + "b" * 64]},
                }
            ]
        ),
        encoding="utf-8",
    )
    runtime_payload = runtime_lock.build_preexecution_lock(
        repo_root=repo,
        family_id="linear",
        source_commit_sha=source_sha,
        source_tree_sha=tree_sha,
        asset_dir=wheel_dir,
        image_inspect_path=image_inspect,
        prepared_at=prepared_at,
    )
    expected_image = json.loads(json.dumps(runtime_payload["container_image"]))

    def verify_local_image(locked: dict) -> None:
        if locked != expected_image:
            raise seal.ProducerSealError("producer_runtime_image_binding_invalid")

    monkeypatch.setattr(seal, "_verify_local_image_binding", verify_local_image)
    runtime_manifest = repo / ".ci/test/runtime-preexecution-lock.json"
    runtime_manifest.write_text(
        json.dumps(runtime_payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "repo_root": repo,
        "family_id": "linear",
        "receipt_path": Path(".ci/test/technical-receipt.json"),
        "package_dir": Path("artifacts/package"),
        "runtime_asset_dir": wheel_dir,
        "runtime_lock_manifest": Path(
            ".ci/test/runtime-preexecution-lock.json"
        ),
        "out_path": Path(".ci/test/producer-seal.json"),
        "source_commit_sha": source_sha,
        "source_tree_sha": tree_sha,
        "repository": "owner/repository",
        "run_id": "100",
        "run_attempt": "1",
        "workflow_sha": source_sha,
        "candidate_artifact_name": "candidate-100-1",
    }


def test_producer_seal_binds_preexecution_runtime_without_promoting_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)

    payload = seal.build_seal(**kwargs)

    source_paths = {row["path"] for row in payload["source_binding"]["source_files"]}
    assert "canonical/requirements-cp312-manylinux2014-x86_64.lock" in source_paths
    runtime = payload["runtime_binding"]
    assert runtime["product_runtime_lock"]["path"].endswith(
        "/source-snapshot/canonical/requirements-cp312-manylinux2014-x86_64.lock"
    )
    assert runtime["all_external_runtime_assets_pre_execution_hash_locked"] is True
    assert runtime["runtime_asset_bytes_attached"] is False
    assert runtime["runtime_asset_metadata_sealed"] is True
    assert runtime["technical_authority_eligible"] is True
    assert runtime["blockers"] == []
    assert runtime["container_image"]["derived_image_id"] == "sha256:" + "a" * 64
    assert runtime["preexecution_lock"]["path"].endswith(
        "/runtime-preexecution-lock.json"
    )
    assert payload["claims"]["verification_level_2"] is False
    assert not any(row["path"].endswith(".whl") for row in payload["candidate_files"])


def test_execution_source_scope_contains_every_tracked_product_file() -> None:
    expected = set(
        subprocess.run(
            ["git", "ls-files", "--", "src/structural_analysis"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    )

    observed = set(seal.execution_source_paths(ROOT, "linear"))

    assert expected
    assert expected <= observed


def test_producer_seal_rejects_asset_changed_after_preexecution_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    asset = (
        kwargs["runtime_asset_dir"]
        / "openseespy-3.7.1.2-py3-none-any.whl"
    )
    asset.write_bytes(b"tampered-wheel")

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_lock_manifest_invalid"
    ):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_lock_prepared_after_external_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    manifest = kwargs["repo_root"] / kwargs["runtime_lock_manifest"]
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    result = json.loads(
        (kwargs["repo_root"] / ".ci/test/results/case-1.json").read_text(
            encoding="utf-8"
        )
    )
    executed_at = datetime.fromisoformat(result["executed_at"])
    payload["prepared_at"] = (executed_at + timedelta(minutes=1)).isoformat()
    payload["artifact_hash"] = runtime_lock._artifact_hash(payload)
    manifest.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_lock_not_pre_execution"
    ):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_tag_instead_of_content_addressed_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    manifest = kwargs["repo_root"] / kwargs["runtime_lock_manifest"]
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["container_image"]["derived_image_id"] = "runtime:latest"
    payload["artifact_hash"] = runtime_lock._artifact_hash(payload)
    manifest.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_lock_manifest_invalid"
    ):
        seal.build_seal(**kwargs)


@pytest.mark.parametrize(
    ("target", "key", "value"),
    [
        ("top", "verification_level_2", True),
        ("image", "release_readiness", True),
    ],
)
def test_producer_seal_rejects_extra_authority_fields_in_preexecution_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    key: str,
    value: bool,
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    manifest = kwargs["repo_root"] / kwargs["runtime_lock_manifest"]
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    container = payload if target == "top" else payload["container_image"]
    container[key] = value
    payload["artifact_hash"] = runtime_lock._artifact_hash(payload)
    manifest.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_lock_manifest_invalid"
    ):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_future_dated_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    result = kwargs["repo_root"] / ".ci/test/results/case-1.json"
    result.write_text(
        json.dumps({"executed_at": "2099-01-01T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_lock_not_pre_execution"
    ):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_receipt_authority_claim_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    receipt = kwargs["repo_root"] / kwargs["receipt_path"]
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["claims"]["design_authority"] = True
    receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(
        seal.ProducerSealError, match="producer_receipt_authority_invalid"
    ):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_rootfs_layer_changed_after_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    manifest = kwargs["repo_root"] / kwargs["runtime_lock_manifest"]
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["container_image"]["rootfs_layer_diff_ids"] = ["sha256:" + "c" * 64]
    payload["artifact_hash"] = runtime_lock._artifact_hash(payload)
    manifest.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_image_binding_invalid"
    ):
        seal.build_seal(**kwargs)


def test_modal_runtime_lock_rejects_missing_native_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)

    with pytest.raises(runtime_lock.RuntimeLockError, match="runtime_lock_asset_set_invalid"):
        runtime_lock.bind_external_assets(
            family_id="modal_buckling", asset_dir=kwargs["runtime_asset_dir"]
        )


def test_producer_seal_rejects_renamed_runtime_asset_in_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    source_asset = (
        kwargs["runtime_asset_dir"]
        / "openseespy-3.7.1.2-py3-none-any.whl"
    )
    leaked = kwargs["repo_root"] / ".ci/test/renamed-runtime.bin"
    leaked.write_bytes(source_asset.read_bytes())

    with pytest.raises(
        seal.ProducerSealError, match="producer_runtime_asset_bytes_attached"
    ):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_untracked_source_contamination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    source = kwargs["repo_root"] / "src/untracked_attack.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("raise RuntimeError('attack')\n", encoding="utf-8")

    with pytest.raises(seal.ProducerSealError, match="producer_tracked_source_dirty"):
        seal.build_seal(**kwargs)


def test_producer_seal_rejects_duplicate_receipt_keys_at_first_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    receipt = kwargs["repo_root"] / kwargs["receipt_path"]
    receipt.write_text(
        '{"source_commit_sha":"x","source_commit_sha":"y"}\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="duplicate_json_key:source_commit_sha"):
        seal.build_seal(**kwargs)
