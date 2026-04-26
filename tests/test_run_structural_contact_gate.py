from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("implementation/phase1/run_structural_contact_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_structural_contact_gate_passes_when_broader_categories_have_direct_evidence(tmp_path: Path) -> None:
    contact_path = tmp_path / "contact_readiness_report.json"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    rule_engine_path = tmp_path / "kds_rc_rule_engine.py"
    special_link_path = tmp_path / "special_link_library.py"
    validation_path = tmp_path / "structural_contact_validation_report.json"
    out_path = tmp_path / "structural_contact_gate_report.json"

    _write_json(
        contact_path,
        {
            "contract_pass": True,
            "coverage_scope": "wheel_rail_hertzian_contact_only",
            "summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | structural_contact=tracked_gap",
        },
    )
    _write_text(roadmap_path, "- roadmap refreshed; broader structural contact gap closed")
    _write_text(
        rule_engine_path,
        "\n".join(
            [
                "CLAUSE_MAP = {",
                "    'foundation:bearing': 'KDS-RC-FOUND-BEAR-001',",
                "    'connection:shear_friction': 'KDS-RC-CONN-SHEAR-001',",
                "}",
            ]
        ),
    )
    _write_text(
        special_link_path,
        "\n".join(
            [
                '"""gap uplift compression-only bearing friction pounding"""',
                "SUPPORTED_LINKS = ['gap', 'uplift', 'compression-only', 'bearing', 'friction', 'pounding']",
            ]
        ),
    )
    _write_json(
        validation_path,
        {
            "summary": {
                "contact_uplift_event_sequence_mismatch": 0,
                "foundation_support_model_types": ["p-y", "q-z"],
                "device_model_types": ["friction_pendulum"],
                "support_search_model_types": [
                    "p-y",
                    "q-z",
                ],
                "node_to_surface_proxy_model_types": [
                    "p-y",
                ],
                "contact_search_surface_types": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "search_surface_mode_counts": {
                    "node_to_soil_surface_proxy": 1,
                },
                "search_family_counts": {
                    "foundation_support_search": 2,
                },
                "support_search_family_types": ["foundation_support_search"],
                "node_to_surface_proxy_family_types": ["foundation_support_search"],
                "search_ready_group_counts": {
                    "contact": 6,
                    "support_ready": 2,
                    "node_to_surface_proxy": 1,
                },
                "support_depth_score": 3,
            },
            "categories": {
                "gap": {"validated": True},
                "uplift": {"validated": True},
                "compression_only": {"validated": True},
                "bearing": {"validated": True},
                "friction": {"validated": True},
                "pounding": {"validated": True},
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contact-readiness-report",
            str(contact_path),
            "--roadmap",
            str(roadmap_path),
            "--kds-rc-rule-engine",
            str(rule_engine_path),
            "--special-link-library",
            str(special_link_path),
            "--structural-contact-validation-report",
            str(validation_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["bounded_contact_evidence_pass"] is True
    assert payload["checks"]["special_link_categories_present"] is True
    assert payload["checks"]["structural_contact_event_sequence_zero_pass"] is True
    assert payload["checks"]["all_structural_contact_categories_ready"] is True
    assert payload["checks"]["foundation_support_surface_present"] is True
    assert payload["checks"]["device_model_surface_present"] is True
    assert payload["checks"]["contact_search_surface_present"] is True
    assert payload["checks"]["contact_family_surface_present"] is True
    assert payload["checks"]["support_search_surface_present"] is True
    assert payload["checks"]["support_search_family_surface_present"] is True
    assert payload["checks"]["node_to_surface_proxy_surface_present"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_present"] is True
    assert payload["checks"]["support_depth_surface_present"] is True
    assert payload["summary_line"].startswith("Structural contact readiness: PASS")
    assert "ready=6/6" in payload["summary_line"]
    assert "support=contact:6,foundation:4,device:5" in payload["summary_line"]
    assert "support_search=9" in payload["summary_line"]
    assert "node_surface_proxy=5" in payload["summary_line"]
    assert "support_depth=21" in payload["summary_line"]
    assert "support_families=2" in payload["summary_line"]
    assert "proxy_families=2" in payload["summary_line"]
    assert "missing=none" in payload["summary_line"]


def test_structural_contact_gate_reports_gap_when_only_partial_design_rule_evidence_exists(tmp_path: Path) -> None:
    contact_path = tmp_path / "contact_readiness_report.json"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    rule_engine_path = tmp_path / "kds_rc_rule_engine.py"
    special_link_path = tmp_path / "special_link_library.py"
    validation_path = tmp_path / "structural_contact_validation_report.json"
    out_path = tmp_path / "structural_contact_gate_report.json"

    _write_json(
        contact_path,
        {
            "contract_pass": True,
            "coverage_scope": "wheel_rail_hertzian_contact_only",
            "summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | structural_contact=tracked_gap",
        },
    )
    _write_text(
        roadmap_path,
        "\n".join(
            [
                "- contact / gap / uplift / compression-only 계열 부족",
                "- gap, uplift, bearing, isolator, friction, pounding",
                "- contact / uplift event sequence mismatch `0`",
            ]
        ),
    )
    _write_text(
        rule_engine_path,
        "\n".join(
            [
                "CLAUSE_MAP = {",
                "    'foundation:bearing': 'KDS-RC-FOUND-BEAR-001',",
                "    'connection:shear_friction': 'KDS-RC-CONN-SHEAR-001',",
                "}",
            ]
        ),
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contact-readiness-report",
            str(contact_path),
            "--roadmap",
            str(roadmap_path),
            "--kds-rc-rule-engine",
            str(rule_engine_path),
            "--special-link-library",
            str(special_link_path),
            "--structural-contact-validation-report",
            str(validation_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_STRUCTURAL_CONTACT_IMPLEMENTATION_MISSING"
    assert payload["checks"]["bounded_contact_evidence_pass"] is True
    assert payload["checks"]["bearing_design_rule_present"] is True
    assert payload["checks"]["friction_design_rule_present"] is True
    assert payload["checks"]["special_link_library_present"] is False
    assert payload["checks"]["special_link_categories_present"] is False
    assert payload["checks"]["all_structural_contact_categories_ready"] is False
    assert payload["summary_line"].startswith("Structural contact readiness: GAP")
    assert "partial_only=bearing,friction" in payload["summary_line"]


def test_structural_contact_gate_requires_upstream_bounded_contact_evidence(tmp_path: Path) -> None:
    contact_path = tmp_path / "contact_readiness_report.json"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    rule_engine_path = tmp_path / "kds_rc_rule_engine.py"
    special_link_path = tmp_path / "special_link_library.py"
    validation_path = tmp_path / "structural_contact_validation_report.json"
    out_path = tmp_path / "structural_contact_gate_report.json"

    _write_json(
        contact_path,
        {
            "contract_pass": False,
            "coverage_scope": "wheel_rail_hertzian_contact_only",
            "summary_line": "Contact readiness: GAP | scope=wheel_rail_hertzian_contact_only | structural_contact=tracked_gap",
        },
    )
    _write_text(roadmap_path, "- no-op")
    _write_text(rule_engine_path, "CLAUSE_MAP = {}")
    _write_text(
        special_link_path,
        "SUPPORTED_LINKS = ['gap', 'uplift', 'compression-only', 'bearing', 'friction', 'pounding']",
    )
    _write_json(
        validation_path,
        {
            "summary": {"contact_uplift_event_sequence_mismatch": 0},
            "categories": {
                "gap": {"validated": True},
                "uplift": {"validated": True},
                "compression_only": {"validated": True},
                "bearing": {"validated": True},
                "friction": {"validated": True},
                "pounding": {"validated": True},
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contact-readiness-report",
            str(contact_path),
            "--roadmap",
            str(roadmap_path),
            "--kds-rc-rule-engine",
            str(rule_engine_path),
            "--special-link-library",
            str(special_link_path),
            "--structural-contact-validation-report",
            str(validation_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_BOUNDED_CONTACT_EVIDENCE_FAIL"
    assert payload["checks"]["bounded_contact_evidence_pass"] is False
    assert payload["checks"]["special_link_categories_present"] is True
    assert payload["checks"]["structural_contact_validation_present"] is True


def test_structural_contact_gate_merges_partial_support_and_proxy_family_span_with_catalog(tmp_path: Path) -> None:
    contact_path = tmp_path / "contact_readiness_report.json"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    rule_engine_path = tmp_path / "kds_rc_rule_engine.py"
    special_link_path = tmp_path / "special_link_library.py"
    validation_path = tmp_path / "structural_contact_validation_report.json"
    out_path = tmp_path / "structural_contact_gate_report.json"

    _write_json(
        contact_path,
        {
            "contract_pass": True,
            "coverage_scope": "wheel_rail_hertzian_contact_only",
            "summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | structural_contact=tracked_gap",
        },
    )
    _write_text(roadmap_path, "- roadmap refreshed; broader structural contact gap closed")
    _write_text(rule_engine_path, "CLAUSE_MAP = {}")
    _write_text(
        special_link_path,
        "\n".join(
            [
                '"""gap uplift compression-only bearing friction pounding"""',
                "SUPPORTED_LINKS = ['gap', 'uplift', 'compression-only', 'bearing', 'friction', 'pounding']",
            ]
        ),
    )
    _write_json(
        validation_path,
        {
            "checks": {
                "support_search_surface_pass": True,
                "node_to_surface_proxy_pass": True,
            },
            "summary": {
                "contact_uplift_event_sequence_mismatch": 0,
                "contact_search_surface_types": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "contact_family_count": 6,
                "support_search_model_types": ["p-y", "pile_head", "q-z", "t-z"],
                "node_to_surface_proxy_model_types": ["p-y", "q-z", "t-z"],
                "support_search_family_types": ["foundation_support_search"],
                "node_to_surface_proxy_family_types": ["foundation_support_search"],
                "support_search_family_requirements": [
                    "device_support_search",
                    "foundation_support_search",
                ],
                "search_family_counts": {"foundation_support_search": 4},
                "support_depth_score": 11,
            },
            "categories": {
                "gap": {"validated": True},
                "uplift": {"validated": True},
                "compression_only": {"validated": True},
                "bearing": {"validated": True},
                "friction": {"validated": True},
                "pounding": {"validated": True},
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contact-readiness-report",
            str(contact_path),
            "--roadmap",
            str(roadmap_path),
            "--kds-rc-rule-engine",
            str(rule_engine_path),
            "--special-link-library",
            str(special_link_path),
            "--structural-contact-validation-report",
            str(validation_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["contact_family_surface_present"] is True
    assert payload["checks"]["support_search_family_surface_present"] is True
    assert payload["checks"]["node_to_surface_proxy_family_surface_present"] is True
    assert payload["support_surface_evidence"]["support_search_model_count"] == 9
    assert payload["support_surface_evidence"]["node_to_surface_proxy_count"] == 5
    assert payload["support_surface_evidence"]["support_depth_score"] == 21


def test_structural_contact_gate_ignores_stale_low_contact_family_count(tmp_path: Path) -> None:
    contact_path = tmp_path / "contact_readiness_report.json"
    roadmap_path = tmp_path / "commercial_tool_replacement_roadmap.md"
    rule_engine_path = tmp_path / "kds_rc_rule_engine.py"
    special_link_path = tmp_path / "special_link_library.py"
    validation_path = tmp_path / "structural_contact_validation_report.json"
    out_path = tmp_path / "structural_contact_gate_report.json"

    _write_json(
        contact_path,
        {
            "contract_pass": True,
            "coverage_scope": "wheel_rail_hertzian_contact_only",
            "summary_line": "Contact readiness: PASS | scope=wheel_rail_hertzian_contact_only | structural_contact=tracked_gap",
        },
    )
    _write_text(roadmap_path, "- roadmap refreshed; broader structural contact gap closed")
    _write_text(rule_engine_path, "CLAUSE_MAP = {}")
    _write_text(
        special_link_path,
        "\n".join(
            [
                '"""gap uplift compression-only bearing friction pounding"""',
                "SUPPORTED_LINKS = ['gap', 'uplift', 'compression-only', 'bearing', 'friction', 'pounding']",
            ]
        ),
    )
    _write_json(
        validation_path,
        {
            "summary": {
                "contact_uplift_event_sequence_mismatch": 0,
                "contact_family_count": 1,
                "contact_search_surface_types": [
                    "bearing_bilinear",
                    "compression_only_penalty",
                    "coulomb_friction",
                    "kelvin_voigt_pounding",
                    "normal_gap_unilateral",
                    "uplift_seat_unilateral",
                ],
                "search_ready_group_counts": {
                    "contact": 6,
                    "support_ready": 1,
                    "node_to_surface_proxy": 1,
                },
            },
            "categories": {
                "gap": {"validated": True},
                "uplift": {"validated": True},
                "compression_only": {"validated": True},
                "bearing": {"validated": True},
                "friction": {"validated": True},
                "pounding": {"validated": True},
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--contact-readiness-report",
            str(contact_path),
            "--roadmap",
            str(roadmap_path),
            "--kds-rc-rule-engine",
            str(rule_engine_path),
            "--special-link-library",
            str(special_link_path),
            "--structural-contact-validation-report",
            str(validation_path),
            "--out",
            str(out_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["checks"]["contact_family_surface_present"] is True
    assert payload["support_surface_evidence"]["contact_family_count"] == 6
    assert payload["support_surface_evidence"]["support_link_group_counts"]["contact"] == 6
