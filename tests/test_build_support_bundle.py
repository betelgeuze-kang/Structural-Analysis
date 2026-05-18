from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_support_bundle.py"
SPEC = importlib.util.spec_from_file_location("build_support_bundle", SCRIPT_PATH)
assert SPEC is not None
build_support_bundle = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_support_bundle)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _support_inputs(tmp_path: Path) -> dict[str, Path]:
    return {
        "p0_status": _write_json(tmp_path / "p0.json", {"contract_pass": True}),
        "p1_status": _write_json(tmp_path / "p1.json", {"p1_inputs_ready": True}),
        "p1_strict_evidence_preflight": _write_json(
            tmp_path / "preflight.json",
            {
                "contract_pass": False,
                "blockers": ["external_receipt_or_closure_pending:hardest_external_10case"],
                "Authorization": "Bearer should-be-redacted",
            },
        ),
        "project_ops_snapshot": _write_json(tmp_path / "project-ops.json", {"summary": {"project_count": 1}}),
        "runtime_probe": _write_json(tmp_path / "runtime-probe.json", {"strict_rust_hip_pass": True}),
        "runtime_packaging_manifest": _write_json(tmp_path / "runtime-manifest.json", {"contract_pass": False}),
        "external_benchmark_updates": _write_json(tmp_path / "eb.json", {"receipt_status": "pending"}),
        "residual_holdout_updates": _write_json(tmp_path / "rh.json", {"status": "open"}),
        "package_json": _write_json(tmp_path / "package.json", {"name": "support-bundle-test"}),
        "pyproject": _write_text(tmp_path / "pyproject.toml", "[project]\nname='support-bundle-test'\n"),
    }


def test_support_bundle_builds_redacted_digest_and_roundtrip(tmp_path: Path) -> None:
    inputs = _support_inputs(tmp_path)
    audit_log = _write_text(
        tmp_path / "audit.jsonl",
        '{"tenant_id":"tenant-a","Authorization":"Bearer audit-token","status":200}\n',
    )

    payload = build_support_bundle.build_support_bundle(
        bundle_dir=tmp_path / "bundle",
        audit_log_path=audit_log,
        **inputs,
    )

    assert payload["contract_pass"] is True
    assert payload["checks"]["redaction_self_test_pass"] is True
    assert payload["checks"]["audit_event_digest_pass"] is True
    assert payload["checks"]["bundle_roundtrip_test_pass"] is True
    assert payload["audit_digest"]["event_count"] == 1
    assert payload["blockers"] == []

    index_path = Path(payload["bundle_index"]["path"])
    assert index_path.exists()
    redacted_preflight = Path(payload["required_sections"]["p1_strict_evidence_preflight"]).read_text(
        encoding="utf-8"
    )
    assert "should-be-redacted" not in redacted_preflight
    assert build_support_bundle.REDACTED in redacted_preflight


def test_support_bundle_blocks_when_required_artifact_missing(tmp_path: Path) -> None:
    inputs = _support_inputs(tmp_path)
    inputs["runtime_probe"] = tmp_path / "missing-runtime-probe.json"

    payload = build_support_bundle.build_support_bundle(
        bundle_dir=tmp_path / "bundle",
        **inputs,
    )

    assert payload["contract_pass"] is False
    assert "required_artifact_missing:runtime_probe" in payload["blockers"]
