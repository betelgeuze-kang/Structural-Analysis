from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_workbench_case_normalizer_has_no_engineering_default_fillers() -> None:
    schema = (
        ROOT / "src/workbench-v2/model/caseSchema.ts"
    ).read_text(encoding="utf-8")

    assert "export type EvidenceValue<T>" in schema
    assert "SOURCE_SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/" in schema
    assert "Number.isInteger(value)" in schema
    assert "finite and in (0, 1]" in schema
    assert "iterations must be strictly increasing" in schema
    assert "duplicates ${current}" in schema
    assert "relativeIncrement: fin(row.relativeIncrement) ?? 0" not in schema
    assert "alpha: fin(row.alpha) ?? 1" not in schema
    assert "nodeCount: fin(rawModel.nodeCount) ?? 0" not in schema
    assert "residualTolerance: fin(rawAnalysis.residualTolerance) ?? 0" not in schema


def test_workbench_ui_renders_evidence_states_and_scaled_trace_separately() -> None:
    ribbon = (
        ROOT / "src/workbench-v2/components/AnalysisRibbon.tsx"
    ).read_text(encoding="utf-8")
    audit = (
        ROOT / "src/workbench-v2/components/ResidualAuditPanel.tsx"
    ).read_text(encoding="utf-8")

    for label in (
        "Characteristic length",
        "Scaled residual",
        "Scaled increment",
        "Scaled condition",
        "Scaling hash",
    ):
        assert label in ribbon
    for label in (
        "Legacy residual",
        "Raw transl. residual",
        "Raw rot. residual",
        "Scaled residual",
        "Raw transl. increment",
        "Raw rot. increment",
        "Scaled increment",
        "Scaled condition",
        "Scaling hash",
    ):
        assert label in audit
    assert "formatEvidence" in ribbon
    assert "formatEvidence" in audit


def test_workbench_demo_fixture_source_hashes_are_strict_sha256() -> None:
    fixtures = ROOT / "src/workbench-v2/model/fixtures"
    pattern = re.compile(r"^sha256:[0-9a-f]{64}$")

    for path in sorted(fixtures.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert pattern.fullmatch(payload["provenance"]["sourceSha256"]), path


def test_frontend_runtime_evidence_contract_is_registered() -> None:
    spec = (
        ROOT / "tests/frontend/workbench-v2-evidence-values.spec.ts"
    ).read_text(encoding="utf-8")

    assert "preserves explicit zero" in spec
    assert "marks invalid hash, counts, tolerance, alpha" in spec
    assert "preserves nested unknown fields" in spec
    assert "normalizes snake-case scaling evidence" in spec


def test_external_comparison_requires_scaling_evidence_on_both_sides() -> None:
    benchmark_schema = (
        ROOT / "src/workbench-v2/model/benchmark/benchmarkSchema.ts"
    ).read_text(encoding="utf-8")
    compare = (
        ROOT / "src/workbench-v2/components/ComparePanel.tsx"
    ).read_text(encoding="utf-8")

    assert "equationScalingAvailable" in benchmark_schema
    assert "equationScalingHash" in benchmark_schema
    assert "/^sha256:[0-9a-f]{64}$/" in benchmark_schema
    assert "currentScalingAvailable" in compare
    assert "referenceEquationScalingAvailable" in compare
    assert "both source-bound scaling receipts are attached" in compare
    assert "current scaling evidence unavailable" in compare
    assert "reference scaling evidence unavailable" in compare
