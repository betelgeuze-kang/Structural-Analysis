from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "workflow-contract-ci.yml"


def _ancestry_block() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    return workflow.split(
        "- name: Verify local direct and nested merge-parent ancestry",
        1,
    )[1].split("- name: Set up Python", 1)[0]


def _executable_lines(block: str) -> list[str]:
    return [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def test_ancestry_validation_uses_full_checkout_without_remote_hydration() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    block = _ancestry_block()

    checkout = workflow.split(
        "uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        1,
    )[1].split("\n\n", 1)[0]
    assert "fetch-depth: 0" in checkout
    assert "persist-credentials: false" in checkout
    assert "git fetch" not in block
    assert " origin " not in block


def test_ancestry_validation_derives_each_commit_generation_locally() -> None:
    block = _ancestry_block()

    assert "git cat-file -p HEAD" in block
    assert 'git cat-file -p "$parent"' in block
    executable = _executable_lines(block)
    assert not any("fetch" in line for line in executable)


def test_ancestry_validation_verifies_every_requested_commit_object() -> None:
    block = _ancestry_block()

    assert 'git cat-file -e "${parent}^{commit}"' in block
    assert 'git cat-file -e "${nested_parent}^{commit}"' in block
    assert 'git cat-file -e "${GITHUB_SHA}^{commit}"' in block
