from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = (
    ROOT / "artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json",
    ROOT / "artifacts/vv/opensees_calculix_clean_runner/external_code_to_code_receipt.json",
    ROOT / "artifacts/vv/opensees_calculix_clean_runner/external_modal_buckling_receipt.json",
)

AncestryQuery = Callable[[str, str], bool]
ParentQuery = Callable[[str], set[str]]


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


def _commit_exists(commit: str) -> bool:
    return _git("cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode == 0


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    return (
        _git("merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode
        == 0
    )


def _direct_parents(commit: str) -> set[str]:
    raw_commit = _git("cat-file", "-p", commit).stdout
    return {
        line.removeprefix("parent ")
        for line in raw_commit.splitlines()
        if line.startswith("parent ")
    }


def _ancestry_proven(
    *,
    recorded_commit: str,
    head: str,
    shallow_repository: bool,
    is_ancestor: AncestryQuery,
    direct_parents: ParentQuery,
) -> bool:
    if is_ancestor(recorded_commit, head):
        return True
    if not shallow_repository:
        return False
    parents = direct_parents(head)
    return bool(parents) and any(
        parent == recorded_commit or is_ancestor(recorded_commit, parent)
        for parent in parents
    )


def _recorded_receipt_commit() -> str:
    commits = {
        json.loads(path.read_text(encoding="utf-8"))["source_commit_sha"]
        for path in RECEIPTS
    }
    assert len(commits) == 1
    commit = commits.pop()
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    return commit


def test_exact_receipt_commit_object_exists_and_is_proven_in_head_ancestry() -> None:
    recorded_commit = _recorded_receipt_commit()
    head = _git("rev-parse", "HEAD").stdout.strip()
    shallow_repository = (
        _git("rev-parse", "--is-shallow-repository").stdout.strip() == "true"
    )

    assert _commit_exists(recorded_commit), (
        "recorded receipt commit object is unavailable; ancestry cannot be proven"
    )
    assert _ancestry_proven(
        recorded_commit=recorded_commit,
        head=head,
        shallow_repository=shallow_repository,
        is_ancestor=_is_ancestor,
        direct_parents=_direct_parents,
    )


def test_shallow_synthetic_merge_accepts_a_deeper_parent_ancestor() -> None:
    relationships = {
        ("recorded", "merge"): False,
        ("recorded", "base-parent"): True,
        ("recorded", "feature-parent"): False,
    }

    assert _ancestry_proven(
        recorded_commit="recorded",
        head="merge",
        shallow_repository=True,
        is_ancestor=lambda ancestor, descendant: relationships.get(
            (ancestor, descendant), False
        ),
        direct_parents=lambda _commit: {"base-parent", "feature-parent"},
    )


def test_unrelated_commit_is_rejected_even_when_its_object_exists() -> None:
    assert not _ancestry_proven(
        recorded_commit="unrelated",
        head="merge",
        shallow_repository=True,
        is_ancestor=lambda _ancestor, _descendant: False,
        direct_parents=lambda _commit: {"base-parent", "feature-parent"},
    )


def test_nonshallow_history_never_uses_parent_fallback() -> None:
    parent_query_called = False

    def parents(_commit: str) -> set[str]:
        nonlocal parent_query_called
        parent_query_called = True
        return {"base-parent"}

    assert not _ancestry_proven(
        recorded_commit="recorded",
        head="head",
        shallow_repository=False,
        is_ancestor=lambda _ancestor, _descendant: False,
        direct_parents=parents,
    )
    assert parent_query_called is False
