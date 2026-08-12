from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_pdf_report.py"
SPEC = importlib.util.spec_from_file_location("check_native_pdf_report", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pdf_report = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pdf_report
SPEC.loader.exec_module(pdf_report)


def _copy_contract(tmp_path: Path) -> None:
    for relative in ("native/capabilities.json", *pdf_report.REQUIRED_TOKENS):
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_repository_pdf_report_contract_is_evidence_backed() -> None:
    report = pdf_report.check_pdf_report_contract(ROOT)

    assert report["contract_pass"] is True
    assert report["cutover_gate"] == "C5"
    assert report["blockers"] == []


def test_contract_fails_closed_when_xref_tamper_evidence_disappears(
    tmp_path: Path,
) -> None:
    _copy_contract(tmp_path)
    path = tmp_path / "native/crates/structural-report/tests/pdf_render.rs"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "xref_tamper_is_detected_without_a_pdf_parser_dependency",
            "xref_tamper_evidence_removed",
        ),
        encoding="utf-8",
    )

    report = pdf_report.check_pdf_report_contract(tmp_path)

    assert report["contract_pass"] is False
    assert any(
        blocker.endswith(":xref_tamper_is_detected_without_a_pdf_parser_dependency")
        for blocker in report["blockers"]
    )
