from implementation.phase1.generate_singlefile_optimization_history_viewer import (
    generate_singlefile_optimization_history_html,
)


def test_generate_singlefile_optimization_history_html_removes_sidecar_script() -> None:
    html = generate_singlefile_optimization_history_html(
        {
            "viewer_family": "optimization_history_viewer",
            "summary": {"title": "Optimization History"},
            "history": [{"iter": 0, "cost": 1.0, "dcr": 0.9, "penalty": 0.1, "modified": 0}],
        }
    )

    assert "./optimization_history.data.js" not in html
    assert "./design-theme.css" not in html
    assert "inlined from src/structure-viewer/design-theme.css" in html
    assert "window.__STRUCTURAL_SINGLEFILE__=true;" in html
    assert html.count("window.__STRUCTURAL_SINGLEFILE__=true;") == 1
    assert "IS_SINGLEFILE_VIEWER" in html
    assert "@import url(" not in html
    assert "fonts.googleapis" not in html
    assert "https://fonts" not in html
    assert 'body class="structural-surface history-command-shell"' in html
    assert 'class="companion-topbar"' in html
    assert 'class="companion-workspace history-workspace"' in html
    assert 'class="shell-nav-list"' in html
    assert 'class="chip chip-button"' in html
    assert 'class="container companion-canvas"' in html
    assert 'class="summary-bar companion-insight"' in html
    assert 'id="optimization-history-data"' in html
    assert '"viewer_family": "optimization_history_viewer"' in html
    assert "cdn.jsdelivr.net" not in html
    assert "unpkg.com" not in html
