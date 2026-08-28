from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
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
                "claims": {
                    "independent_operator_attested": False,
                    "legal_use_approved": False,
                    "verification_level_2": False,
                    "design_authority": False,
                    "commercial_equivalence": False,
                    "release_readiness": False,
                },
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
    return {
        "repo_root": repo,
        "family_id": "linear",
        "receipt_path": Path(".ci/test/technical-receipt.json"),
        "package_dir": Path("artifacts/package"),
        "wheel_dir": wheel_dir,
        "out_path": Path(".ci/test/producer-seal.json"),
        "source_commit_sha": source_sha,
        "source_tree_sha": tree_sha,
        "repository": "owner/repository",
        "run_id": "100",
        "run_attempt": "1",
        "workflow_sha": source_sha,
        "candidate_artifact_name": "candidate-100-1",
        "runtime_blockers": [],
    }


def test_producer_seal_binds_clean_tree_transitive_locks_and_candidate_bytes(
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
    assert payload["claims"]["verification_level_2"] is False
    assert not any(
        row["path"].endswith(".whl") for row in payload["candidate_files"]
    )


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


def test_mandatory_runtime_blocker_cannot_be_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    monkeypatch.setitem(
        seal.MANDATORY_RUNTIME_BLOCKERS,
        "linear",
        ("unlocked_external_runtime",),
    )

    payload = seal.build_seal(**kwargs)

    assert payload["runtime_binding"]["technical_authority_eligible"] is False
    assert payload["runtime_binding"]["blockers"] == ["unlocked_external_runtime"]


def test_producer_seal_marks_unlocked_native_runtime_non_promoting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kwargs = _fixture_repo(tmp_path, monkeypatch)
    kwargs["runtime_blockers"] = [
        "calculix_apt_transitive_bytes_not_pre_execution_hash_locked"
    ]

    payload = seal.build_seal(**kwargs)

    runtime = payload["runtime_binding"]
    assert runtime["all_external_runtime_assets_pre_execution_hash_locked"] is False
    assert runtime["runtime_asset_bytes_attached"] is False
    assert runtime["technical_authority_eligible"] is False
    assert runtime["blockers"] == kwargs["runtime_blockers"]


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
