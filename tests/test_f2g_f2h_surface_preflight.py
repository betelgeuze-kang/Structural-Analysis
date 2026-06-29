from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_f2g_f2h_surface_preflight.py"
SPEC = importlib.util.spec_from_file_location("build_f2g_f2h_surface_preflight", SCRIPT_PATH)
assert SPEC and SPEC.loader
preflight_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight_module)

RECOVERY_PATH = REPO_ROOT / "scripts" / "build_f2g_f2h_authoritative_surface_recovery_packet.py"
RECOVERY_SPEC = importlib.util.spec_from_file_location("build_f2g_f2h_authoritative_surface_recovery_packet", RECOVERY_PATH)
assert RECOVERY_SPEC and RECOVERY_SPEC.loader
recovery_module = importlib.util.module_from_spec(RECOVERY_SPEC)
RECOVERY_SPEC.loader.exec_module(recovery_module)


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write(path, json.dumps(payload))


def _complete_fixture(root: Path) -> None:
    (root / "implementation/phase1").mkdir(parents=True)
    _write(root / "implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt")
    _write_json(root / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json", {})
    _write(
        root / "implementation/phase1/run_g1_mgt_sparse_direct_physical_line_search_smoke.py",
        "frame_service_tangent_source = 'real_per_element'\n",
    )
    product = root / "implementation/phase1/release_evidence/productization"
    _write_json(
        product / "g1_mgt_regularized_assembled_direction_smoke.local.json",
        {
            "status": "ready",
            "uses_real_mgt_model": True,
            "promotes_g1_closure": False,
            "frame_service_tangent_source": "real_per_element",
            "assembled_tangent_parity": {"pass": True},
        },
    )
    _write_json(
        product / "g1_null_space_mode_audit.local.json",
        {
            "status": "ready",
            "uses_real_mgt_model": True,
            "promotes_g1_closure": False,
            "singularity_indicators": {"near_null_mode_count": 1},
            "mode_rows": [{"mode_index": 0}],
        },
    )
    _write_json(
        product / "mgt_boundary_entity_support_receipt.json",
        {
            "support": {
                "canonical_support_constraint_entity_ready": True,
                "canonical_elastic_link_entity_ready": True,
            },
            "summary": {
                "unmatched_support_constraint_node_count": 0,
                "unmatched_elastic_link_node_count": 0,
            },
        },
    )
    _write_json(
        product / "mgt_boundary_spring_tangent_receipt.json",
        {
            "support": {
                "authored_support_mask_application_ready": True,
                "finite_elastic_link_spring_tangent_ready": True,
            },
            "summary": {
                "authored_support_node_count_missing_from_boundary_subsystem": 0,
                "elastic_link_rows_skipped": 0,
            },
        },
    )


def test_preflight_blocks_without_authoritative_surfaces(tmp_path: Path) -> None:
    payload = preflight_module.build_preflight(repo_root=tmp_path)

    assert payload["status"] == "blocked"
    assert payload["summary"]["blocker_count"] == len(preflight_module.SURFACES)
    assert payload["promotes_g1_closure"] is False


def test_preflight_passes_with_all_required_surfaces(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)

    payload = preflight_module.build_preflight(repo_root=tmp_path)

    assert payload["status"] == "ready"
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["blocker_count"] == 0
    assert payload["summary"]["f2g_support_elastic_reconciliation_ready_to_run"] is True
    assert payload["summary"]["f2h_lightweight_continuation_ready_to_run"] is False
    assert payload["next_actions"] == ["run_f2g_support_elastic_link_reconciliation_audit"]


def test_recovery_packet_lists_only_missing_surfaces(tmp_path: Path) -> None:
    _complete_fixture(tmp_path)
    (tmp_path / "implementation/phase1/release_evidence/productization/g1_null_space_mode_audit.local.json").unlink()
    preflight = preflight_module.build_preflight(repo_root=tmp_path)
    preflight_path = tmp_path / ".betelgeuze/f2g_f2h_surface_preflight.local.json"
    _write_json(preflight_path, preflight)

    payload = recovery_module.build_recovery_packet(repo_root=tmp_path, preflight_path=preflight_path)

    assert payload["status"] == "blocked"
    assert payload["recovery_item_count"] == 1
    assert payload["recovery_items"][0]["surface_id"] == "near_null_mode_packet"
