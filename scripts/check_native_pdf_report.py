#!/usr/bin/env python3
"""Verify the bounded deterministic native PDF report evidence contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_TOKENS = {
    "native/crates/structural-report/src/pdf.rs": (
        "render_nonlinear_ndtha_pdf_v1",
        "validate_deterministic_pdf_v1",
        "pdf_document_source_projection_mismatch",
        "pdf_report_ir_projection_mismatch",
        "pdf_object_offset_invalid",
        "%PDF-1.7",
        "startxref",
        "not_pdf_a_accessibility",
    ),
    "native/crates/structural-report/tests/pdf_render.rs": (
        "deterministic_pdf_is_hash_bound_to_exact_report_projection",
        "forged_document_and_self_consistent_alternate_report_are_rejected",
        "xref_tamper_is_detected_without_a_pdf_parser_dependency",
    ),
    "native/crates/structural-cli/src/report.rs": (
        "execute_pdf_report",
        "publish_pdf_report",
        "report.pdf",
        "pdf-receipt.json",
        "receipt_hash",
    ),
    "native/crates/structural-cli/tests/pdf_report_cli.rs": (
        "python_node_and_external_renderer_free_pdf_is_bitwise_deterministic",
        "command.env_clear()",
        "forged_markdown_and_existing_destination_fail_without_overwrite",
        "sha256:35f2bebb41411b31cba9e0c395ba74f914097498e8da63e4b14d72704f06c197",
        "sha256:b807334630bb3c98398efcec4451e44ba23e3e538a1938b1c284bc781a677877",
    ),
    "docs/native/pdf-report-v1.md": (
        "closes C5 only",
        "Poppler is verification tooling, not a product dependency",
        "PDF/A",
        "tagged accessibility",
        "HIP C2",
        "C6",
    ),
}


def check_pdf_report_contract(repo_root: Path = ROOT) -> dict[str, object]:
    root = repo_root.resolve()
    blockers: list[str] = []
    try:
        payload = json.loads(
            (root / "native/capabilities.json").read_text(encoding="utf-8")
        )
        row = payload["capabilities"]["pdf_report"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"pdf_report_capability_manifest_invalid:{exc}")
        row = {}
    if row.get("status") != "implemented":
        blockers.append("pdf_report_capability_not_implemented")
    if row.get("cutover_gate") != "C5":
        blockers.append("pdf_report_capability_gate_not_c5")
    if row.get("owner") != "structural-report":
        blockers.append("pdf_report_capability_owner_invalid")
    claim = str(row.get("claim", ""))
    for token in (
        "deterministic A4 PDF 1.7",
        "validates its own xref/object/trailer",
        "no Python, Node or external renderer lookup",
        "PDF/A",
        "tagged accessibility",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"pdf_report_scope_token_missing:{token}")

    for relative, tokens in REQUIRED_TOKENS.items():
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            blockers.append(f"pdf_report_evidence_missing:{relative}")
            continue
        for token in tokens:
            if token not in text:
                blockers.append(f"pdf_report_evidence_token_missing:{relative}:{token}")

    blockers = sorted(set(blockers))
    return {
        "schema_version": "native-bounded-pdf-report-contract.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cutover_gate": row.get("cutover_gate"),
        "blockers": blockers,
        "claim_boundary": (
            "This validates one bounded deterministic PDF implementation; it is not PDF/A, "
            "accessibility, broader report, HIP or C6 evidence."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = check_pdf_report_contract(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native PDF report contract: {report['status']}")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
