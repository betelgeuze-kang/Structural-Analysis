#!/usr/bin/env python3
"""Render a deterministic, source-bound PDF from a verified native Frame3D ResultIR."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


RECEIPT_SCHEMA_VERSION = "structural-native-linear-frame3d-pdf-receipt.v1"
RENDERER_PROFILE = "reportlab_invariant_a4_ascii.v1"
PDF_CLAIM_BOUNDARY = (
    "deterministic_source_bound_presentation_of_verified_native_replay_"
    "not_external_validation_design_commercial_or_release_authority"
)


class NativeFramePdfError(RuntimeError):
    """A stable fail-closed PDF projection error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _reject_duplicate_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise NativeFramePdfError(
                "duplicate_json_key", f"Duplicate JSON key is not allowed: {key}"
            )
        value[key] = item
    return value


def _strict_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8", errors="strict")
        value = json.loads(decoded, object_pairs_hook=_reject_duplicate_pairs)
    except NativeFramePdfError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NativeFramePdfError(
            f"{label}_json_invalid", f"{label} is not strict UTF-8 JSON: {error}"
        ) from error
    if not isinstance(value, dict):
        raise NativeFramePdfError(
            f"{label}_json_invalid", f"{label} JSON root must be an object"
        )
    return value


def _read_strict_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise NativeFramePdfError(
            f"{label}_read_failed", f"Could not read {label}: {error}"
        ) from error
    return _strict_json_bytes(payload, label)


def _run_cli(command: Sequence[str], label: str, accepted_codes: set[int]) -> bytes:
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise NativeFramePdfError(
            f"{label}_execution_failed", f"Could not execute structural-cli: {error}"
        ) from error
    if completed.returncode not in accepted_codes:
        detail = completed.stdout or completed.stderr
        rendered = detail.decode("utf-8", errors="replace").strip()
        raise NativeFramePdfError(
            f"{label}_rejected",
            f"structural-cli {label} exited {completed.returncode}: {rendered[:1000]}",
        )
    if completed.stderr:
        raise NativeFramePdfError(
            f"{label}_stderr_not_empty",
            f"structural-cli {label} emitted unexpected stderr",
        )
    return completed.stdout


def _load_verified_sources(
    structural_cli: Path,
    result_path: Path,
    report_id: str,
    reference_path: Path | None,
    comparison_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, str]:
    if (reference_path is None) != (comparison_id is None):
        raise NativeFramePdfError(
            "comparison_arguments_incomplete",
            "--reference-ir and --comparison-id must be supplied together",
        )
    result = _read_strict_json(result_path, "result_ir")
    report_payload = _run_cli(
        [
            str(structural_cli),
            "result",
            "report-frame3d",
            str(result_path),
            "--report-id",
            report_id,
            "--output",
            "report-ir",
        ],
        "report_replay",
        {0},
    )
    report = _strict_json_bytes(report_payload, "report_ir")
    if report.get("schema_version") != "structural-native-linear-frame3d-report-ir.v1":
        raise NativeFramePdfError(
            "report_replay_schema_invalid",
            "Rust replay did not return the required ReportIR schema",
        )
    if result.get("schema_version") != "structural-native-linear-frame3d-result-ir.v1":
        raise NativeFramePdfError(
            "result_ir_schema_invalid", "Source is not native linear Frame3D ResultIR v1"
        )
    source_result = report.get("source_result")
    if not isinstance(source_result, dict) or (
        source_result.get("result_id") != result.get("result_id")
        or source_result.get("result_hash") != result.get("result_hash")
    ):
        raise NativeFramePdfError(
            "report_source_binding_invalid",
            "Rust-replayed ReportIR is not bound to the supplied ResultIR",
        )

    comparison = None
    if reference_path is not None and comparison_id is not None:
        comparison_payload = _run_cli(
            [
                str(structural_cli),
                "result",
                "compare-frame3d",
                str(result_path),
                str(reference_path),
                "--comparison-id",
                comparison_id,
                "--output",
                "comparison-ir",
            ],
            "comparison_replay",
            {0, 2},
        )
        comparison = _strict_json_bytes(comparison_payload, "comparison_ir")
        if (
            comparison.get("schema_version")
            != "structural-native-linear-frame3d-comparison-ir.v1"
        ):
            raise NativeFramePdfError(
                "comparison_replay_schema_invalid",
                "Rust replay did not return an auditable ComparisonIR artifact",
            )
        comparison_source = comparison.get("source_result")
        if not isinstance(comparison_source, dict) or (
            comparison_source.get("result_id") != result.get("result_id")
            or comparison_source.get("result_hash") != result.get("result_hash")
        ):
            raise NativeFramePdfError(
                "comparison_source_binding_invalid",
                "ComparisonIR is not bound to the supplied ResultIR",
            )

    version_payload = _run_cli([str(structural_cli), "--version"], "version", {0})
    cli_version = version_payload.decode("ascii", errors="strict").strip()
    if not cli_version.startswith("structural-cli "):
        raise NativeFramePdfError(
            "cli_version_invalid", "structural-cli returned an unexpected version identity"
        )
    return result, report, comparison, cli_version


