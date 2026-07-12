from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "verify_phase1_evidence_source_state.py"
)
SPEC = importlib.util.spec_from_file_location(
    "verify_phase1_evidence_source_state_test",
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


def test_source_state_accepts_generated_evidence_only_commit(
    tmp_path: Path,
) -> None:
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

    receipt = module.verify_source_state(
        repo_root=tmp_path,
        source_commit=source,
        head_commit=head,
    )

    assert receipt["contract_pass"] is True
    assert receipt["source_is_ancestor"] is True
    assert receipt["changed_paths"] == [
        "implementation/phase1/release_evidence/productization/"
        "phase1_core_api_contract_summary.json"
    ]
    assert receipt["disallowed_paths"] == []
    assert receipt["policy"]["integration_requirement"] == (
        "regular_merge_commit_preserves_source_ancestry"
    )


def test_source_state_rejects_code_change_after_source(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    source_file = tmp_path / "source.py"
    source_file.write_text("SOURCE = True\n", encoding="utf-8")
    source = _commit_all(tmp_path, "source")

    source_file.write_text("SOURCE = False\n", encoding="utf-8")
    head = _commit_all(tmp_path, "semantic source change")

    receipt = module.verify_source_state(
        repo_root=tmp_path,
        source_commit=source,
        head_commit=head,
    )

    assert receipt["contract_pass"] is False
    assert receipt["disallowed_paths"] == ["source.py"]
    assert receipt["blockers"] == [
        "non_evidence_path_changed_after_source:source.py"
    ]


def test_source_state_rejects_unrelated_history(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "source.py").write_text("SOURCE = True\n", encoding="utf-8")
    source = _commit_all(tmp_path, "source")

    subprocess.check_call(["git", "checkout", "--orphan", "other"], cwd=tmp_path)
    subprocess.check_call(["git", "rm", "-rf", "."], cwd=tmp_path)
    (tmp_path / "other.py").write_text("OTHER = True\n", encoding="utf-8")
    head = _commit_all(tmp_path, "other history")

    receipt = module.verify_source_state(
        repo_root=tmp_path,
        source_commit=source,
        head_commit=head,
    )

    assert receipt["contract_pass"] is False
    assert receipt["source_is_ancestor"] is False
    assert receipt["blockers"] == ["source_commit_not_ancestor_of_head"]


def test_resync_workflow_invokes_exact_head_verifier() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github/workflows/authoritative-core-evidence-resync.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/verify_phase1_evidence_source_state.py" in workflow
    assert "--source-commit" in workflow
    assert "--fail-blocked" in workflow
