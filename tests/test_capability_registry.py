from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SCRIPT = ROOT / "scripts/generate_capability_surfaces.py"
SPEC = importlib.util.spec_from_file_location("generate_capability_surfaces", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)

from structural_analysis.api import capabilities  # noqa: E402
from structural_analysis.api.cli import main as cli_main  # noqa: E402


def test_registry_is_valid_and_all_generated_surfaces_are_current() -> None:
    registry = generator.load_registry(ROOT)

    assert registry["schema_version"] == "structural-analysis-capabilities.v1"
    assert (
        registry["authority_rules"]["solver_truth_owner"] == "structural_analysis_core"
    )
    assert registry["authority_rules"]["workbench_truth_owner"] == "none"
    assert registry["authority_rules"]["ai_truth_owner"] == "none"
    assert registry["authority_rules"]["fallback_promotion_allowed"] is False
    assert Counter(row["status"] for row in registry["capabilities"]) == {
        "supported": 1,
        "bounded_public": 9,
        "experimental": 6,
        "shadow_only": 1,
        "blocked": 4,
    }
    assert Counter(
        row["implementation_status"] for row in registry["capabilities"]
    ) == {"implemented": 17, "partial": 4}
    assert Counter(
        row["authority_status"] for row in registry["capabilities"]
    ) == {"granted": 10, "candidate": 7, "none": 4}
    assert generator.check_outputs(ROOT) == []


def test_public_api_filters_rows_and_returns_independent_copies() -> None:
    all_rows = capabilities()
    public_rows = capabilities(public_only=True)

    assert len(all_rows) == 21
    assert len(public_rows) == 10
    assert all(row["public"] for row in public_rows)
    assert all(row["implementation_status"] == "implemented" for row in public_rows)
    assert all(row["authority_status"] == "granted" for row in public_rows)
    assert all(row["status"] in {"supported", "bounded_public"} for row in public_rows)
    assert any(
        row["id"] == "vv.opensees_level2" and not row["public"] for row in all_rows
    )
    assert any(row["status"] == "shadow_only" for row in all_rows)
    assert any(
        row["id"] == "analysis.nonlinear_corotational_fiber_frame_2d"
        and row["status"] == "experimental"
        and "finite rigid offsets" in row["limitations"][0]
        and "optional RZ end releases" in row["limitations"][0]
        for row in all_rows
    )
    assert any(
        row["id"] == "backend.nonlinear_sparse"
        and row["authority"]
        == "bounded_native_coo_csr_and_fail_closed_exact_conditioning_candidate"
        for row in all_rows
    )
    assert any(
        row["id"]
        == "analysis.nonlinear_corotational_fiber_frame_2d_direct_displacement"
        and row["implementation_status"] == "implemented"
        and row["authority_status"] == "candidate"
        for row in all_rows
    )
    assert any(
        row["id"] == "analysis.nonlinear_corotational_fiber_frame_2d_arc_length"
        and row["implementation_status"] == "implemented"
        and row["authority_status"] == "candidate"
        for row in all_rows
    )
    assert any(
        row["id"] == "material.fracture_energy_concrete"
        and row["status"] == "experimental"
        and row["public"] is False
        for row in all_rows
    )

    all_rows[0]["limitations"].append("consumer mutation")
    assert "consumer mutation" not in capabilities()[0]["limitations"]


def test_cli_prints_full_and_public_capability_views(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli_main(["--capabilities"]) == 0
    full_payload = json.loads(capsys.readouterr().out)
    assert full_payload["schema_version"] == "structural-analysis-capabilities.v1"
    assert len(full_payload["capabilities"]) == 21

    assert cli_main(["--capabilities", "--public-only"]) == 0
    public_payload = json.loads(capsys.readouterr().out)
    assert len(public_payload["capabilities"]) == 10
    assert all(row["public"] for row in public_payload["capabilities"])


def test_workbench_consumes_generated_registry_without_truth_ownership() -> None:
    payload = json.loads(
        (ROOT / "src/workbench-v2/model/generatedCapabilities.json").read_text(
            encoding="utf-8"
        )
    )
    component = (
        ROOT / "src/workbench-v2/components/CapabilitySupportPanel.tsx"
    ).read_text(encoding="utf-8")

    assert payload["authorityRules"]["workbench_truth_owner"] == "none"
    assert payload["authorityRules"]["ai_truth_owner"] == "none"
    assert len(payload["capabilities"]) == 21
    assert "generatedCapabilities.json" in component
    assert "data-wb2-capability-table" in component
    assert "data-implementation-status" in component
    assert "data-authority-status" in component


def test_registry_validation_rejects_conflated_or_invalid_authority_axes() -> None:
    registry = deepcopy(generator.load_registry(ROOT))
    registry["capabilities"][0]["authority_status"] = "none"

    with pytest.raises(
        generator.CapabilityRegistryError,
        match="public capability cannot have authority_status none",
    ):
        generator.validate_registry(registry, repo_root=ROOT)

    registry = deepcopy(generator.load_registry(ROOT))
    registry["capabilities"][0]["implementation_status"] = "unknown"
    with pytest.raises(
        generator.CapabilityRegistryError,
        match="invalid implementation_status",
    ):
        generator.validate_registry(registry, repo_root=ROOT)


def test_registry_validation_fails_closed_for_missing_evidence() -> None:
    registry = deepcopy(generator.load_registry(ROOT))
    registry["capabilities"][0]["evidence"] = ["missing/evidence.json"]

    with pytest.raises(
        generator.CapabilityRegistryError, match="missing evidence path"
    ):
        generator.validate_registry(registry, repo_root=ROOT)
