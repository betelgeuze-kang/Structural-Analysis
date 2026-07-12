from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "build_phase1_core_api_contract_artifacts.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_phase1_core_api_contract_artifacts_source_state",
    SCRIPT_PATH,
)
assert SPEC is not None
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _init_repo(path: Path) -> None:
    subprocess.check_call(["git", "init"], cwd=path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"],
        cwd=path,
    )
    subprocess.check_call(
        ["git", "config", "user.name", "Test"],
        cwd=path,
    )


def _commit_all(path: Path, message: str) -> str:
    subprocess.check_call(["git", "add", "."], cwd=path)
    subprocess.check_call(
        ["git", "commit", "-m", message],
        cwd=path,
        stdout=subprocess.DEVNULL,
    )
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        text=True,
    ).strip()


def _summaries(source: str, head: str) -> tuple[dict, dict]:
    existing = {
        "schema_version": "phase1-core-api-contract-artifacts.v2",
        "generated_at": "2026-07-12T00:00:00+00:00",
        "source_commit_sha": source,
        "source_state_policy": {
            "mode": "source_commit_then_evidence_only_commit",
            "source_commit_sha": source,
            "exact_head_verification_required": True,
            "allowed_post_source_scope": (
                "generated_phase1_and_readiness_evidence_only"
            ),
        },
        "contract_pass": True,
    }
    expected = json.loads(json.dumps(existing))
    expected["source_commit_sha"] = head
    expected["source_state_policy"]["source_commit_sha"] = head
    expected["generated_at"] = "2026-07-12T00:00:01+00:00"
    return existing, expected


def test_source_state_accepts_one_evidence_only_commit(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "source.py").write_text("SOURCE = True\n", encoding="utf-8")
    source = _commit_all(tmp_path, "source")

    evidence = (
        tmp_path
        / "implementation/phase1/release_evidence/productization/"
        "phase1_core_api_contract_summary.json"
    )
    evidence.parent.mkdir(parents=True)
    evidence.write_text("{}\n", encoding="utf-8")
    head = _commit_all(tmp_path, "evidence")

    existing, expected = _summaries(source, head)
    normalized = module._expected_summary_for_verified_source_state(
        existing=existing,
        expected=expected,
        repo_root=tmp_path,
    )

    assert normalized["source_commit_sha"] == source
    assert normalized["source_state_policy"]["source_commit_sha"] == source
    assert module._strip_volatile(existing) == module._strip_volatile(normalized)


def test_source_state_rejects_non_evidence_change_after_source(
    tmp_path: Path,
) -> None:
    _init_repo(tmp_path)
    source_file = tmp_path / "source.py"
    source_file.write_text("SOURCE = True\n", encoding="utf-8")
    source = _commit_all(tmp_path, "source")

    source_file.write_text("SOURCE = False\n", encoding="utf-8")
    head = _commit_all(tmp_path, "semantic source change")

    existing, expected = _summaries(source, head)
    with pytest.raises(
        ValueError,
        match="non_evidence_paths_changed_after_source_commit:source.py",
    ):
        module._expected_summary_for_verified_source_state(
            existing=existing,
            expected=expected,
            repo_root=tmp_path,
        )


def test_source_commit_remains_part_of_nonvolatile_comparison() -> None:
    left = {"source_commit_sha": "abc", "generated_at": "one"}
    right = {"source_commit_sha": "def", "generated_at": "two"}

    assert module._strip_volatile(left) != module._strip_volatile(right)


def test_resync_workflow_tracks_source_state_contract() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/authoritative-core-evidence-resync.yml"
    ).read_text(encoding="utf-8")

    assert 'tests/test_phase1_core_api_source_state.py' in workflow
    assert 'source_commit_then_evidence_only_commit' in workflow
    assert 'Verify exact evidence head' in workflow