def _ascii(value: Any) -> str:
    return str(value).encode("ascii", errors="replace").decode("ascii")


def _number(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "INVALID"
    number = float(value)
    if not math.isfinite(number):
        return "NONFINITE"
    return f"{number:.9e}"


class _PdfDocument:
    def __init__(self, title: str) -> None:
        try:
            from reportlab.lib.colors import HexColor
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfbase.pdfmetrics import stringWidth
            from reportlab.pdfgen import canvas
        except ImportError as error:
            raise NativeFramePdfError(
                "reportlab_unavailable", "ReportLab is required to render the PDF"
            ) from error

        self._HexColor = HexColor
        self._A4 = A4
        self._string_width = stringWidth
        self._buffer = io.BytesIO()
        self._canvas = canvas.Canvas(
            self._buffer,
            pagesize=A4,
            invariant=1,
            pageCompression=0,
            pdfVersion=(1, 4),
        )
        self._canvas.setTitle(_ascii(title))
        self._canvas.setAuthor("Structural Analysis")
        self._canvas.setCreator(RENDERER_PROFILE)
        self._canvas.setSubject(PDF_CLAIM_BOUNDARY)
        self._width, self._height = A4
        self._left = 42.0
        self._right = self._width - 42.0
        self._bottom = 48.0
        self._y = 0.0
        self._active_table_header: str | None = None
        self.page_count = 0
        self._new_page()

    def _new_page(self) -> None:
        if self.page_count:
            self._canvas.showPage()
        self.page_count += 1
        self._canvas.setStrokeColor(self._HexColor("#1F4E79"))
        self._canvas.setLineWidth(1.2)
        self._canvas.line(self._left, self._height - 39, self._right, self._height - 39)
        self._canvas.setFillColor(self._HexColor("#1F4E79"))
        self._canvas.setFont("Helvetica-Bold", 8)
        self._canvas.drawString(self._left, self._height - 31, "NATIVE FRAME3D - BOUNDED REPORT")
        self._canvas.setFillColor(self._HexColor("#555555"))
        self._canvas.setFont("Helvetica", 6.5)
        footer = "bounded presentation - not external validation, design, commercial, or release authority"
        self._canvas.drawString(self._left, 25, footer)
        self._canvas.drawRightString(self._right, 25, f"Page {self.page_count}")
        self._y = self._height - 56

    def _ensure(self, height: float) -> None:
        if self._y - height < self._bottom:
            self._new_page()

    def _wrapped(self, text: str, font: str, size: float, width: float) -> Iterable[str]:
        words: list[str] = []
        for token in _ascii(text).split():
            remainder = token
            while self._string_width(remainder, font, size) > width:
                split_at = 1
                while (
                    split_at < len(remainder)
                    and self._string_width(remainder[: split_at + 1], font, size) <= width
                ):
                    split_at += 1
                words.append(remainder[:split_at])
                remainder = remainder[split_at:]
            if remainder:
                words.append(remainder)
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if self._string_width(candidate, font, size) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def text(
        self,
        value: Any,
        *,
        font: str = "Helvetica",
        size: float = 8.3,
        color: str = "#202124",
        indent: float = 0.0,
        leading: float = 10.5,
        before: float = 0.0,
    ) -> None:
        self._y -= before
        lines = list(self._wrapped(_ascii(value), font, size, self._right - self._left - indent))
        for line in lines:
            self._ensure(leading)
            self._canvas.setFillColor(self._HexColor(color))
            self._canvas.setFont(font, size)
            self._canvas.drawString(self._left + indent, self._y, line)
            self._y -= leading

    def section(self, title: str) -> None:
        self._active_table_header = None
        self._ensure(45)
        self._y -= 8
        self._canvas.setFillColor(self._HexColor("#D9EAF7"))
        self._canvas.rect(self._left, self._y - 4, self._right - self._left, 17, stroke=0, fill=1)
        self._canvas.setFillColor(self._HexColor("#17365D"))
        self._canvas.setFont("Helvetica-Bold", 10)
        self._canvas.drawString(self._left + 5, self._y, _ascii(title))
        self._y -= 14

    def title(self, title: str, subtitle: str) -> None:
        self.text(title, font="Helvetica-Bold", size=18, color="#17365D", leading=22)
        self.text(subtitle, font="Helvetica", size=9, color="#555555", leading=13)

    def key_value(self, key: str, value: Any) -> None:
        self._ensure(11)
        self._canvas.setFillColor(self._HexColor("#333333"))
        self._canvas.setFont("Helvetica-Bold", 7.5)
        self._canvas.drawString(self._left, self._y, _ascii(key))
        self._canvas.setFont("Courier", 7.2)
        rendered = _ascii(value)
        max_width = self._right - (self._left + 118)
        if self._string_width(rendered, "Courier", 7.2) <= max_width:
            self._canvas.drawString(self._left + 118, self._y, rendered)
            self._y -= 10
        else:
            self._y -= 10
            self.text(rendered, font="Courier", size=6.8, indent=12, leading=8.5)

    def table_header(self, columns: str) -> None:
        self._active_table_header = columns
        self.text(columns, font="Courier-Bold", size=6.6, color="#17365D", leading=8.5)

    def table_row(self, row: str, *, passed: bool | None = None) -> None:
        if self._y - 7.9 < self._bottom:
            self._new_page()
            if self._active_table_header is not None:
                self.text(
                    self._active_table_header,
                    font="Courier-Bold",
                    size=6.6,
                    color="#17365D",
                    leading=8.5,
                )
        color = "#8B1A1A" if passed is False else "#202124"
        self.text(row, font="Courier", size=6.3, color=color, leading=7.9)

    def finish(self) -> bytes:
        self._canvas.save()
        return self._buffer.getvalue()


def render_pdf_bytes(
    result: dict[str, Any],
    report: dict[str, Any],
    comparison: dict[str, Any] | None,
) -> tuple[bytes, int]:
    document = _PdfDocument(f"Native Frame3D report - {report.get('report_id', 'unknown')}")
    summary = report.get("summary", {})
    bindings = result.get("bindings", {})
    document.title(
        "Native Frame3D bounded analysis report",
        "Verified Rust replay projected to deterministic PDF presentation",
    )
    document.text(
        PDF_CLAIM_BOUNDARY,
        font="Helvetica-Bold",
        size=8.5,
        color="#8B1A1A",
        before=4,
    )

    document.section("Identity and source binding")
    for key, value in [
        ("Report ID", report.get("report_id")),
        ("Report hash", report.get("report_hash")),
        ("Result ID", result.get("result_id")),
        ("Result hash", result.get("result_hash")),
        ("Model ID", bindings.get("model_id")),
        ("Model content hash", bindings.get("model_content_hash")),
        ("Load pattern", bindings.get("load_pattern_id")),
        ("Load combination", bindings.get("load_combination_id")),
        ("Formulation", summary.get("formulation")),
        ("Backend", summary.get("backend")),
    ]:
        document.key_value(key, value)

    document.section("Promotion gates")
    gates = report.get("gates", {})
    document.table_header("GATE                                      METRIC          TOLERANCE       STATUS")
    gate_rows = [
        ("free residual scaled L-inf", "free_residual_scaled_linf", "free_residual_scaled_linf_tolerance"),
        ("global force balance scaled L-inf", "global_force_balance_scaled_linf", "global_force_balance_scaled_linf_tolerance"),
        ("global moment balance scaled L-inf", "global_moment_balance_scaled_linf", "global_moment_balance_scaled_linf_tolerance"),
        ("member-force replay scaled L-inf", "member_force_replay_scaled_linf", "member_force_replay_scaled_linf_tolerance"),
    ]
    for label, metric_key, tolerance_key in gate_rows:
        document.table_row(
            f"{label:<41} {_number(gates.get(metric_key)):>14} "
            f"{_number(gates.get(tolerance_key)):>14} {'PASS':>7}"
        )
    document.key_value("Fallback count", gates.get("fallback_count"))
    document.key_value("Regularization count", gates.get("regularization_count"))

    document.section("Absolute extrema")
    document.table_header("QUANTITY           ENTITY              COMP          SIGNED VALUE        ABS VALUE UNIT")
    for row in report.get("extrema", []):
        document.table_row(
            f"{_ascii(row.get('quantity')):<18.18} {_ascii(row.get('entity_id')):<19.19} "
            f"{_ascii(row.get('component')):<8.8} {_number(row.get('signed_value')):>16} "
            f"{_number(row.get('absolute_value')):>16} {_ascii(row.get('unit'))}"
        )

    document.section("Authority and limitations")
    for key, value in report.get("authority", {}).items():
        document.key_value(key, value)
    document.text("Limitations", font="Helvetica-Bold", size=8)
    for limitation in report.get("limitations", []):
        document.text(f"- {limitation}", font="Courier", size=6.8, indent=8, leading=8.5)

    document.section("Node results - global axes")
    document.table_header("NODE             UX(m)       UY(m)       UZ(m)      RX(rad)      RY(rad)      RZ(rad)")
    for node in result.get("nodes", []):
        values = " ".join(f"{_number(value):>11}" for value in node.get("displacement_m_rad", []))
        document.table_row(f"{_ascii(node.get('node_id')):<14.14} {values}")
    document.table_header("NODE             FX(N)       FY(N)       FZ(N)      MX(N*m)      MY(N*m)      MZ(N*m)")
    for node in result.get("nodes", []):
        values = " ".join(f"{_number(value):>11}" for value in node.get("reaction_n_nm", []))
        document.table_row(f"{_ascii(node.get('node_id')):<14.14} {values}")

    document.section("Member end forces - member-local axes")
    document.table_header("MEMBER/END       FX(N)       FY(N)       FZ(N)      MX(N*m)      MY(N*m)      MZ(N*m)")
    for member in result.get("members", []):
        member_id = _ascii(member.get("member_id"))
        for end, key in [("I", "end_i_force_n_nm"), ("J", "end_j_force_n_nm")]:
            values = " ".join(f"{_number(value):>11}" for value in member.get(key, []))
            document.table_row(f"{(member_id + '/' + end):<14.14} {values}")

    if comparison is None:
        document.section("External comparison")
        document.text(
            "No ReferenceIR/ComparisonIR pair was attached. External validation is not established.",
            font="Helvetica-Bold",
            color="#8B1A1A",
        )
    else:
        comparison_summary = comparison.get("summary", {})
        reference = comparison.get("source_reference", {})
        passed = comparison_summary.get("passed") is True
        document.section("Bounded native-to-external comparison")
        document.key_value("Comparison ID", comparison.get("comparison_id"))
        document.key_value("Comparison hash", comparison.get("comparison_hash"))
        document.key_value("Reference ID", reference.get("reference_id"))
        document.key_value("Reference hash", reference.get("reference_hash"))
        document.key_value("Reference tool", reference.get("tool"))
        document.key_value("Reference version", reference.get("version"))
        document.key_value("Reference origin", reference.get("origin"))
        document.key_value("Evaluated gate", "PASS" if passed else "CHECK")
        document.key_value("External validation", comparison.get("authority", {}).get("external_validation"))
        document.text(
            "A PASS means only that the attached, operator-declared or synthetic values satisfy the fixed tolerance profile.",
            font="Helvetica-Bold",
            size=7.5,
            color="#8B1A1A",
        )
        document.table_header("FAMILY              ROWS  FAILS       MAX SCALED         TOL STATUS WORST")
        for family in comparison_summary.get("families", []):
            family_passed = family.get("passed") is True
            document.table_row(
                f"{_ascii(family.get('quantity')):<19.19} {family.get('row_count', 0):>4} "
                f"{family.get('failing_row_count', 0):>6} {_number(family.get('max_scaled_difference')):>16} "
                f"{_number(family.get('tolerance')):>11} "
                f"{('PASS' if family_passed else 'CHECK'):>6} "
                f"{_ascii(family.get('worst_entity_id'))}/{_ascii(family.get('worst_component'))}",
                passed=family_passed,
            )
        document.section("Comparison component rows")
        document.table_header("QUANTITY           ENTITY       COMP UNIT        NATIVE      REFERENCE    SCALED      TOL STATUS")
        for row in comparison.get("rows", []):
            row_passed = row.get("passed") is True
            document.table_row(
                f"{_ascii(row.get('quantity')):<18.18} {_ascii(row.get('entity_id')):<12.12} "
                f"{_ascii(row.get('component')):<5.5} {_ascii(row.get('unit')):<4.4} "
                f"{_number(row.get('native_value')):>12} {_number(row.get('reference_value')):>12} "
                f"{_number(row.get('scaled_difference')):>11} {_number(row.get('tolerance')):>10} "
                f"{'PASS' if row_passed else 'CHECK'}",
                passed=row_passed,
            )

    pdf_bytes = document.finish()
    return pdf_bytes, document.page_count


def build_receipt(
    pdf_bytes: bytes,
    page_count: int,
    result: dict[str, Any],
    report: dict[str, Any],
    comparison: dict[str, Any] | None,
    cli_version: str,
    reportlab_version: str,
) -> dict[str, Any]:
    comparison_receipt = None
    if comparison is not None:
        comparison_receipt = {
            "comparison_id": comparison["comparison_id"],
            "comparison_hash": comparison["comparison_hash"],
            "reference_id": comparison["source_reference"]["reference_id"],
            "reference_hash": comparison["source_reference"]["reference_hash"],
            "passed": comparison["summary"]["passed"],
            "external_validation": comparison["authority"]["external_validation"],
        }
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "renderer": {
            "profile": RENDERER_PROFILE,
            "structural_cli": cli_version,
            "reportlab": reportlab_version,
        },
        "pdf": {
            "sha256": f"sha256:{hashlib.sha256(pdf_bytes).hexdigest()}",
            "byte_length": len(pdf_bytes),
            "page_count": page_count,
        },
        "source_result": {
            "result_id": result["result_id"],
            "result_hash": result["result_hash"],
            "model_content_hash": result["bindings"]["model_content_hash"],
        },
        "source_report": {
            "report_id": report["report_id"],
            "report_hash": report["report_hash"],
        },
        "source_comparison": comparison_receipt,
        "authority": {
            "source_result": "bounded_candidate",
            "presentation": "deterministic_projection",
            "external_validation": "not_established",
            "engineering_design": "not_authoritative",
            "commercial_use": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": PDF_CLAIM_BOUNDARY,
    }


def _canonical_json(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "ascii"
    )


def _write_pair_no_overwrite(
    pdf_path: Path, receipt_path: Path, pdf_bytes: bytes, receipt_bytes: bytes
) -> None:
    if pdf_path == receipt_path:
        raise NativeFramePdfError(
            "output_paths_collide", "PDF and receipt output paths must be different"
        )
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists() or receipt_path.exists():
        raise NativeFramePdfError(
            "output_exists", "PDF rendering is no-overwrite; remove or rename existing outputs"
        )
    wrote_pdf = False
    wrote_receipt = False
    try:
        with pdf_path.open("xb") as handle:
            handle.write(pdf_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        wrote_pdf = True
        with receipt_path.open("xb") as handle:
            handle.write(receipt_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        wrote_receipt = True
    except OSError as error:
        if wrote_receipt:
            receipt_path.unlink(missing_ok=True)
        if wrote_pdf:
            pdf_path.unlink(missing_ok=True)
        raise NativeFramePdfError("output_write_failed", f"Could not publish outputs: {error}") from error


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structural-cli", required=True, type=Path)
    parser.add_argument("--result-ir", required=True, type=Path)
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--reference-ir", type=Path)
    parser.add_argument("--comparison-id")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--receipt-out", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    receipt_path = args.receipt_out or args.out.with_suffix(args.out.suffix + ".receipt.json")
    try:
        result, report, comparison, cli_version = _load_verified_sources(
            args.structural_cli,
            args.result_ir,
            args.report_id,
            args.reference_ir,
            args.comparison_id,
        )
        pdf_bytes, page_count = render_pdf_bytes(result, report, comparison)
        try:
            import reportlab
        except ImportError as error:
            raise NativeFramePdfError(
                "reportlab_unavailable", "ReportLab is required to render the PDF"
            ) from error
        receipt = build_receipt(
            pdf_bytes,
            page_count,
            result,
            report,
            comparison,
            cli_version,
            reportlab.Version,
        )
        receipt_bytes = _canonical_json(receipt)
        _write_pair_no_overwrite(args.out, receipt_path, pdf_bytes, receipt_bytes)
    except NativeFramePdfError as error:
        failure = {
            "schema_version": "structural-native-linear-frame3d-pdf-failure.v1",
            "success": False,
            "issues": [{"code": error.code, "detail": error.detail}],
            "claim_boundary": "pdf_projection_failed_closed_without_output_authority",
        }
        print(_canonical_json(failure).decode("ascii"), end="")
        return 2
    print(
        _canonical_json(
            {
                "schema_version": "structural-native-linear-frame3d-pdf-publish.v1",
                "success": True,
                "pdf": str(args.out),
                "receipt": str(receipt_path),
                "pdf_sha256": receipt["pdf"]["sha256"],
                "page_count": page_count,
                "claim_boundary": PDF_CLAIM_BOUNDARY,
            }
        ).decode("ascii"),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
