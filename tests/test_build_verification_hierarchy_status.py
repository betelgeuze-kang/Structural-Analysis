from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_verification_hierarchy_status.py"
spec = importlib.util.spec_from_file_location(
    "build_verification_hierarchy_status",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_current_hierarchy_completes_level_one_analytic_families() -> None:
    payload = module.build_verification_hierarchy_status(repo_root=ROOT)

    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["highest_verified_level"] == 1
    assert payload["evidence_count"] == 5
    assert payload["ready_evidence_count"] == 5
    analytic = payload["level_rows"][0]
    assert analytic["status"] == "ready"
    assert analytic["intrinsic_contract_pass"] is True
    assert analytic["promotion_contract_pass"] is True
    slots = {row["category"]: row for row in analytic["slot_rows"]}
    assert slots["single_bar"]["contract_pass"] is True
    assert slots["patch_tests"]["contract_pass"] is True
    assert slots["cantilever_beam"]["contract_pass"] is True
    assert slots["simply_supported_beam"]["contract_pass"] is True
    assert slots["portal_frame"]["contract_pass"] is True
    assert all(row["status"] == "missing" for row in payload["level_rows"][1:])


def test_hierarchy_status_cli_write_and_check(tmp_path: Path) -> None:
    out = tmp_path / "verification-hierarchy.json"
    write = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    check = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert write.returncode == 0, write.stderr
    assert "highest_level=1/5" in write.stdout
    assert check.returncode == 0, check.stderr
    assert "verification_hierarchy_status_consistent" in check.stdout


def test_invalid_operator_manifest_does_not_fall_back_silently(
    tmp_path: Path,
) -> None:
    operator = tmp_path / module.DEFAULT_OPERATOR_EVIDENCE
    operator.parent.mkdir(parents=True, exist_ok=True)
    operator.write_text('{"evidence": []}\n', encoding="utf-8")

    payload = module.build_verification_hierarchy_status(repo_root=tmp_path)

    assert payload["contract_pass"] is False
    assert payload["input_blockers"] == [
        "verification_hierarchy_operator_manifest_claim_boundary_missing",
        "verification_hierarchy_operator_manifest_schema_invalid",
    ]


def test_invalid_analytic_frame_artifact_fails_three_slots_closed(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "analytic-frame.json"
    artifact.write_text('{"schema_version":"wrong"}\n', encoding="utf-8")

    payload = module.build_verification_hierarchy_status(
        repo_root=ROOT,
        analytic_frame_artifact_path=artifact,
    )

    assert payload["highest_verified_level"] == 0
    analytic = payload["level_rows"][0]
    slots = {row["category"]: row for row in analytic["slot_rows"]}
    assert slots["single_bar"]["contract_pass"] is True
    assert slots["patch_tests"]["contract_pass"] is True
    for category in module.ANALYTIC_FRAME_CATEGORIES:
        assert slots[category]["contract_pass"] is False
        evidence = next(
            row for row in payload["evidence_rows"] if row["category"] == category
        )
        assert any(
            blocker.startswith("analytic_frame_artifact_invalid:")
            for blocker in evidence["blockers"]
        )


def test_operator_manifest_schema_is_valid() -> None:
    schema = json.loads(
        (
            ROOT
            / "src/structural_analysis/schemas/structural_verification_evidence_manifest_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
