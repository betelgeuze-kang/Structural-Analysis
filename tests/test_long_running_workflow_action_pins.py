from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATHS = {
    "repository_python": ROOT / ".github/workflows/python-test-collection.yml",
    "legacy_evidence": ROOT / ".github/workflows/legacy-evidence-ci.yml",
    "workflow_contract": ROOT / ".github/workflows/workflow-contract-ci.yml",
}
IMMUTABLE_ACTION_RE = re.compile(
    r"^\s*uses:\s+actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def test_reviewed_workflows_pin_first_party_actions_to_commit_shas() -> None:
    for workflow in WORKFLOW_PATHS.values():
        source = workflow.read_text(encoding="utf-8")
        action_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith("uses: actions/")
        ]
        assert action_lines, workflow
        assert all(IMMUTABLE_ACTION_RE.fullmatch(line) for line in action_lines), (
            workflow,
            action_lines,
        )


def test_exact_reviewed_action_pins_are_retained() -> None:
    sources = {
        name: path.read_text(encoding="utf-8") for name, path in WORKFLOW_PATHS.items()
    }
    checkout = "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    setup_python = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
    upload = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"

    assert sources["repository_python"].count(checkout) == 2
    assert sources["repository_python"].count(setup_python) == 2
    assert upload not in sources["repository_python"]

    assert sources["legacy_evidence"].count(checkout) == 2
    assert sources["legacy_evidence"].count(setup_python) == 2
    assert sources["legacy_evidence"].count(upload) == 1

    assert sources["workflow_contract"].count(checkout) == 1
    assert sources["workflow_contract"].count(setup_python) == 1
    assert sources["workflow_contract"].count(upload) == 1


def test_workflow_contract_hydrates_nested_merge_parents_in_batched_fetches() -> None:
    source = WORKFLOW_PATHS["workflow_contract"].read_text(encoding="utf-8")

    assert "Hydrate direct and nested merge-parent ancestry" in source
    assert "git config maintenance.auto false" in source
    assert "git config gc.auto 0" in source
    assert 'git cat-file -p "$parent"' in source
    assert '--no-tags --depth=512 origin "${parents[@]}"' in source
    assert '--no-tags --depth=512 origin "${nested_parents[@]}"' in source
    assert 'git cat-file -e "${parent}^{commit}"' in source
    assert 'git cat-file -e "${nested_parent}^{commit}"' in source
