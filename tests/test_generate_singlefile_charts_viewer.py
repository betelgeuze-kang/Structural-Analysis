from implementation.phase1.generate_singlefile_charts_viewer import generate_singlefile_charts_html


def test_generate_singlefile_charts_html_inlines_payload_and_removes_sidecar() -> None:
    html = generate_singlefile_charts_html(
        {
            "generated_at": "2026-04-12T00:00:00+00:00",
            "source": "charts_singlefile_export",
            "results_explorer": {"time_history": []},
            "dynamic_time_history_report": {"generated_at": "2026-04-12T00:00:00+00:00"},
            "nonlinear_ndtha_stress_report": {"rows": []},
            "member_force_soft_accept_report": {"rows": []},
        }
    )

    assert "./charts.data.js" not in html
    assert "./design-theme.css" not in html
    assert "inlined from src/structure-viewer/design-theme.css" in html
    assert "window.__STRUCTURAL_SINGLEFILE__=true;" in html
    assert html.count("window.__STRUCTURAL_SINGLEFILE__=true;") == 1
    assert "IS_SINGLEFILE_VIEWER" in html
    assert "@import url(" not in html
    assert "fonts.googleapis" not in html
    assert "https://fonts" not in html
    assert 'body class="structural-surface charts-command-shell"' in html
    assert 'class="companion-topbar"' in html
    assert 'class="companion-workspace"' in html
    assert 'class="tabs"' in html
    assert 'class="shell-nav-list"' in html
    assert 'class="status-pill"' in html
    assert 'class="companion-canvas"' in html
    assert 'class="companion-insight"' in html
    assert 'data-rail-tab-key="timeseries"' in html
    assert "setActiveChartShellTab" in html
    assert 'id="charts-artifact-data"' in html
    assert html.index('id="charts-artifact-data"') < html.index("const ARTIFACT_PATHS=")
    assert '"source": "charts_singlefile_export"' in html
    assert "cdn.jsdelivr.net" not in html
    assert "unpkg.com" not in html
