from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ga_enterprise_readiness_report.py"
SPEC = importlib.util.spec_from_file_location("build_ga_enterprise_readiness_report", SCRIPT_PATH)
assert SPEC is not None
build_ga_enterprise_readiness_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ga_enterprise_readiness_report)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_text(path: Path, text: str = "manual\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _base_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "measured_benchmark_breadth": _write_json(
            tmp_path / "measured_breadth.json",
            {"contract_pass": True, "summary": {"measured_case_count": 304}},
        ),
        "release_registry": _write_json(
            tmp_path / "release_registry.json",
            {"contract_pass": True, "summary": {"signing_algorithm": "ed25519"}},
        ),
        "support_bundle": _write_json(
            tmp_path / "support_bundle.json",
            {
                "contract_pass": True,
                "checks": {
                    "redaction_self_test_pass": True,
                    "bundle_roundtrip_test_pass": True,
                    "missing_required_count": 0,
                },
            },
        ),
        "validation_manual": _write_text(tmp_path / "validation_manual.md"),
    }


def test_ga_readiness_blocks_external_enterprise_signoffs(tmp_path: Path) -> None:
    payload = build_ga_enterprise_readiness_report.build_report(
        **_base_inputs(tmp_path),
        independent_vv_attestation=tmp_path / "missing-independent-vv.json",
        family_validation_manual_signoff=tmp_path / "missing-family-signoff.json",
        customer_audit_failure_bundle_sla=tmp_path / "missing-customer-sla.json",
    )

    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_GA_ENTERPRISE_EVIDENCE_PENDING"
    assert payload["checks"]["ga_validation_case_threshold_pass"] is True
    assert payload["checks"]["signed_release_registry_pass"] is True
    assert payload["checks"]["support_failure_bundle_export_pass"] is True
    assert payload["blockers"] == [
        "independent_vv_missing",
        "family_validation_manual_signoff_missing",
        "customer_audit_failure_bundle_sla_missing",
    ]
    assert "does not create independent V&V" in payload["claim_boundary"]


def test_ga_readiness_passes_when_enterprise_signoffs_are_attached(tmp_path: Path) -> None:
    payload = build_ga_enterprise_readiness_report.build_report(
        **_base_inputs(tmp_path),
        independent_vv_attestation=_write_json(tmp_path / "independent-vv.json", {"contract_pass": True}),
        family_validation_manual_signoff=_write_json(tmp_path / "family-signoff.json", {"reason_code": "PASS"}),
        customer_audit_failure_bundle_sla=_write_json(tmp_path / "customer-sla.json", {"pass": True}),
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["blockers"] == []
    assert payload["summary_line"].startswith("GA enterprise readiness: PASS")


def test_ga_readiness_cli_writes_markdown(tmp_path: Path, capsys) -> None:
    inputs = _base_inputs(tmp_path)
    out = tmp_path / "ga.json"
    out_md = tmp_path / "ga.md"

    exit_code = build_ga_enterprise_readiness_report.main(
        [
            "--measured-benchmark-breadth",
            str(inputs["measured_benchmark_breadth"]),
            "--release-registry",
            str(inputs["release_registry"]),
            "--support-bundle",
            str(inputs["support_bundle"]),
            "--validation-manual",
            str(inputs["validation_manual"]),
            "--independent-vv-attestation",
            str(tmp_path / "missing-independent-vv.json"),
            "--family-validation-manual-signoff",
            str(tmp_path / "missing-family-signoff.json"),
            "--customer-audit-failure-bundle-sla",
            str(tmp_path / "missing-customer-sla.json"),
            "--out",
            str(out),
            "--out-md",
            str(out_md),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "GA Enterprise Readiness Report" in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["summary"]["measured_case_count"] == 304
    assert "Validation Commands" in out_md.read_text(encoding="utf-8")
