from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github/workflows/python-test-collection.yml",
    ROOT / ".github/workflows/legacy-evidence-ci.yml",
)
IMMUTABLE_ACTION_RE = re.compile(
    r"^\s*uses:\s+actions/[A-Za-z0-9_.-]+@[0-9a-f]{40}(?:\s+#.*)?$"
)


def test_long_running_workflows_pin_first_party_actions_to_commit_shas() -> None:
    for workflow in WORKFLOWS:
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
    python_source = WORKFLOWS[0].read_text(encoding="utf-8")
    legacy_source = WORKFLOWS[1].read_text(encoding="utf-8")

    checkout = "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803"
    setup_python = "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1"
    upload = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"

    assert python_source.count(checkout) == 2
    assert python_source.count(setup_python) == 2
    assert legacy_source.count(checkout) == 1
    assert legacy_source.count(setup_python) == 1
    assert legacy_source.count(upload) == 1
