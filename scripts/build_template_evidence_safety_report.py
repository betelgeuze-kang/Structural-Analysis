#!/usr/bin/env python3
"""Audit release templates so handoff files cannot masquerade as evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


SCHEMA_VERSION = "template-evidence-safety-report.v1"
DEFAULT_TEMPLATE_DIR = Path("docs/templates")
DEFAULT_OUT = Path("implementation/phase1/release_evidence/productization/template_evidence_safety_report.json")
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
PLACEHOLDER_MARKERS = (
    "OWNER_INPUT_REQUIRED",
    "LICENSE-ID",
    "LEGAL-OR-PRODUCT-APPROVAL-ID",
    "PRODUCT-OR-LEGAL-OWNER",
    "TEMPLATE ONLY",
    "PLACEHOLDER",
    "REPLACE_ME",
    "TODO",
    "TBD",
)
KNOWN_TEMPLATE_PROBES = {
    "license_status.template.json",
    "ux_new_user_observation.template.json",
    "independent_vv_attestation.template.json",
    "family_validation_manual_signoff.template.json",
    "customer_audit_failure_bundle_sla.template.json",
}


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_script_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json_paths(value: Any, prefix: str = "$") -> list[tuple[str, Any]]:
    rows = [(prefix, value)]
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(_json_paths(item, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(_json_paths(item, f"{prefix}[{index}]"))
    return rows


def _affirmative_pass_signals(payload: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    for path, value in _json_paths(payload):
        key = path.rsplit(".", 1)[-1]
        if key == "contract_pass" and value is True:
            signals.append(path)
        elif key == "pass" and value is True:
            signals.append(path)
        elif key == "reason_code" and str(value).strip().upper() == "PASS":
            signals.append(path)
    return signals


def _placeholder_markers(payload: dict[str, Any]) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).upper()
    return [marker for marker in PLACEHOLDER_MARKERS if marker in serialized]


def _scan_template(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    pass_signals = _affirmative_pass_signals(payload)
    markers = _placeholder_markers(payload)
    blockers = [
        *(["template_json_object_missing"] if not payload else []),
        *(["template_only_missing"] if payload.get("template_only") is not True else []),
        *(f"template_affirmative_pass_signal:{signal}" for signal in pass_signals),
        *(["template_placeholder_marker_missing"] if not markers else []),
        *(["template_validator_probe_missing"] if path.name not in KNOWN_TEMPLATE_PROBES else []),
    ]
    return {
        "path": str(path),
        "name": path.name,
        "contract_pass": not blockers,
        "template_only": payload.get("template_only") is True,
        "pass_signal_paths": pass_signals,
        "placeholder_markers": markers,
        "validator_probe_mapped": path.name in KNOWN_TEMPLATE_PROBES,
        "blockers": blockers,
    }


def _reason_pass(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("contract_pass") is True
        or payload.get("pass") is True
        or str(payload.get("reason_code", "")).strip().upper() == "PASS"
    )


def _probe_license_template(template_dir: Path) -> dict[str, Any]:
    path = template_dir / "license_status.template.json"
    module = _load_script_module(
        "build_license_status_closure_report",
        Path("scripts/build_license_status_closure_report.py"),
    )
    report = module.build_report(license_status_path=path)
    blockers = [str(item) for item in report.get("blockers", [])]
    probe_pass = bool(not _reason_pass(report) and "license_status_template_only" in blockers)
    return {
        "label": "license_status_template_probe",
        "template_path": str(path),
        "contract_pass": probe_pass,
        "validator_contract_pass": _reason_pass(report),
        "expected_blockers_present": ["license_status_template_only"],
        "observed_blockers": blockers,
        "state": "template_rejected_as_license_evidence" if probe_pass else "template_probe_failed",
    }


def _probe_ux_template(template_dir: Path) -> dict[str, Any]:
    path = template_dir / "ux_new_user_observation.template.json"
    module = _load_script_module(
        "build_ux_new_user_observation_report",
        Path("scripts/build_ux_new_user_observation_report.py"),
    )
    report = module.build_report(observation_path=path)
    blockers = [str(item) for item in report.get("blockers", [])]
    expected = ["placeholder_values_present", "template_only_observation_source"]
    probe_pass = bool(not _reason_pass(report) and all(blocker in blockers for blocker in expected))
    return {
        "label": "ux_new_user_observation_template_probe",
        "template_path": str(path),
        "contract_pass": probe_pass,
        "validator_contract_pass": _reason_pass(report),
        "expected_blockers_present": expected,
        "observed_blockers": blockers,
        "state": "template_rejected_as_ux_evidence" if probe_pass else "template_probe_failed",
    }


def _probe_ga_signoff_templates(template_dir: Path) -> list[dict[str, Any]]:
    module = _load_script_module(
        "build_ga_enterprise_signoff_intake_packet",
        Path("scripts/build_ga_enterprise_signoff_intake_packet.py"),
    )
    rows: list[dict[str, Any]] = []
    for _blocker, spec in module.SIGNOFF_SPECS.items():
        template_path = template_dir / Path(str(spec["default_template_path"])).name
        template = _load_json(template_path)
        required_fields = [str(field) for field in spec.get("required_fields", [])]
        field_status = module._evidence_field_status(template, required_fields)
        validator_contract_pass = bool(
            template_path.exists()
            and module._reason_pass(template)
            and not field_status["missing_fields"]
            and not field_status["placeholder_fields"]
            and field_status["approval_decision_pass"]
            and not field_status["template_only"]
        )
        state = module._evidence_state(
            evidence_present=template_path.exists(),
            evidence_contract_pass=validator_contract_pass,
            field_status=field_status,
        )
        expected_state = "template_only_external_signoff_evidence"
        probe_pass = bool(
            not validator_contract_pass
            and state == expected_state
            and field_status["template_only"] is True
            and field_status["placeholder_fields"]
        )
        rows.append(
            {
                "label": f"{spec['signoff']}_template_probe",
                "template_path": str(template_path),
                "contract_pass": probe_pass,
                "validator_contract_pass": validator_contract_pass,
                "expected_state": expected_state,
                "observed_state": state,
                "template_only": field_status["template_only"],
                "placeholder_fields": field_status["placeholder_fields"],
                "missing_fields": field_status["missing_fields"],
                "approval_decision_pass": field_status["approval_decision_pass"],
            }
        )
    return rows


def _validator_probes(template_dir: Path) -> list[dict[str, Any]]:
    return [
        _probe_license_template(template_dir),
        _probe_ux_template(template_dir),
        *_probe_ga_signoff_templates(template_dir),
    ]


def build_report(*, template_dir: Path = DEFAULT_TEMPLATE_DIR) -> dict[str, Any]:
    template_paths = sorted(template_dir.glob("*.json")) if template_dir.exists() else []
    template_rows = [_scan_template(path) for path in template_paths]
    probe_rows = _validator_probes(template_dir)
    probe_paths = {Path(str(row.get("template_path", ""))).name for row in probe_rows}
    unscanned_probe_templates = sorted(KNOWN_TEMPLATE_PROBES - {path.name for path in template_paths})
    unprobed_templates = sorted(path.name for path in template_paths if path.name not in probe_paths)
    blockers = [
        *(["template_directory_missing"] if not template_dir.exists() else []),
        *(["template_directory_empty"] if template_dir.exists() and not template_paths else []),
        *(f"template_scan_failed:{row['name']}:{blocker}" for row in template_rows for blocker in row["blockers"]),
        *(f"validator_probe_failed:{row['label']}" for row in probe_rows if not row["contract_pass"]),
        *(f"known_template_missing:{name}" for name in unscanned_probe_templates),
        *(f"template_probe_missing:{name}" for name in unprobed_templates),
    ]
    contract_pass = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "template_safety_audit",
        "generated_at": _now_utc_iso(),
        "template_dir": str(template_dir),
        "contract_pass": contract_pass,
        "reason_code": "PASS" if contract_pass else "ERR_TEMPLATE_EVIDENCE_SAFETY_BLOCKED",
        "summary_line": (
            f"Template evidence safety: {'PASS' if contract_pass else 'BLOCKED'} | "
            f"templates={len(template_rows)} | validator_probes={len(probe_rows)} | blockers={len(blockers)}"
        ),
        "summary": {
            "template_count": len(template_rows),
            "template_pass_count": sum(1 for row in template_rows if row["contract_pass"]),
            "validator_probe_count": len(probe_rows),
            "validator_probe_pass_count": sum(1 for row in probe_rows if row["contract_pass"]),
            "unprobed_templates": unprobed_templates,
            "missing_known_templates": unscanned_probe_templates,
        },
        "template_rows": template_rows,
        "validator_probes": probe_rows,
        "blockers": blockers,
        "claim_boundary": (
            "This audit proves docs/templates JSON files are handoff-only templates and are rejected by "
            "release-evidence validators. It does not create owner evidence or replace external signoff."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Template Evidence Safety Report",
        "",
        f"- `summary_line`: `{payload['summary_line']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `template_dir`: `{payload['template_dir']}`",
        "",
        "## Templates",
        "",
        "| Template | Template Only | Pass Signals | Placeholders | Probe | Blockers |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in payload["template_rows"]:
        lines.append(
            f"| `{row['name']}` | `{row['template_only']}` | `{len(row['pass_signal_paths'])}` | "
            f"`{len(row['placeholder_markers'])}` | `{row['validator_probe_mapped']}` | "
            f"{', '.join(f'`{item}`' for item in row['blockers']) or '`none`'} |"
        )
    lines.extend(
        [
            "",
            "## Validator Probes",
            "",
            "| Probe | Pass | Validator Pass | State | Template |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in payload["validator_probes"]:
        state = row.get("state", row.get("observed_state", ""))
        lines.append(
            f"| `{row['label']}` | `{row['contract_pass']}` | `{row['validator_contract_pass']}` | "
            f"`{state}` | `{row['template_path']}` |"
        )
    if payload["blockers"]:
        lines.extend(["", "## Blockers", ""])
        for blocker in payload["blockers"]:
            lines.append(f"- `{blocker}`")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-dir", type=Path, default=DEFAULT_TEMPLATE_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(template_dir=args.template_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) if args.json else _markdown(payload))
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
