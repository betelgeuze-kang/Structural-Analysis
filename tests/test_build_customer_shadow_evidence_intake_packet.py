from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "build_customer_shadow_evidence_intake_packet.py"
)
SPEC = importlib.util.spec_from_file_location("build_customer_shadow_evidence_intake_packet", SCRIPT_PATH)
assert SPEC is not None
intake_packet = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(intake_packet)


REQUIRED_METADATA_FIELDS = (
    "generated_at",
    "source_commit_sha",
    "engine_version",
    "input_checksums",
    "reused_evidence",
    "reuse_policy",
)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _schema_payload() -> dict[str, object]:
    return {
        "schema_version": "customer-shadow-evidence.schema.v1",
        "required_fields": [
            "case_id",
            "project_status",
            "structure_family",
            "reference_solver",
            "reference_solver_version",
            "reference_output_checksum",
            "our_engine_commit",
            "delta_metrics",
            "residual_metrics",
            "reviewer_decision",
            "known_limitations",
            "reproduce_bundle_id",
            "raw_data_retained_by_customer",
            "redistribution_allowed",
        ],
        "fixed_values": {
            "project_status": "completed",
            "raw_data_retained_by_customer": True,
            "redistribution_allowed": False,
        },
        "allowed_reviewer_decisions": ["PASS", "REVIEW", "FAIL"],
        "claim_boundary": (
            "Customer shadow evidence records derived checksums, metrics, reviewer decision, "
            "and reproduce bundle identity only."
        ),
    }


def _template_payload() -> dict[str, object]:
    return {
        "case_id": "OWNER_INPUT_REQUIRED_CASE_ID",
        "project_status": "completed",
        "structure_family": "OWNER_INPUT_REQUIRED_STRUCTURE_FAMILY",
        "reference_solver": "OWNER_INPUT_REQUIRED_REFERENCE_SOLVER",
        "reference_solver_version": "OWNER_INPUT_REQUIRED_REFERENCE_SOLVER_VERSION",
        "reference_output_checksum": "sha256:OWNER_INPUT_REQUIRED_REFERENCE_OUTPUT_DIGEST",
        "our_engine_commit": "OWNER_INPUT_REQUIRED_ENGINE_COMMIT",
        "delta_metrics": {"max_relative_error_pct": "OWNER_INPUT_REQUIRED"},
        "residual_metrics": {"normalized_equilibrium_residual": "OWNER_INPUT_REQUIRED"},
        "reviewer_decision": "REVIEW",
        "known_limitations": ["OWNER_INPUT_REQUIRED_LIMITATION"],
        "reproduce_bundle_id": "OWNER_INPUT_REQUIRED_REPRODUCE_BUNDLE_ID",
        "raw_data_retained_by_customer": True,
        "redistribution_allowed": False,
    }


def _status_payload(*, contract_pass: bool, completed: int = 0) -> dict[str, object]:
    return {
        "schema_version": "customer-shadow-evidence-status.v1",
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_CUSTOMER_SHADOW_EVIDENCE_INCOMPLETE",
        "evidence_dir": "implementation/phase1/customer_shadow_evidence",
        "summary": {
            "completed_shadow_case_count": completed,
            "min_completed_shadow_cases": 3,
            "target_completed_shadow_cases": 5,
        },
        "blockers": [] if contract_pass else ["completed_shadow_case_count_below_minimum"],
    }


def _inputs(
    tmp_path: Path,
    *,
    schema: dict[str, object] | None = None,
    template: dict[str, object] | None = None,
    status: dict[str, object] | None = None,
    status_contract_pass: bool = False,
    completed: int = 0,
) -> dict[str, Path]:
    return {
        "schema": _write_json(
            tmp_path / "customer_shadow_evidence.schema.json",
            schema if schema is not None else _schema_payload(),
        ),
        "template": _write_json(
            tmp_path / "customer_shadow_evidence.template.json",
            template if template is not None else _template_payload(),
        ),
        "status": _write_json(
            tmp_path / "customer_shadow_evidence_status.json",
            status
            if status is not None
            else _status_payload(contract_pass=status_contract_pass, completed=completed),
        ),
    }


def test_intake_packet_passes_as_structure_artifact_while_status_is_blocked(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, status_contract_pass=False, completed=0)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["current_completed_shadow_case_count"] == 0
    assert payload["summary"]["min_completed_shadow_cases"] == 3
    assert payload["summary"]["target_completed_shadow_cases"] == 5
    assert payload["summary"]["intake_slot_count"] == 5
    assert payload["summary"]["fixed_values"] == {
        "project_status": "completed",
        "raw_data_retained_by_customer": True,
        "redistribution_allowed": False,
    }
    assert payload["required_schema_fields"] == _schema_payload()["required_fields"]
    assert payload["fixed_values"] == payload["summary"]["fixed_values"]
    assert payload["allowed_reviewer_decisions"] == ["PASS", "REVIEW", "FAIL"]
    assert payload["blockers"] == []
    assert payload["checks"]["raw_data_policy_fixed"] is True
    assert payload["checks"]["reviewer_decisions_present"] is True
    assert payload["checks"]["template_has_required_fields"] is True
    assert payload["checks"]["current_status_blocked_until_evidence_attached"] is True
    slots = {slot["slot_id"] for slot in payload["intake_slots"]}
    assert slots == {
        "customer-shadow-case-001",
        "customer-shadow-case-002",
        "customer-shadow-case-003",
        "customer-shadow-case-004",
        "customer-shadow-case-005",
    }
    for slot in payload["intake_slots"]:
        assert slot["status"] == "owner_input_required"
        assert slot["required"] is True
        assert "OWNER_INPUT_REQUIRED" not in slot["evidence_path"]
        assert any("raw_data_retained_by_customer=true" in action for action in slot["owner_actions"])
        assert any("redistribution_allowed=false" in action for action in slot["owner_actions"])


