from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


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
    assert registry["authority_rules"]["solver_truth_owner"] == "structural_analysis_core"
    assert registry["authority_rules"]["workbench_truth_owner"] == "none"
    assert registry["authority_rules"]["ai_truth_owner"] == "none"
    assert registry["authority_rules"]["fallback_promotion_allowed"] is False
    assert generator.check_outputs(ROOT) == []


def test_public_api_exposes_only_explicit_public_rows_when_filtered() -> None:
    all_rows = capabilities()
    public_rows = capabilities(public_only=True)

    assert all_rows
    assert public_rows
    assert all(row["public"] for row in public_rows)
    assert all(row["status"] in {"supported", "bounded_public"} for row in public_rows)
    assert {row["id"] for row in public_rows} < {row["id"] for row in all_rows}
    assert any(row["id"] == "vv.opensees_level2" and not row["public"] for row in all_rows)
    assert any(
        row["id"] == "analysis.nonlinear_corotational_fiber_frame_2d"
        and row["status"] == "experimental"
        for row in all_rows
    )


def test_cli_prints_same_generated_capability_registry(capsys: object) -> None:
    assert cli_main(["--capabilities"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["schema_version"] == "structural-analysis-capabilities.v1"
    assert payload["authority_rules"]["workbench_truth_owner"] == "none"
    assert payload["capabilities"] == list(capabilities())


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
    assert "generatedCapabilities.json" in component
    assert "data-wb2-capability-table" in component
