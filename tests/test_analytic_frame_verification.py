from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_analytic_frame_verification_artifact.py"
SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/analytic_frame_verification_v1.schema.json"
)

from structural_analysis.benchmark.analytic_frame import (  # noqa: E402
    ANALYTIC_FRAME_CATEGORIES,
    AnalyticFrameVerificationError,
    build_analytic_frame_verification_artifact,
    validate_analytic_frame_verification_artifact,
)


def test_three_frame_families_match_closed_form_without_fallback() -> None:
    payload = build_analytic_frame_verification_artifact(repo_root=ROOT)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert payload["contract_pass"] is True
    assert payload["summary"] == {
        "case_count": 3,
        "passing_case_count": 3,
        "categories": list(ANALYTIC_FRAME_CATEGORIES),
        "contract_pass": True,
    }
    assert [row["category"] for row in payload["cases"]] == list(
        ANALYTIC_FRAME_CATEGORIES
    )
    for case in payload["cases"]:
        assert case["status"] == "ready"
        assert case["contract_pass"] is True
        assert case["numerical_checks"]["contract_pass"] is True
        assert case["numerical_checks"]["fallback_used"] is False
        assert case["numerical_checks"]["regularization_used"] is False
        assert all(row["contract_pass"] for row in case["comparisons"])
    portal = payload["cases"][2]
    assert portal["formula_profile"] == "finite_ea_ei_portal_slope_deflection.v1"
    assert len(portal["comparisons"]) == 12
    assert max(row["absolute_error"] for row in portal["comparisons"]) > 0.0


def test_receipt_validation_rejects_hash_and_source_tampering() -> None:
    payload = build_analytic_frame_verification_artifact(repo_root=ROOT)
    tampered = deepcopy(payload)
    tampered["cases"][0]["comparisons"][0]["actual"] += 1.0

    with pytest.raises(AnalyticFrameVerificationError) as error:
        validate_analytic_frame_verification_artifact(
            tampered,
            repo_root=ROOT,
            rerun=False,
        )
    assert str(error.value) == "analytic_frame_artifact_hash_mismatch"

    stale = deepcopy(payload)
    stale["source"]["input_checksums"][
        "src/structural_analysis/solvers/linear/static.py"
    ] = "sha256:" + "0" * 64
    without_hash = {
        key: value for key, value in stale.items() if key != "artifact_hash"
    }
    import hashlib

    stale["artifact_hash"] = "sha256:" + hashlib.sha256(
        json.dumps(
            without_hash,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    with pytest.raises(AnalyticFrameVerificationError) as source_error:
        validate_analytic_frame_verification_artifact(
            stale,
            repo_root=ROOT,
            rerun=False,
        )
    assert str(source_error.value) in {
        "analytic_frame_source_set_hash_mismatch",
        "analytic_frame_sources_stale",
    }


def test_cli_write_and_offline_reproduction_check(tmp_path: Path) -> None:
    out = tmp_path / "analytic-frame.json"
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
    assert "cases=3/3" in write.stdout
    assert check.returncode == 0, check.stderr
    assert "analytic_frame_verification_consistent" in check.stdout
