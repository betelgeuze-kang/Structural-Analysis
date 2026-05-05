from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("scripts/generate_p1_evidence_intake_template.py")
SCRIPT_PATH = Path(__file__).resolve().parent.parent / SCRIPT
SPEC = importlib.util.spec_from_file_location("generate_p1_evidence_intake_template", SCRIPT_PATH)
assert SPEC is not None
generator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(generator)

BUILDER_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_p1_evidence_sidecar_updates.py"
BUILDER_SPEC = importlib.util.spec_from_file_location("build_p1_evidence_sidecar_updates", BUILDER_PATH)
assert BUILDER_SPEC is not None
builder = importlib.util.module_from_spec(BUILDER_SPEC)
assert BUILDER_SPEC.loader is not None
BUILDER_SPEC.loader.exec_module(builder)

PREFLIGHT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "preflight_p1_evidence_sidecar_intake.py"
PREFLIGHT_SPEC = importlib.util.spec_from_file_location("preflight_p1_evidence_sidecar_intake", PREFLIGHT_PATH)
assert PREFLIGHT_SPEC is not None
preflight = importlib.util.module_from_spec(PREFLIGHT_SPEC)
assert PREFLIGHT_SPEC.loader is not None
PREFLIGHT_SPEC.loader.exec_module(preflight)


QUEUE_IDS = ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"]
RH_IDS = ["RH-001", "RH-002", "RH-003"]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _operational_queues(path: Path) -> Path:
    external = []
    residual = []
    for index, queue_id in enumerate(QUEUE_IDS, start=1):
        external.append(
            {
                "work_item_id": f"EB-{index:03d}",
                "queue_id": queue_id,
                "submission_id": f"p1-{queue_id}",
                "owner": f"{queue_id}_owner",
                "status": "ready_for_full_submission",
                "receipt_status": "pending_external_submission_receipt",
                "closure_evidence_required": f"{queue_id}_submission_receipt",
                "receipt_template_path": f"queues/EB-{index:03d}.receipt_template.json",
                "owner_action": "submit_external_benchmark_package_and_attach_receipt",
            }
        )
    for index, work_item_id in enumerate(RH_IDS, start=1):
        residual.append(
            {
                "work_item_id": work_item_id,
                "category_id": [
                    "licensed_engineer_review_required",
                    "legacy_tool_cross_validation_required",
                    "legal_authority_signoff_required",
                ][index - 1],
                "owner": f"owner-{work_item_id}",
                "status": "open",
                "queue_status": "pending_review",
                "closure_evidence_required": f"{work_item_id}.required_packet",
                "closure_packet_template_path": f"queues/{work_item_id}.closure_packet_template.json",
                "owner_action": "attach_closure_evidence",
                "sla_label": "72h",
                "due_date": "assignment_plus_3_business_days",
            }
        )
    return _write_json(
        path,
        {
            "schema_version": "p1-operational-queues.v1",
            "contract_pass": True,
            "queues": {
                "external_benchmark_submission_work_items": external,
                "residual_holdout_work_items": residual,
            },
        },
    )


def test_generate_template_from_operational_queues(tmp_path: Path) -> None:
    payload = generator.build_template(p1_operational_queues=_operational_queues(tmp_path / "ops.json"))

    assert payload["schema_version"] == "p1-evidence-sidecar-intake.v1"
    assert payload["summary"]["external_expected_queue_count"] == 4
    assert payload["summary"]["residual_expected_work_item_count"] == 3
    assert set(payload["external_benchmark_receipts"]) == set(QUEUE_IDS)
    assert set(payload["residual_holdout_closures"]) == set(RH_IDS)
    first = payload["external_benchmark_receipts"]["hardest_external_10case"]
    assert first["work_item_id"] == "EB-001"
    assert first["receipt_url"] == ""
    assert first["source_receipt_template_path"].endswith("EB-001.receipt_template.json")
    assert payload["residual_holdout_closures"]["RH-001"]["closure_evidence_path"] == ""


def test_generate_template_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    out = tmp_path / "p1-evidence-intake.template.json"
    out_md = tmp_path / "p1-evidence-intake.template.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--p1-operational-queues",
            str(_operational_queues(tmp_path / "ops.json")),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["template_kind"] == "p1_evidence_intake_fill_in"
    assert "P1 Evidence Intake Template" in markdown
    assert "hardest_external_10case" in markdown
    assert "RH-003" in markdown


def test_generated_template_can_be_filled_and_promoted_to_sidecars(tmp_path: Path) -> None:
    template = generator.build_template(p1_operational_queues=_operational_queues(tmp_path / "ops.json"))
    for queue_id, row in template["external_benchmark_receipts"].items():
        row["receipt_url"] = f"https://bench.example/receipts/{queue_id}"
        row["submitted_at_utc"] = "2026-05-05T01:02:03Z"
        row["last_checked_at_utc"] = "2026-05-05T02:03:04Z"
    for work_item_id, row in template["residual_holdout_closures"].items():
        evidence = tmp_path / "evidence" / f"{work_item_id}.closure.json"
        _write_json(evidence, {"work_item_id": work_item_id, "contract_pass": True})
        row["closure_evidence_path"] = str(evidence.relative_to(tmp_path))
        row["last_checked_at_utc"] = "2026-05-05T04:05:06Z"
        row["closed_at_utc"] = "2026-05-05T04:06:07Z"
    intake = _write_json(tmp_path / "p1-evidence-intake.json", template)

    external_payload, residual_payload = builder.build_sidecars(
        intake_manifest=intake,
        base_external_updates=tmp_path / "missing-eb.json",
        base_residual_updates=tmp_path / "missing-rh.json",
        repo_root=tmp_path,
        require_complete=True,
    )
    external_out = _write_json(tmp_path / "external_benchmark_submission_updates.json", external_payload)
    residual_out = _write_json(tmp_path / "residual_holdout_closure_updates.json", residual_payload)
    result = preflight.build_preflight(
        external_benchmark_submission_updates=external_out,
        residual_holdout_closure_updates=residual_out,
        repo_root=tmp_path,
    )

    assert result["contract_pass"] is True
    assert result["summary"]["external_receipt_attached_count"] == 4
    assert result["summary"]["residual_closed_count"] == 3