def test_intake_packet_claim_boundary_does_not_create_or_close_customer_evidence(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    boundary = payload["claim_boundary"]
    assert "does not create customer shadow evidence" in boundary
    assert "close the 3/5 completed-project target" in boundary
    assert "ingest customer raw data" in boundary
    assert "customer-retained" in boundary


def test_intake_packet_blocks_when_customer_target_already_closed(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path, status_contract_pass=True, completed=5)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_CUSTOMER_SHADOW_INTAKE_PACKET_INCOMPLETE"
    assert payload["summary"]["current_status_contract_pass"] is True
    assert payload["checks"]["current_status_blocked_until_evidence_attached"] is False
    assert "current_status_blocked_until_evidence_attached" in payload["blockers"]


def test_intake_packet_blocks_missing_required_fields_in_template(tmp_path: Path) -> None:
    template = _template_payload()
    template.pop("raw_data_retained_by_customer")
    template.pop("redistribution_allowed")
    inputs = _inputs(tmp_path, template=template)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["template_has_required_fields"] is False
    assert "template_has_required_fields" in payload["blockers"]


def test_intake_packet_blocks_when_raw_data_policy_is_relaxed(tmp_path: Path) -> None:
    schema = _schema_payload()
    schema["fixed_values"] = {
        "project_status": "completed",
        "raw_data_retained_by_customer": True,
        "redistribution_allowed": True,
    }
    inputs = _inputs(tmp_path, schema=schema)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["raw_data_policy_fixed"] is False
    assert "raw_data_policy_fixed" in payload["blockers"]


def test_intake_packet_blocks_when_reviewer_decisions_missing(tmp_path: Path) -> None:
    schema = _schema_payload()
    schema["allowed_reviewer_decisions"] = ["PASS"]
    inputs = _inputs(tmp_path, schema=schema)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    assert payload["contract_pass"] is False
    assert payload["checks"]["reviewer_decisions_present"] is False
    assert "reviewer_decisions_present" in payload["blockers"]


def test_intake_packet_blocks_when_min_greater_than_target(tmp_path: Path) -> None:
    status = _status_payload(contract_pass=False)
    status["summary"] = {
        "completed_shadow_case_count": 0,
        "min_completed_shadow_cases": 6,
        "target_completed_shadow_cases": 5,
    }
    inputs = _inputs(tmp_path, status=status)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    assert payload["checks"]["intake_slot_count_covers_target"] is False
    assert "intake_slot_count_covers_target" in payload["blockers"]


def test_intake_packet_exposes_release_evidence_metadata(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
    )

    for field in REQUIRED_METADATA_FIELDS:
        assert field in payload, f"missing release evidence metadata field: {field}"
    assert payload["reused_evidence"] is True
    assert "intake_packet_rebuilt_from_schema_template_and_current_shadow_status" in payload["reuse_policy"]
    assert str(inputs["schema"]) in payload["input_checksums"]
    assert str(inputs["template"]) in payload["input_checksums"]
    assert str(inputs["status"]) in payload["input_checksums"]


def test_intake_packet_slot_count_overrides_via_kwargs(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)

    payload = intake_packet.build_packet(
        schema_path=inputs["schema"],
        template_path=inputs["template"],
        status_path=inputs["status"],
        min_completed_cases=2,
        target_completed_cases=4,
    )

    assert payload["summary"]["min_completed_shadow_cases"] == 2
    assert payload["summary"]["target_completed_shadow_cases"] == 4
    assert payload["summary"]["intake_slot_count"] == 4
    assert len(payload["intake_slots"]) == 4


def test_intake_packet_cli_writes_json_and_markdown(tmp_path: Path, capsys) -> None:
    inputs = _inputs(tmp_path)
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = intake_packet.main(
        [
            "--schema",
            str(inputs["schema"]),
            "--template",
            str(inputs["template"]),
            "--status",
            str(inputs["status"]),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "customer-shadow-evidence-intake-packet: PASS" in captured.out
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["intake_slot_count"] == 5
    md = out_md.read_text(encoding="utf-8")
    assert "Customer Shadow Evidence Intake Packet" in md
    assert "customer-shadow-case-001" in md
    assert "validate_one_evidence_file" in md
    assert "refresh_status" in md


def test_intake_packet_cli_fail_blocked_exits_nonzero_on_incomplete_inputs(tmp_path: Path, capsys) -> None:
    schema = _schema_payload()
    schema["fixed_values"]["redistribution_allowed"] = True
    inputs = _inputs(tmp_path, schema=schema)
    out = tmp_path / "packet.json"
    out_md = tmp_path / "packet.md"

    exit_code = intake_packet.main(
        [
            "--schema",
            str(inputs["schema"]),
            "--template",
            str(inputs["template"]),
            "--status",
            str(inputs["status"]),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
            "--fail-blocked",
        ]
    )

    capsys.readouterr()
    assert exit_code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert "raw_data_policy_fixed" in payload["blockers"]
