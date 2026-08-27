from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "workflow-contract-ci.yml"


def _hydration_block() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    return workflow.split(
        "- name: Hydrate direct and nested merge-parent ancestry for provenance tests",
        1,
    )[1].split("- name: Set up Python", 1)[0]


def _executable_lines(block: str) -> list[str]:
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_ancestry_hydration_disables_automatic_git_maintenance() -> None:
    block = _hydration_block()

    assert "git config maintenance.auto false" in block
    assert "git config gc.auto 0" in block
    assert block.count("git -c maintenance.auto=false -c gc.auto=0 fetch") == 2


def test_ancestry_hydration_batches_each_commit_generation_once() -> None:
    block = _hydration_block()

    assert '--no-tags --depth=512 origin "${parents[@]}"' in block
    assert '--no-tags --depth=512 origin "${nested_parents[@]}"' in block

    executable = _executable_lines(block)
    assert not any('origin "$parent"' in line for line in executable)
    assert not any('origin "$nested_parent"' in line for line in executable)


def test_ancestry_hydration_verifies_every_requested_commit_object() -> None:
    block = _hydration_block()

    assert 'git cat-file -e "${parent}^{commit}"' in block
    assert 'git cat-file -e "${nested_parent}^{commit}"' in block
    assert 'git cat-file -e "${GITHUB_SHA}^{commit}"' in block
