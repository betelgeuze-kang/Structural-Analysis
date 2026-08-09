from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_n1_evidence_boundary.py"
SPEC = importlib.util.spec_from_file_location("check_n1_evidence_boundary", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _run(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def evidence_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init", "-q")
    _run(repo, "config", "user.name", "N1 Boundary Test")
    _run(repo, "config", "user.email", "n1-boundary@example.invalid")
    (repo / "core.py").write_text("CORE = 1\n", encoding="utf-8")
    (repo / "generator.py").write_text("GENERATOR = 1\n", encoding="utf-8")
    _run(repo, "add", "core.py", "generator.py")
    _run(repo, "commit", "-qm", "source")
    source_commit = _run(repo, "rev-parse", "HEAD")

    core_checksum = _sha256((repo / "core.py").read_bytes())
    for name in ("full.json", "material.json"):
        _write_json(
            repo / "evidence" / name,
            {
                "source_commit_sha": source_commit,
                "input_checksums": {"core.py": core_checksum},
            },
        )
    _run(repo, "add", "evidence/full.json", "evidence/material.json")
    _run(repo, "commit", "-qm", "upstream receipts")
    aggregate_source = _run(repo, "rev-parse", "HEAD")

    full_checksum = _sha256((repo / "evidence/full.json").read_bytes())
    material_checksum = _sha256((repo / "evidence/material.json").read_bytes())
    _write_json(
        repo / "evidence" / "aggregate.json",
        {
            "aggregate_source": {
                "source_commit_sha": aggregate_source,
                "input_checksums": {
                    "generator.py": _sha256((repo / "generator.py").read_bytes()),
                    "evidence/full.json": full_checksum,
                    "evidence/material.json": material_checksum,
                },
            },
            "sources": {
                "actual": {
                    "path": "evidence/full.json",
                    "file_sha256": full_checksum,
                },
                "material": {
                    "path": "evidence/material.json",
                    "file_sha256": material_checksum,
                },
            },
        },
    )
    _run(repo, "add", "evidence/aggregate.json")
    _run(repo, "commit", "-qm", "aggregate")
    return repo, _run(repo, "rev-parse", "HEAD")


def _inspect(repo: Path, baseline: str):
    return module.inspect_n1_evidence_boundary(
        baseline_ref=baseline,
        repo_root=repo,
        aggregate_path=Path("evidence/aggregate.json"),
    )


def test_repository_n1_boundary_is_currently_intact() -> None:
    report = module.assert_n1_evidence_boundary(
        baseline_ref="636ce92a5a52bb1078ef8c5c3932cc5f34e0e825",
        repo_root=ROOT,
    )
    assert report.contract_pass is True
    assert report.bound_path_count == 34
    assert len(report.bound_inputs) >= report.bound_path_count


def test_guard_accepts_unchanged_transitive_fixture(
    evidence_repo: tuple[Path, str],
) -> None:
    repo, baseline = evidence_repo
    report = _inspect(repo, baseline)
    assert report.contract_pass is True
    assert report.bound_path_count == 4


def test_guard_rejects_uncommitted_workspace_checksum_drift(
    evidence_repo: tuple[Path, str],
) -> None:
    repo, baseline = evidence_repo
    (repo / "core.py").write_text("CORE = 2\n", encoding="utf-8")
    report = _inspect(repo, baseline)
    assert report.contract_pass is False
    assert any(
        row.code == "workspace_checksum_drift" and row.path == "core.py"
        for row in report.issues
    )


@pytest.mark.parametrize("operation", ("delete", "rename"))
def test_guard_rejects_bound_deletion_and_rename(
    evidence_repo: tuple[Path, str],
    operation: str,
) -> None:
    repo, baseline = evidence_repo
    if operation == "delete":
        _run(repo, "rm", "core.py")
    else:
        _run(repo, "mv", "core.py", "renamed-core.py")
    _run(repo, "commit", "-qm", operation)
    report = _inspect(repo, baseline)
    codes = {(row.code, row.path) for row in report.issues}
    assert ("workspace_input_missing", "core.py") in codes
    assert ("bound_path_changed_in_followup_diff", "core.py") in codes


def test_guard_rejects_recorded_source_checksum_drift(
    evidence_repo: tuple[Path, str],
) -> None:
    repo, baseline = evidence_repo
    upstream = json.loads((repo / "evidence/full.json").read_text(encoding="utf-8"))
    upstream["input_checksums"]["core.py"] = "sha256:" + "0" * 64
    _write_json(repo / "evidence/full.json", upstream)
    report = _inspect(repo, baseline)
    codes = {row.code for row in report.issues}
    assert "source_checksum_drift" in codes
    assert "workspace_checksum_drift" in codes


def test_guard_pins_aggregate_root_before_traversing_reduced_graph(
    evidence_repo: tuple[Path, str],
) -> None:
    repo, baseline = evidence_repo
    aggregate_path = repo / "evidence" / "aggregate.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    del aggregate["sources"]["material"]
    del aggregate["aggregate_source"]["input_checksums"]["evidence/material.json"]
    _write_json(aggregate_path, aggregate)

    report = _inspect(repo, baseline)

    assert report.contract_pass is False
    assert any(
        row.code == "aggregate_root_changed_from_baseline"
        and row.path == "evidence/aggregate.json"
        for row in report.issues
    )
