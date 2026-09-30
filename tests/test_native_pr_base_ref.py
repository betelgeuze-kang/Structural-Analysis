from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
from urllib.error import URLError

import pytest
import yaml

from scripts import classify_native_ci_scope as scope
from scripts import verify_native_pr_base_ref as gate


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PATH = "implementation/phase1/release_evidence/productization/receipt.json"


@dataclass(frozen=True)
class GitGraph:
    root: Path
    event_base: str
    base: str
    head: str
    merge: str
    next_base: str


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def graph(tmp_path: Path) -> GitGraph:
    _git(tmp_path, "init", "-q", "-b", "base")
    _git(tmp_path, "config", "user.name", "Native CI Test")
    _git(tmp_path, "config", "user.email", "native-ci-test@example.invalid")
    (tmp_path / "README.md").write_text("initial\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "event base")
    event_base = _git(tmp_path, "rev-parse", "HEAD")

    _git(tmp_path, "checkout", "-qb", "feature")
    (tmp_path / "native").mkdir()
    (tmp_path / "native/Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    _git(tmp_path, "add", "native/Cargo.toml")
    _git(tmp_path, "commit", "-qm", "feature")
    head = _git(tmp_path, "rev-parse", "HEAD")

    _git(tmp_path, "checkout", "-q", "base")
    protected = tmp_path / PROTECTED_PATH
    protected.parent.mkdir(parents=True)
    protected.write_text("synthetic base-only fixture\n", encoding="utf-8")
    _git(tmp_path, "add", PROTECTED_PATH)
    _git(tmp_path, "commit", "-qm", "base advance")
    base = _git(tmp_path, "rev-parse", "HEAD")

    _git(tmp_path, "checkout", "-qb", "merge-ref")
    (tmp_path / "native").mkdir()
    (tmp_path / "native/Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    _git(tmp_path, "add", "native/Cargo.toml")
    merged_tree = _git(tmp_path, "write-tree")
    merge = _git(
        tmp_path,
        "commit-tree",
        merged_tree,
        "-p",
        base,
        "-p",
        head,
        "-m",
        "synthetic PR merge ref",
    )
    _git(tmp_path, "update-ref", "refs/heads/merge-ref", merge)
    assert _git(tmp_path, "show", "-s", "--format=%P", "HEAD") == f"{base} {head}"

    _git(tmp_path, "checkout", "-q", "base")
    _git(tmp_path, "checkout", "-qb", "base-next")
    (tmp_path / "base-next.txt").write_text("newer base\n", encoding="utf-8")
    _git(tmp_path, "add", "base-next.txt")
    _git(tmp_path, "commit", "-qm", "base advanced after merge ref")
    next_base = _git(tmp_path, "rev-parse", "HEAD")
    return GitGraph(tmp_path, event_base, base, head, merge, next_base)


def _fetch_for(graph: GitGraph, *, current_tip: str):
    calls: list[str] = []

    def fetch(path: str):
        calls.append(path)
        if "/git/ref/heads/" in path:
            return {"ref": "refs/heads/base", "object": {"sha": current_tip}}
        if "/compare/" in path:
            event_base, tested_base = path.rsplit("/", 1)[-1].split("...")
            merge_base = _git(graph.root, "merge-base", event_base, tested_base)
            if merge_base == event_base:
                status, behind = "ahead", 0
            elif merge_base == tested_base:
                status, behind = "behind", 1
            else:
                status, behind = "diverged", 1
            return {
                "status": status,
                "behind_by": behind,
                "merge_base_commit": {"sha": merge_base},
            }
        raise AssertionError(f"unexpected API path: {path}")

    return fetch, calls


def _verify(graph: GitGraph, *, event_base: str, current_tip: str) -> bool:
    fetch, _ = _fetch_for(graph, current_tip=current_tip)
    return gate.verify_base_ref(
        repository="example/structural",
        base_ref="base",
        event_base_sha=event_base,
        tested_base_sha=graph.base,
        fetch=fetch,
    )


def test_exact_event_base_and_current_named_branch_pass(graph: GitGraph) -> None:
    fetch, calls = _fetch_for(graph, current_tip=graph.base)
    assert (
        gate.verify_base_ref(
            repository="example/structural",
            base_ref="base",
            event_base_sha=graph.base,
            tested_base_sha=graph.base,
            fetch=fetch,
        )
        is False
    )
    assert len(calls) == 1


def test_stale_event_base_with_genuine_forward_advance_passes(graph: GitGraph) -> None:
    fetch, calls = _fetch_for(graph, current_tip=graph.base)
    assert (
        gate.verify_base_ref(
            repository="example/structural",
            base_ref="base",
            event_base_sha=graph.event_base,
            tested_base_sha=graph.base,
            fetch=fetch,
        )
        is True
    )
    assert len(calls) == 2


def test_unrelated_event_base_or_force_rewrite_is_rejected(graph: GitGraph) -> None:
    with pytest.raises(gate.RefIdentityError, match="does not descend"):
        _verify(graph, event_base=graph.head, current_tip=graph.base)


def test_stale_merge_parent_is_rejected_even_when_it_descends_from_event_base(
    graph: GitGraph,
) -> None:
    _git(graph.root, "update-ref", "refs/heads/base", graph.next_base)
    with pytest.raises(gate.RefIdentityError, match="not the current base tip"):
        _verify(graph, event_base=graph.event_base, current_tip=graph.next_base)


def test_api_failure_and_wrong_named_ref_fail_closed(
    graph: GitGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_request, *, timeout: int):
        raise URLError("offline")

    monkeypatch.setattr(gate, "urlopen", unavailable)
    with pytest.raises(gate.RefIdentityError, match="API request failed"):
        gate._github_fetch("repos/example/structural/git/ref/heads/base", token="fake")
    with pytest.raises(gate.RefIdentityError, match="named base branch identity"):
        gate.verify_base_ref(
            repository="example/structural",
            base_ref="base",
            event_base_sha=graph.base,
            tested_base_sha=graph.base,
            fetch=lambda _path: {
                "ref": "refs/heads/another",
                "object": {"sha": graph.base},
            },
        )


def test_exact_merge_head_mismatch_is_rejected_before_api_lookup(
    graph: GitGraph,
    tmp_path: Path,
) -> None:
    _git(graph.root, "checkout", "-q", "merge-ref")
    workflow = yaml.load(
        (ROOT / ".github/workflows/native-pr-fast.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    step = next(
        step
        for step in workflow["jobs"]["scope-contract"]["steps"]
        if step["name"] == "Verify exact tested ref identity"
    )
    run = step["run"].replace("${{ github.event.merge_group.head_sha }}", "unused")
    output = tmp_path / "github-output.txt"
    env = {
        **os.environ,
        "EVENT_NAME": "pull_request",
        "EXPECTED_BASE_SHA": graph.event_base,
        "EXPECTED_BASE_REF": "base",
        "EXPECTED_HEAD_SHA": graph.event_base,
        "EXPECTED_MERGE_SHA": graph.merge,
        "GITHUB_REPOSITORY": "example/structural",
        "GITHUB_TOKEN": "fake",
        "GITHUB_OUTPUT": str(output),
    }
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", run],
        cwd=graph.root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "merge-ref head parent mismatch" in result.stderr
    assert not output.exists()


def test_classifier_uses_verified_merge_parent_not_base_only_protected_change(
    graph: GitGraph,
) -> None:
    changed = scope._git_changed_paths(
        base=graph.base, head=graph.merge, repo_root=graph.root
    )
    assert changed == ["native/Cargo.toml"]
    assert scope.classify_paths(changed)["protected_evidence"] is False
    stale_changed = scope._git_changed_paths(
        base=graph.event_base, head=graph.merge, repo_root=graph.root
    )
    assert PROTECTED_PATH in stale_changed
    assert scope.classify_paths(stale_changed)["protected_evidence"] is True
    assert "scripts/verify_native_pr_base_ref.py" in scope.NATIVE_CI_CONTROL_PATHS
    assert "tests/test_native_pr_base_ref.py" in scope.NATIVE_CI_CONTROL_PATHS
