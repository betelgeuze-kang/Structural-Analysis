from __future__ import annotations

from implementation.phase1.ui_layout_fragments import (
    render_card_title_block,
    render_link_pills,
    render_route_context_banner,
    render_section_heading,
    render_split_hero,
    render_token_row,
)


def test_render_route_context_banner_emits_shared_contract() -> None:
    html = render_route_context_banner()

    assert "route-context-banner" in html
    assert "Connected Review Route" in html
    assert "route-context-title" in html
    assert "route-context-step" in html
    assert "route-context-source" in html
    assert "route-context-target" in html
    assert "route-context-status" in html
    assert "route-context-note" in html
    assert "route-context-return" in html
    assert "../../../../index.html" in html
    assert "Structural Optimization Workbench" in html


def test_render_split_hero_wraps_main_and_side_content() -> None:
    html = render_split_hero(
        main_markup="<h1>Main</h1>",
        side_markup="<p>Side</p>",
        section_id="demo-hero",
        main_classes="card hero-main",
        side_classes="card hero-side",
    )

    assert "section" in html
    assert "demo-hero" in html
    assert "card hero-main" in html
    assert "card hero-side" in html
    assert "<h1>Main</h1>" in html
    assert "<p>Side</p>" in html


def test_render_token_row_supports_shared_classes_and_attrs() -> None:
    html = render_token_row(
        items=[
            "Primary",
            {"content": "Warn", "class_name": "is-warn", "attrs": {"data-tone": "warn"}},
        ],
        container_class="kpi-line",
        item_class="pill",
        container_attrs={"style": "margin-top:14px;"},
    )

    assert "class='kpi-line'" in html
    assert "style='margin-top:14px;'" in html
    assert "class='pill'" in html
    assert "class='pill is-warn'" in html
    assert "data-tone='warn'" in html
    assert ">Primary<" in html
    assert ">Warn<" in html


def test_render_section_heading_wraps_body_and_actions() -> None:
    html = render_section_heading(
        eyebrow="Navigator",
        title="Section Title",
        lead="Lead copy",
        actions_markup="<button>Jump</button>",
    )

    assert "class='section-heading'" in html
    assert "class='section-heading__body'" in html
    assert "class='section-heading__eyebrow'" in html
    assert "class='section-heading__title'" in html
    assert "class='section-heading__lead'" in html
    assert "class='section-heading__actions'" in html
    assert ">Navigator<" in html
    assert ">Section Title<" in html
    assert ">Lead copy<" in html
    assert "<button>Jump</button>" in html


def test_render_card_title_block_wraps_kicker_title_and_copy() -> None:
    html = render_card_title_block(
        kicker="Step 1",
        title="Open 3D",
        copy="Read structure first",
        actions_markup="<a>Go</a>",
    )

    assert "class='card-title-block'" in html
    assert "class='card-title-block__kicker'" in html
    assert "class='card-title-block__title'" in html
    assert "class='card-title-block__copy'" in html
    assert "class='card-title-block__actions'" in html
    assert ">Step 1<" in html
    assert ">Open 3D<" in html
    assert ">Read structure first<" in html
    assert "<a>Go</a>" in html


def test_render_link_pills_wraps_links_and_skips_empty_hrefs() -> None:
    html = render_link_pills(
        links=[
            ("Report", "report.html"),
            {
                "label": "Audit JSON",
                "href": "audit.json",
                "class_name": "is-secondary",
                "attrs": {"target": "_blank", "rel": "noopener"},
            },
            {"label": "Skip", "href": ""},
        ],
        container_class="link-row",
    )

    assert "class='link-row'" in html
    assert "href='report.html'" in html
    assert ">Report<" in html
    assert "class='link-pill is-secondary'" in html
    assert "href='audit.json'" in html
    assert "target='_blank'" in html
    assert "rel='noopener'" in html
    assert "Skip" not in html
