from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_medium_benchmark_corpus_plan.py"
spec = importlib.util.spec_from_file_location(
    "build_medium_benchmark_corpus_plan", SCRIPT
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_current_medium_corpus_plan_excludes_large_substitute_from_credit() -> None:
    payload = module.build_medium_benchmark_corpus_plan(repo_root=ROOT)

    assert payload["schema_version"] == "medium-benchmark-corpus-readiness.v1"
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["attached_case_count"] == 3
    assert payload["medium_benchmark_credit_count"] == 0
    cases = {row["case_id"]: row for row in payload["case_rows"]}
    assert set(cases) == {
        "SCBF16B",
        "SCBF16B_shell_beam_mix",
        "luxinzheng_megatall_model1",
    }
    assert "medium_case_license_not_approved" in cases["SCBF16B"]["blockers"]
    assert (
        "medium_case_capability_missing:diaphragm_load_path"
        in (cases["SCBF16B_shell_beam_mix"]["blockers"])
    )
    assert (
        "large_model_substitute_not_medium"
        in (cases["luxinzheng_megatall_model1"]["blockers"])
    )
    assert (
        "medium_case_size_class_not_medium"
        in (cases["luxinzheng_megatall_model1"]["blockers"])
    )
    slots = {row["archetype_id"]: row for row in payload["slot_rows"]}
    assert slots["steel_moment_frame_3d"]["slot_status"] == (
        "operator_selection_required"
    )
    assert slots["foundation_link_or_mixed_element"]["slot_status"] == (
        "operator_selection_required"
    )
    assert payload["reference_solver_diversity"]["contract_pass"] is False
    assert "large-model substitutes receive zero credit" in payload["claim_boundary"]


def test_medium_corpus_plan_cli_write_and_check(tmp_path: Path) -> None:
    out = tmp_path / "medium-corpus-plan.json"
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
    assert "Medium benchmark corpus: BLOCKED" in write.stdout
    assert check.returncode == 0, check.stderr
    assert "medium_benchmark_corpus_plan_consistent" in check.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["contract_pass"] is False


def test_operator_case_evidence_replaces_parser_candidate_fallback(
    tmp_path: Path,
) -> None:
    operator_path = tmp_path / module.DEFAULT_OPERATOR_CASE_EVIDENCE
    operator_path.parent.mkdir(parents=True, exist_ok=True)
    operator_path.write_text(
        json.dumps(
            {
                "schema_version": module.OPERATOR_CASE_EVIDENCE_SCHEMA_VERSION,
                "binding_profile": module.MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE,
                "cases": [],
                "claim_boundary": "Operator evidence only; no automatic promotion.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_medium_benchmark_corpus_plan(repo_root=tmp_path)

    assert payload["attached_case_count"] == 0
    assert payload["medium_benchmark_credit_count"] == 0
    assert all(
        row["slot_status"] == "operator_selection_required"
        for row in payload["slot_rows"]
    )
    assert payload["input_blockers"] == []


def test_invalid_operator_manifest_is_explicitly_blocked(tmp_path: Path) -> None:
    operator_path = tmp_path / module.DEFAULT_OPERATOR_CASE_EVIDENCE
    operator_path.parent.mkdir(parents=True, exist_ok=True)
    operator_path.write_text('{"cases": []}\n', encoding="utf-8")

    payload = module.build_medium_benchmark_corpus_plan(repo_root=tmp_path)

    assert payload["contract_pass"] is False
    assert payload["input_blockers"] == [
        "medium_corpus_operator_manifest_binding_profile_invalid",
        "medium_corpus_operator_manifest_claim_boundary_missing",
        "medium_corpus_operator_manifest_schema_invalid",
    ]


def test_operator_manifest_declarations_without_bound_files_receive_zero_credit(
    tmp_path: Path,
) -> None:
    candidate = module._candidate_case(
        {
            "case_id": "SCBF16B",
            "parser_contract_ready": True,
            "path": "missing/SCBF16B.tcl",
            "sha256": "a" * 64,
            "family_id": "test-family",
            "source_url": "https://example.org/SCBF16B.tcl",
        },
        license_receipt={
            "license_evidence": {"spdx": "GPL-3.0"},
            "commercial_use_allowed": False,
        },
    )
    assert candidate is not None
    operator_path = tmp_path / module.DEFAULT_OPERATOR_CASE_EVIDENCE
    operator_path.parent.mkdir(parents=True, exist_ok=True)
    operator_path.write_text(
        json.dumps(
            {
                "schema_version": module.OPERATOR_CASE_EVIDENCE_SCHEMA_VERSION,
                "binding_profile": module.MEDIUM_BENCHMARK_EVIDENCE_BINDING_PROFILE,
                "cases": [candidate],
                "claim_boundary": "Declarations only; no bound bytes.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_medium_benchmark_corpus_plan(repo_root=tmp_path)
    row = payload["case_rows"][0]

    assert payload["input_blockers"] == []
    assert payload["medium_benchmark_credit_count"] == 0
    assert payload["byte_bound_case_count"] == 0
    assert row["evidence_binding_contract_pass"] is False
    assert "medium_case_source_file_missing" in row["blockers"]
    assert "medium_case_source_commit_sha_invalid" in row["blockers"]
