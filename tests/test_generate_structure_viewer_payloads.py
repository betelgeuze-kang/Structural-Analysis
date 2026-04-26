from implementation.phase1.generate_structure_viewer_payloads import (
    build_index_preset_payloads,
    build_payloads,
    generate_panel_zone_singlefile_html,
)


def test_build_payloads_exposes_expected_viewer_keys() -> None:
    payloads = build_payloads()

    assert set(payloads) == {"index", "charts", "optimization_history", "panel_zone"}
    assert "interactive_3d" in payloads["index"]
    assert "results_explorer" in payloads["charts"]
    assert "member_force_soft_accept_report" in payloads["charts"]
    assert "member_force_station_source" in payloads["charts"]
    assert "smoke_history" in payloads["optimization_history"]
    assert "clash_artifact" in payloads["panel_zone"]
    assert "clash_verification" in payloads["panel_zone"]
    assert "row_provenance_lookup" in payloads["panel_zone"]
    station_source = payloads["charts"]["member_force_station_source"]
    assert station_source["authoritative_raw_station_source_available"] is True
    assert station_source["authoritative_raw_station_source_used"] is True
    assert station_source["candidate_station_header_count"] > 0
    row = payloads["charts"]["member_force_soft_accept_report"]["rows"][0]
    assert row["member_id"].startswith("MF-")
    assert row["distribution_chart"]["source_mode"] == "authoritative_raw_station_profile"
    assert row["distribution_chart"]["authoritative_raw_station_source_available"] is True
    assert len(row["distribution_chart"]["series"]) == 10


def test_build_index_preset_payloads_exposes_midas33_raw_model() -> None:
    presets = build_index_preset_payloads()

    assert "midas33" in presets
    assert "midas33_pr" in presets
    assert "midas33_optimized" in presets
    assert presets["midas33"]["report_name"] == "midas_generator_33.json"
    assert presets["midas33"]["path"].endswith("implementation/phase1/open_data/midas/midas_generator_33.json")
    assert presets["midas33_pr"]["report_name"] == "midas_generator_33.pr_recheck.json"
    assert presets["midas33_optimized"]["report_name"] == "midas_generator_33.optimized.roundtrip.json"
    payload = presets["midas33"]["payload"]
    assert "model" in payload
    assert len(payload["model"]["nodes"]) > 1000
    assert len(payload["model"]["elements"]) > 1000


def test_generate_panel_zone_singlefile_html_inlines_payload_and_vendor_modules() -> None:
    payloads = build_payloads()

    html = generate_panel_zone_singlefile_html(payloads["panel_zone"])

    assert 'id="embedded-panel-zone-payload"' in html
    assert "./design-theme.css" not in html
    assert "inlined from src/structure-viewer/design-theme.css" in html
    assert "window.__STRUCTURAL_SINGLEFILE__=true;" in html
    assert 'body class="structural-surface panel-inspection-shell"' in html
    assert "data:text/javascript;base64," in html
    assert "./panel_zone.data.js" not in html
    assert "./vendor/three.module.js" not in html
    assert "./vendor/OrbitControls.js" not in html
