from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release-publish.yml"


def test_release_publish_workflow_keeps_publication_gates_in_order() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    expected_order = [
        "Source boundary preflight",
        "Regenerate release viewer artifacts",
        "Build fresh publication candidate",
        "Publish manifest-listed release assets",
        "Verify published release closure",
        "Upload publication evidence",
        "Promote verified manifest",
    ]
    positions = [text.index(label) for label in expected_order]

    assert positions == sorted(positions)
    assert "permissions:\n  contents: write" in text
    assert "scripts/publish_github_release_assets.py" in text
    assert "--replace-existing" in text
    assert "scripts/check_release_p0_closure.py" in text
    assert "implementation/phase1/release_artifacts_manifest.json" in text
