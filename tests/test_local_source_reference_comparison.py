"""Local-build report contracts; stored values here are fixtures, not new runs."""

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, ValidationError
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
local = importlib.import_module("run_local_source_reference_comparison")
base = local.base


def fixture_report():
    stored = json.loads(
        (
            ROOT
            / "implementation/phase1/release_evidence/productization/external_code_to_code_technical_execution_receipt.json"
        ).read_bytes()
    )
    cases = deepcopy(stored["comparisons"])
    for row in cases:
        if row["reference_solver"] == "OpenSees 3.7.1":
            row["reference_solver"] = local.REFERENCE_NAME
    sha = "sha256:" + "1" * 64
    opensees = {
        "return_code": 0,
        "binding": {
            "profile_id": local.PROFILE_ID,
            "binary_sha256": local.BINARY_HASH,
            "module_origin": "opensees.so",
        },
        "stdout_sha256": sha,
        "stderr_sha256": sha,
        "parent_wall_ns": 1,
        "driver_sha256": base._text_hash(
            base.OPENSEES_DRIVER.replace(
                "import openseespy.opensees as ops", "import opensees as ops"
            )
        ),
    }
    calculix = deepcopy(stored["runtimes"]["calculix"]["execution_outputs"])
    calculix.update({"parent_wall_ns": 1, "binary_sha256": sha})
    raw = {"source-opensees.stdout": sha, "source-opensees.stderr": sha}
    for prefix, stem in (("", "axial"), ("spatial_truss_", "spatial_truss")):
        for key, suffix in (
            ("stdout_sha256", "stdout"),
            ("stderr_sha256", "stderr"),
            ("input_deck_sha256", "inp"),
            ("dat_sha256", "dat"),
            ("frd_sha256", "frd"),
        ):
            raw["calculix/" + stem + "." + suffix] = calculix[prefix + key]
    report = {
        "schema_version": local.SCHEMA_VERSION,
        "source_commit_sha": "1" * 40,
        "source_checksums": {},
        "profile": json.loads(local.PROFILE_PATH.read_bytes()),
        "authority": dict(local.AUTHORITY),
        "comparisons": cases,
        "reference_assets": {
            n: p["sha256"]
            for n, p in base.EXTERNAL_ASSET_POLICY.items()
            if n.endswith(".deb")
        },
        "executions": {
            "opensees": opensees,
            "calculix": calculix,
            "product_comparison_parent_wall_ns": 1,
        },
        "comparison_pass": True,
        "raw_files": raw,
        "parent_wall_ns": 1,
    }
    report["artifact_hash"] = base._artifact_hash(report)
    return report


def test_full_local_contract_keeps_all_cases_and_cannot_be_official_receipt():
    report = fixture_report()
    local.validate_report(report, ROOT)
    assert len(report["comparisons"]) == 12
    schema = json.loads((ROOT / base.SCHEMA_PATH).read_bytes())
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(report)


@pytest.mark.parametrize(
    "change",
    [
        "authority",
        "authority_number",
        "profile",
        "official_label",
        "case_missing",
        "raw",
        "tolerance",
        "metric",
        "pass",
        "cost",
        "binding",
    ],
)
def test_rehashed_invalid_report_rejects(change):
    report = fixture_report()
    if change == "authority":
        report["authority"]["reference_profile_adopted"] = True
    elif change == "authority_number":
        report["authority"]["reference_profile_adopted"] = 0
    elif change == "profile":
        report["profile"]["patch_sha256"] = "2" * 64
    elif change == "official_label":
        report["comparisons"][0]["reference_solver"] = "OpenSees 3.7.1"
    elif change == "case_missing":
        report["comparisons"].pop()
    elif change == "raw":
        report["raw_files"]["calculix/axial.dat"] = "sha256:" + "2" * 64
    elif change == "tolerance":
        report["comparisons"][0]["metrics"][0]["relative_tolerance"] *= 100
    elif change == "metric":
        report["comparisons"][0]["metrics"][0]["product_value"] += 1
    elif change == "pass":
        report["comparison_pass"] = False
    elif change == "cost":
        report["executions"]["opensees"]["parent_wall_ns"] = True
    else:
        report["executions"]["opensees"]["binding"]["binary_sha256"] = "2" * 64
    report["artifact_hash"] = base._artifact_hash(report)
    with pytest.raises((ValueError, ValidationError)):
        local.validate_report(report, ROOT)


def test_failed_case_cannot_be_counted_as_success():
    report = fixture_report()
    report["comparisons"][0]["external_return_code"] = 3
    report["artifact_hash"] = base._artifact_hash(report)
    with pytest.raises(ValueError, match="receipt_case_pass_invalid"):
        local.validate_report(report, ROOT)
    report["comparisons"][0]["contract_pass"] = False
    report["comparison_pass"] = False
    report["artifact_hash"] = base._artifact_hash(report)
    local.validate_report(report, ROOT)


def test_unreviewed_build_packet_rejects_before_creating_output(tmp_path):
    packet = tmp_path / "build"
    Path(str(packet) + ".inventory.json").write_text("{}")
    with pytest.raises(ValueError, match="source_build_inventory_not_reviewed"):
        local.run_comparison(
            repo=ROOT, build_packet=packet, debs=[], output=tmp_path / "out"
        )
    assert not (tmp_path / "out").exists()
