#!/usr/bin/env python3
"""Verify the bounded deterministic native PDF report evidence contract."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_FONT_ASSET = (
    "native/crates/structural-report/assets/StructuralReportKoreanSubset.ttf"
)

REQUIRED_TOKENS = {
    "native/crates/structural-report/src/pdf.rs": (
        "render_nonlinear_ndtha_pdf_v1",
        "render_sparse_linear_pdf_v1",
        "build_sparse_linear_pdf_bytes",
        "validate_deterministic_pdf_v1",
        "pdf_document_source_projection_mismatch",
        "pdf_report_ir_projection_mismatch",
        "pdf_object_offset_invalid",
        "%PDF-1.7",
        "startxref",
        "not_pdf_a_accessibility",
    ),
    "native/crates/structural-report/src/localized_pdf.rs": (
        "render_nonlinear_ndtha_localized_pdf_v2",
        "render_sparse_linear_localized_pdf_v2",
        "verify_exact_sparse_projection",
        "validate_deterministic_localized_pdf_v2",
        "/Subtype /Type0",
        "/CIDToGIDMap /Identity",
        "/ToUnicode 9 0 R",
        "pdf_embedded_font_identity_mismatch",
        "not_arbitrary_unicode_pdf_ua_accessibility",
    ),
    "native/crates/structural-report/src/localized_font.rs": (
        "include_bytes!",
        "LOCALIZED_FONT_GLYPHS",
        "sha256:bdcc6ac7747f102ba1dc64a0d034d9695bab41b1f82b098ffb836334c9329a68",
    ),
    "native/crates/structural-report/assets/StructuralReportKoreanSubset.provenance.json": (
        "OFL-1.1",
        "reserved_primary_names_removed",
        "not a production, build, test, packaging, or runtime dependency",
        "not a general Korean or arbitrary-Unicode font",
    ),
    "native/crates/structural-report/assets/OFL-1.1.txt": (
        "SIL OPEN FONT LICENSE",
        "Reserved Font Names",
        "Structural Report Korean Subset",
    ),
    "native/crates/structural-report/tests/pdf_render.rs": (
        "deterministic_pdf_is_hash_bound_to_exact_report_projection",
        "forged_document_and_self_consistent_alternate_report_are_rejected",
        "xref_tamper_is_detected_without_a_pdf_parser_dependency",
        "embedded_font_localized_pdfs_are_deterministic_distinct_and_extractable",
        "localized_pdf_rejects_projection_and_embedded_font_tampering",
        "sparse_linear_pdf_is_deterministic_and_exactly_projection_bound",
        "localized_sparse_linear_pdfs_are_deterministic_distinct_and_projection_bound",
    ),
    "native/crates/structural-cli/src/report.rs": (
        "execute_pdf_report",
        "publish_pdf_report",
        "execute_localized_pdf_report",
        "execute_sparse_linear_pdf_report",
        "execute_sparse_linear_localized_pdf_report",
        "publish_localized_pdf_report",
        "structural-native-localized-pdf-report-receipt.v2",
        "structural-native-sparse-linear-pdf-report-receipt.v1",
        "structural-native-sparse-linear-localized-pdf-report-receipt.v2",
        "report.pdf",
        "pdf-receipt.json",
        "receipt_hash",
    ),
    "native/crates/structural-cli/tests/pdf_report_cli.rs": (
        "python_node_and_external_renderer_free_pdf_is_bitwise_deterministic",
        "command.env_clear()",
        "forged_markdown_and_existing_destination_fail_without_overwrite",
        "localized_embedded_font_pdf_is_clean_environment_deterministic_and_closed",
        "sparse_linear_pdf_cli_is_clean_environment_deterministic_and_profile_typed",
        "localized_sparse_linear_pdf_cli_is_deterministic_and_profile_typed",
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
    "docs/native/pdf-report-v2.md": (
        "absent `--locale`",
        "OFL-1.1",
        "Identity-H",
        "ToUnicode",
        "printable ASCII dynamic values",
        "arbitrary Unicode",
        "PDF/UA",
        "Poppler",
        "render-sparse-pdf",
        "structural-native-sparse-linear-localized-pdf-report-receipt.v2",
    ),
    "docs/native/pdf-report-sparse-v1.md": (
        "render-sparse-pdf",
        "structural-native-sparse-linear-pdf-report-receipt.v1",
        "structural-native-model-ir-linear-pdf-report-receipt.v1",
        "no clock metadata",
        "localized sparse-linear PDF v2",
        "PDF/UA",
        "HIP C2",
        "C6 decommission",
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
        "OFL-1.1",
        "en-US",
        "ko-KR",
        "sparse-linear",
        "arbitrary Unicode",
        "PDF/A",
        "tagged accessibility",
        "HIP C2",
        "C6",
    ):
        if token not in claim:
            blockers.append(f"pdf_report_scope_token_missing:{token}")

    try:
        font_bytes = (
            root / EMBEDDED_FONT_ASSET
        ).read_bytes()
        provenance = json.loads(
            (
                root
                / "native/crates/structural-report/assets/StructuralReportKoreanSubset.provenance.json"
            ).read_text(encoding="utf-8")
        )
        asset = provenance["asset"]
        origin = provenance["origin"]
        modification = provenance["modification"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        blockers.append(f"pdf_report_embedded_font_provenance_invalid:{exc}")
    else:
        if not all(isinstance(value, dict) for value in (asset, origin, modification)):
            blockers.append("pdf_report_embedded_font_provenance_shape_invalid")
            asset = {}
            origin = {}
            modification = {}
        if asset.get("byte_length") != len(font_bytes):
            blockers.append("pdf_report_embedded_font_length_mismatch")
        if asset.get("sha256") != hashlib.sha256(font_bytes).hexdigest():
            blockers.append("pdf_report_embedded_font_hash_mismatch")
        if asset.get("postscript_name") != "StructuralReportKoreanSubset":
            blockers.append("pdf_report_embedded_font_name_invalid")
        if origin.get("license") != "OFL-1.1":
            blockers.append("pdf_report_embedded_font_license_invalid")
        if modification.get("reserved_primary_names_removed") is not True:
            blockers.append("pdf_report_embedded_font_reserved_names_not_removed")

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
