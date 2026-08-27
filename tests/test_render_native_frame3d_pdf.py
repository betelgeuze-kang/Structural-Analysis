from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import jsonschema
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "render_native_frame3d_pdf.py"
SCHEMA_PATH = (
    ROOT
    / "src"
    / "structural_analysis"
    / "schemas"
    / "native_frame3d_pdf_receipt_v1.schema.json"
)


def load_module():
    spec = importlib.util.spec_from_file_location("render_native_frame3d_pdf", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(character: str) -> str:
    return f"sha256:{character * 64}"


def sources():
    result = {
        "schema_version": "structural-native-linear-frame3d-result-ir.v1",
        "result_id": "result.LC1",
        "result_hash": digest("a"),
        "bindings": {
            "model_id": "model.alpha",
            "model_content_hash": digest("b"),
            "load_pattern_id": "LC1",
            "load_combination_id": None,
        },
        "nodes": [
            {
                "node_id": "N1",
                "displacement_m_rad": [0.0] * 6,
                "reaction_n_nm": [-1000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            },
            {
                "node_id": "N2",
                "displacement_m_rad": [1.0e-6, 0.0, 0.0, 0.0, 0.0, 0.0],
                "reaction_n_nm": [0.0] * 6,
            },
        ],
        "members": [
            {
                "member_id": "E1",
                "end_i_force_n_nm": [-1000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                "end_j_force_n_nm": [1000.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            }
        ],
    }
    gates = {
        "free_residual_scaled_linf": 1.0e-15,
        "free_residual_scaled_linf_tolerance": 1.0e-9,
        "global_force_balance_scaled_linf": 2.0e-15,
        "global_force_balance_scaled_linf_tolerance": 1.0e-9,
        "global_moment_balance_scaled_linf": 3.0e-15,
        "global_moment_balance_scaled_linf_tolerance": 1.0e-9,
        "member_force_replay_scaled_linf": 4.0e-15,
        "member_force_replay_scaled_linf_tolerance": 1.0e-9,
        "fallback_count": 0,
        "regularization_count": 0,
    }
    report = {
        "schema_version": "structural-native-linear-frame3d-report-ir.v1",
        "report_id": "report.LC1",
        "report_hash": digest("c"),
        "source_result": {
            "result_id": result["result_id"],
            "result_hash": result["result_hash"],
        },
        "summary": {
            "model_id": "model.alpha",
            "formulation": "linear_timoshenko_frame3d",
            "backend": "cpu_reference_dense",
        },
        "gates": gates,
        "extrema": [
            {
                "quantity": "displacement",
                "entity_id": "N2",
                "component": "UX",
                "signed_value": 1.0e-6,
                "absolute_value": 1.0e-6,
                "unit": "m",
            },
            {
                "quantity": "reaction",
                "entity_id": "N1",
                "component": "FX",
                "signed_value": -1000.0,
                "absolute_value": 1000.0,
                "unit": "N",
            },
            {
                "quantity": "member_end_force",
                "entity_id": "E1",
                "component": "FX_I",
                "signed_value": -1000.0,
                "absolute_value": 1000.0,
                "unit": "N",
            },
        ],
        "limitations": ["cpu_only_no_hip_parity", "no_design_or_release_authority"],
        "authority": {
            "source_result": "bounded_candidate",
            "presentation": "deterministic_projection",
            "comparison": "not_evaluated",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
    }
    comparison = {
        "schema_version": "structural-native-linear-frame3d-comparison-ir.v1",
        "comparison_id": "comparison.LC1",
        "comparison_hash": digest("d"),
        "source_result": {
            "result_id": result["result_id"],
            "result_hash": result["result_hash"],
        },
        "source_reference": {
            "reference_id": "reference.LC1",
            "reference_hash": digest("e"),
            "tool": "synthetic_fixture",
            "version": "test-v1",
            "origin": "synthetic_contract_fixture",
        },
        "summary": {
            "passed": True,
            "families": [
                {
                    "quantity": quantity,
                    "row_count": 1,
                    "failing_row_count": 0,
                    "max_scaled_difference": 0.0,
                    "tolerance": tolerance,
                    "worst_entity_id": entity,
                    "worst_component": component,
                    "passed": True,
                }
                for quantity, tolerance, entity, component in [
                    ("displacement", 0.005, "N2", "UX"),
                    ("reaction", 0.005, "N1", "FX"),
                    ("member_end_force", 0.01, "E1", "FX_I"),
                ]
            ],
        },
        "rows": [
            {
                "quantity": "displacement",
                "entity_id": "N2",
                "component": "UX",
                "unit": "m",
                "native_value": 1.0e-6,
                "reference_value": 1.0e-6,
                "scaled_difference": 0.0,
                "tolerance": 0.005,
                "passed": True,
            }
        ],
        "authority": {
            "external_validation": "not_established",
        },
    }
    return result, report, comparison


def test_pdf_and_receipt_are_byte_deterministic_and_source_bound(tmp_path: Path):
    module = load_module()
    result, report, comparison = sources()

    first, first_pages = module.render_pdf_bytes(result, report, comparison)
    second, second_pages = module.render_pdf_bytes(result, report, comparison)

    assert first == second
    assert first.startswith(b"%PDF-1.4")
    assert first_pages == second_pages >= 1
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(first)
    reader = PdfReader(pdf_path)
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Native Frame3D bounded analysis report" in extracted
    assert "not external validation" in extracted
    assert "Comparison component rows" in extracted
    assert "not_established" in extracted

    receipt = module.build_receipt(
        first,
        first_pages,
        result,
        report,
        comparison,
        "structural-cli 0.1.0",
        "4.4.3",
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(receipt)
    assert receipt["pdf"]["sha256"] == f"sha256:{hashlib.sha256(first).hexdigest()}"
    assert receipt["source_result"]["result_hash"] == result["result_hash"]
    assert receipt["source_comparison"]["comparison_hash"] == comparison["comparison_hash"]
    assert receipt["authority"]["external_validation"] == "not_established"


def test_pdf_without_comparison_keeps_external_validation_unestablished(tmp_path: Path):
    module = load_module()
    result, report, _ = sources()

    pdf, pages = module.render_pdf_bytes(result, report, None)
    path = tmp_path / "no-comparison.pdf"
    path.write_bytes(pdf)
    extracted = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    assert "No ReferenceIR/ComparisonIR pair was attached" in extracted
    assert "External validation is not established" in extracted

    receipt = module.build_receipt(
        pdf, pages, result, report, None, "structural-cli 0.1.0", "4.4.3"
    )
    assert receipt["source_comparison"] is None
    assert receipt["authority"]["external_validation"] == "not_established"


def test_no_overwrite_pair_publish_fails_without_mutating_existing_output(tmp_path: Path):
    module = load_module()
    pdf_path = tmp_path / "report.pdf"
    receipt_path = tmp_path / "report.pdf.receipt.json"
    pdf_path.write_bytes(b"existing")

    try:
        module._write_pair_no_overwrite(pdf_path, receipt_path, b"new", b"{}\n")
    except module.NativeFramePdfError as error:
        assert error.code == "output_exists"
    else:
        raise AssertionError("existing output must fail closed")

    assert pdf_path.read_bytes() == b"existing"
    assert not receipt_path.exists()


def test_partial_comparison_arguments_fail_before_cli_execution(tmp_path: Path):
    module = load_module()
    result_path = tmp_path / "result.json"
    result_path.write_text("{}", encoding="utf-8")

    try:
        module._load_verified_sources(
            tmp_path / "missing-cli",
            result_path,
            "report.LC1",
            tmp_path / "reference.json",
            None,
        )
    except module.NativeFramePdfError as error:
        assert error.code == "comparison_arguments_incomplete"
    else:
        raise AssertionError("partial comparison configuration must fail closed")
