from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_product_capabilities_surface.py"
PM_REPORT_PATH = REPO_ROOT / "scripts" / "report_pm_release_gate.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_product_capabilities_surface", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

pm_spec = importlib.util.spec_from_file_location("report_pm_release_gate", PM_REPORT_PATH)
assert pm_spec is not None
pm_report = importlib.util.module_from_spec(pm_spec)
assert pm_spec.loader is not None
sys.modules[pm_spec.name] = pm_report
pm_spec.loader.exec_module(pm_report)


def _capability_by_id(surface: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = surface["capability_rows"]
    assert isinstance(rows, list)
    return {
        str(row["capability_id"]): row
        for row in rows
        if isinstance(row, dict) and "capability_id" in row
    }


def test_product_capabilities_surface_exposes_structural_solver_row() -> None:
    surface = module.build_product_capabilities_surface(repo_root=REPO_ROOT)
    rows = _capability_by_id(surface)

    assert surface["schema_version"] == "product-capabilities-surface.v1"
    assert surface["surface_id"] == "product_capabilities_surface"
    assert surface["surface_kind"] == "product_capabilities_surface"
    assert surface["status"] == "ready"
    assert surface["reason_code"] == "PASS"
    assert surface["contract_pass"] is True
    assert surface["locked"] is False
    assert surface["claim_locked"] is False
    assert surface["blockers"] == []
    assert surface["read_model"] == {
        "route": "/product/capabilities",
        "artifact": "implementation/phase1/release_evidence/surface/product_capabilities_surface.json",
        "mutation_allowed": False,
    }
    assert surface["capability_count"] == 1
    assert surface["ready_capability_count"] == 1
    assert surface["blocked_capability_count"] == 0
    assert surface["blocked_capability_register_count"] == 0
    assert surface["first_blocked_capability_id"] == ""
    assert surface["first_blocked_capability_next_action"] == ""
    assert surface["blocked_capability_register"] == []

    assert set(rows) == {"structural_solver_restricted_alpha_surface"}

    structural = rows["structural_solver_restricted_alpha_surface"]
    assert structural["title"] == "Restricted alpha structural solver evidence"
    assert structural["capability_kind"] == "engineering_core"
    assert structural["state"] == "ready"
    assert structural["contract_pass"] is True
    assert structural["blocker_count"] == 0
    assert structural["next_actions"] == []
    assert structural["summary"] == {
        "surface_count": 8,
        "present_surface_count": 8,
        "ready_surface_count": 8,
    }
    assert structural["evidence_artifacts"] == [
        "implementation/phase1/release_evidence/surface/element_material_breadth_gate_report.json",
        "implementation/phase1/release_evidence/surface/general_fe_contact_benchmark_gate_report.json",
        "implementation/phase1/release_evidence/surface/material_constitutive_gate_report.json",
        "implementation/phase1/release_evidence/surface/solver_breadth_report.json",
        "implementation/phase1/release_evidence/surface/solver_truthfulness_gate_report.json",
        "implementation/phase1/release_evidence/surface/steel_composite_constitutive_gate_report.json",
        "implementation/phase1/release_evidence/surface/structural_contact_gate_report.json",
        "implementation/phase1/release_evidence/surface/surface_interaction_benchmark_gate_report.json",
    ]
    assert surface["reuse_policy"] == (
        "product_capabilities_surface_aggregates_structural_solver_evidence"
    )
    assert "structural analysis solver product" in surface["claim_boundary"]
    assert "Non-structural product domains" in surface["claim_boundary"]
    surface_text = json.dumps(surface, ensure_ascii=False).lower()
    assert not any(
        token in surface_text for token in ("gpcr", "pocketmd", "md3bead")
    )


def test_product_capabilities_surface_builder_has_no_non_structural_defaults() -> None:
    module_names = set(vars(module))
    blocked_names = {
        name
        for name in module_names
        if any(token in name.lower() for token in ("gpcr", "pocketmd", "md3bead"))
    }

    assert blocked_names == set()


def test_product_capabilities_surface_cli_writes_pm_visible_ready_surface(
    tmp_path: Path,
) -> None:
    out = tmp_path / "surface" / "product_capabilities_surface.json"

    assert module.main(["--repo-root", str(REPO_ROOT), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["input_checksums"][
        "scripts/build_product_capabilities_surface.py"
    ].startswith("sha256:")
    assert payload["surface_id"] == "product_capabilities_surface"

    rows = pm_report._evidence_surface_rows(out.parent)
    assert rows == []
