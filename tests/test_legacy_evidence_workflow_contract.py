from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_shards_retain_pytest_diagnostics_before_license_gate() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/legacy-evidence-ci.yml").read_text(
            encoding="utf-8"
        )
    )
    jobs = workflow["jobs"]
    shard = jobs["legacy-evidence-shards"]
    steps = shard["steps"]
    names = [step["name"] for step in steps]
    materialize_name = "Materialize exact current-source V&V inputs"
    test_name = "Deterministic legacy evidence contracts shard"
    upload_name = (
        "Retain diagnostic legacy evidence shard result independently of license status"
    )
    gate_name = "Require exact current-source external license contract"
    assert names.index(materialize_name) < names.index(test_name) < names.index(
        upload_name
    ) < names.index(gate_name)

    named_steps = {step["name"]: step for step in steps}
    materialize = named_steps[materialize_name]
    assert materialize["id"] == "materialize"
    assert "python scripts/build_internal_license_due_diligence.py" in materialize["run"]
    assert "--fail-blocked" not in materialize["run"]
    assert "if" not in named_steps[test_name]
    assert "--junitxml=legacy-evidence-shard-${{ matrix.shard }}.xml" in (
        named_steps[test_name]["run"]
    )
    assert "$LEGACY_TEST_MODULES" in named_steps[test_name]["run"]

    upload = named_steps[upload_name]
    assert upload["if"] == "${{ always() }}"
    assert upload["with"] == {
        "name": "legacy-evidence-shard-diagnostic-${{ matrix.shard }}-${{ github.sha }}",
        "path": "legacy-evidence-shard-${{ matrix.shard }}.xml",
        "if-no-files-found": "warn",
        "retention-days": 14,
    }
    gate = named_steps[gate_name]
    assert gate["if"] == "${{ always() && steps.materialize.outcome == 'success' }}"
    assert gate["run"] == (
        "python scripts/build_internal_license_due_diligence.py "
        '--out "$RUNNER_TEMP/internal-license-gate.json" --fail-blocked'
    )
    assert all(not step.get("continue-on-error", False) for step in steps)
    assert jobs["legacy-evidence-complete"]["if"] == "${{ always() }}"
    assert jobs["legacy-evidence-complete"]["needs"] == [
        "legacy-evidence",
        "legacy-evidence-shards",
    ]
