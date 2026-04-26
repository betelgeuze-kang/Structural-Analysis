#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.ui_design_tokens import build_signal_desk_dark_css
except ImportError:  # pragma: no cover - direct script execution fallback
    from ui_design_tokens import build_signal_desk_dark_css
try:
    from implementation.phase1.ui_layout_fragments import (
        render_link_pills,
        render_section_heading,
        render_route_context_banner,
        render_split_hero,
        render_token_row,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from ui_layout_fragments import (
        render_link_pills,
        render_section_heading,
        render_route_context_banner,
        render_split_hero,
        render_token_row,
    )


DEFAULT_MANIFEST = Path("implementation/phase1/output/benchmark_svg/benchmark_optimization_drawings_manifest.json")
DEFAULT_OUT_HTML = Path("implementation/phase1/release/visualization/benchmark_optimization_review.html")
DEFAULT_OUT_SUMMARY = Path("implementation/phase1/release/visualization/benchmark_optimization_review_summary.json")
DEFAULT_OPTIMIZED_DRAWING_REVIEW_HTML = Path("implementation/phase1/release/visualization/optimized_drawing_review.html")
DEFAULT_STRUCTURAL_OPTIMIZATION_VIEWER_HTML = Path("implementation/phase1/release/visualization/structural_optimization_viewer.html")
DEFAULT_COMMITTEE_DASHBOARD_HTML = Path("implementation/phase1/release/committee_review/committee_review_dashboard.html")
DEFAULT_RELEASE_GAP_REPORT_JSON = Path("implementation/phase1/release/release_gap_report.json")
DEFAULT_PROJECT_REGISTRY_JSON = Path("implementation/phase1/release/project_registry.json")
DEFAULT_PROJECT_PACKAGE_ZIP = Path("implementation/phase1/release/project_package.zip")
DEFAULT_PROJECT_REGISTRY_SIGNATURE = Path("implementation/phase1/release/signing/project_registry.signature.b64")
DEFAULT_BATCH_JOB_REPORT_JSON = Path(
    "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_batch_job_report.json"
)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _rel_href(target: Path, *, base_dir: Path) -> str:
    resolved_target = target.resolve() if target.is_absolute() else (Path.cwd() / target).resolve()
    return os.path.relpath(resolved_target, start=base_dir.resolve()).replace(os.sep, "/")


def _safe_rel_href(target: Path, *, base_dir: Path) -> str:
    try:
        return _rel_href(target, base_dir=base_dir)
    except Exception:
        return Path(target).as_posix()


def _projection_files(directory: Path, *, family: str) -> list[str]:
    if not directory.exists():
        return []
    preferred_by_family = {
        "canton": [
            "detail_story_change_register.svg",
            "detail_zone_cluster.svg",
            "detail_floor_stack.svg",
            "detail_member_zoom.svg",
            "detail_family.svg",
            "isometric.svg",
            "elevation_xz.svg",
            "elevation_yz.svg",
        ],
        "peer": [
            "detail_section.svg",
            "detail_rebar_callout.svg",
            "detail_bar_bending_schedule.svg",
            "detail_anchorage_cut.svg",
            "detail_anchorage_exploded.svg",
            "detail_schedule.svg",
            "isometric.svg",
            "elevation_xz.svg",
            "elevation_yz.svg",
        ],
    }
    preferred = preferred_by_family.get(family, [])
    plans = sorted([path.name for path in directory.glob("plan_*.svg")])
    out = [name for name in preferred if (directory / name).exists()]
    out.extend(plans)
    return out


def _pick_initial_projection(names: list[str], *, family: str) -> str:
    if not names:
        return ""
    family_defaults = {
        "canton": [
            "detail_story_change_register.svg",
            "detail_floor_stack.svg",
            "detail_zone_cluster.svg",
            "detail_member_zoom.svg",
            "isometric.svg",
        ],
        "peer": [
            "detail_section.svg",
            "detail_rebar_callout.svg",
            "detail_bar_bending_schedule.svg",
            "detail_anchorage_exploded.svg",
            "isometric.svg",
        ],
    }
    for candidate in family_defaults.get(family, []):
        if candidate in names:
            return candidate
    return names[0]


def _proposal_change_markup(summary: dict[str, Any]) -> str:
    proposed_changes = summary.get("proposed_changes") if isinstance(summary.get("proposed_changes"), list) else []
    return "".join(
        "<li>"
        f"<strong>{html.escape(str(row.get('action', '') or '').strip().title())}</strong> "
        f"{html.escape(str(row.get('group', '') or '').strip())} "
        f"<span>{html.escape(str(row.get('from_section', '') or '').strip())} → {html.escape(str(row.get('to_section', '') or '').strip())}</span> "
        f"<em>D/C {float(row.get('baseline_dcr', 0.0) or 0.0):.2f} → {float(row.get('optimized_dcr', 0.0) or 0.0):.2f}</em>"
        "</li>"
        for row in proposed_changes[:10]
        if isinstance(row, dict)
    )


def build_review_html(*, manifest: dict[str, Any], manifest_path: Path, out_html: Path) -> str:
    out_dir = out_html.parent
    canton = manifest.get("canton_tower_reduced_shm") if isinstance(manifest.get("canton_tower_reduced_shm"), dict) else {}
    peer = manifest.get("peer_blind_prediction") if isinstance(manifest.get("peer_blind_prediction"), dict) else {}

    baseline_dir = Path(str(canton.get("baseline_review_output_dir") or canton.get("baseline_output_dir", "") or ""))
    optimized_dir = Path(str(canton.get("ai_optimized_review_output_dir") or canton.get("ai_optimized_output_dir", "") or ""))
    baseline_summary = canton.get("baseline_summary") if isinstance(canton.get("baseline_summary"), dict) else {}
    optimized_summary = canton.get("ai_optimized_summary") if isinstance(canton.get("ai_optimized_summary"), dict) else {}
    peer_baseline_dir = Path(str(peer.get("baseline_review_output_dir") or peer.get("baseline_output_dir", "") or ""))
    peer_optimized_dir = Path(str(peer.get("ai_optimized_review_output_dir") or peer.get("ai_optimized_output_dir", "") or ""))
    peer_baseline_summary = peer.get("baseline_summary") if isinstance(peer.get("baseline_summary"), dict) else {}
    peer_optimized_summary = peer.get("ai_optimized_summary") if isinstance(peer.get("ai_optimized_summary"), dict) else {}
    peer_sheet = (
        (peer.get("readiness_sheet") or {}).get("sheet_path", "")
        if isinstance(peer.get("readiness_sheet"), dict)
        else ""
    )

    projection_names = _projection_files(baseline_dir, family="canton") or _projection_files(optimized_dir, family="canton")
    peer_projection_names = _projection_files(peer_baseline_dir, family="peer") or _projection_files(peer_optimized_dir, family="peer")
    initial_projection = _pick_initial_projection(projection_names, family="canton")
    peer_initial_projection = _pick_initial_projection(peer_projection_names, family="peer")
    projection_options = "".join(
        f"<option value='{html.escape(name, quote=True)}'{' selected' if name == initial_projection else ''}>{html.escape(name)}</option>"
        for name in projection_names
    )
    peer_projection_options = "".join(
        f"<option value='{html.escape(name, quote=True)}'{' selected' if name == peer_initial_projection else ''}>{html.escape(name)}</option>"
        for name in peer_projection_names
    )
    baseline_hrefs = {name: _safe_rel_href((baseline_dir / name), base_dir=out_dir) for name in projection_names}
    optimized_hrefs = {name: _safe_rel_href((optimized_dir / name), base_dir=out_dir) for name in projection_names}
    peer_baseline_hrefs = {name: _safe_rel_href((peer_baseline_dir / name), base_dir=out_dir) for name in peer_projection_names}
    peer_optimized_hrefs = {name: _safe_rel_href((peer_optimized_dir / name), base_dir=out_dir) for name in peer_projection_names}
    peer_sheet_href = _safe_rel_href(Path(peer_sheet), base_dir=out_dir) if peer_sheet else ""

    initial_baseline = baseline_hrefs.get(initial_projection, "")
    initial_optimized = optimized_hrefs.get(initial_projection, "")
    peer_initial_baseline = peer_baseline_hrefs.get(peer_initial_projection, "")
    peer_initial_optimized = peer_optimized_hrefs.get(peer_initial_projection, "")

    change_markup = _proposal_change_markup(optimized_summary)
    peer_change_markup = _proposal_change_markup(peer_optimized_summary)

    baseline_json = json.dumps(baseline_hrefs, ensure_ascii=False)
    optimized_json = json.dumps(optimized_hrefs, ensure_ascii=False)
    peer_baseline_json = json.dumps(peer_baseline_hrefs, ensure_ascii=False)
    peer_optimized_json = json.dumps(peer_optimized_hrefs, ensure_ascii=False)
    manifest_href = _safe_rel_href(manifest_path, base_dir=out_dir)
    optimized_drawing_review_href = _safe_rel_href(DEFAULT_OPTIMIZED_DRAWING_REVIEW_HTML, base_dir=out_dir)
    structural_optimization_viewer_href = _safe_rel_href(
        DEFAULT_STRUCTURAL_OPTIMIZATION_VIEWER_HTML,
        base_dir=out_dir,
    )
    committee_dashboard_href = _safe_rel_href(DEFAULT_COMMITTEE_DASHBOARD_HTML, base_dir=out_dir)
    release_gap_report_href = _safe_rel_href(DEFAULT_RELEASE_GAP_REPORT_JSON, base_dir=out_dir)
    project_registry_href = _safe_rel_href(DEFAULT_PROJECT_REGISTRY_JSON, base_dir=out_dir)
    project_package_href = _safe_rel_href(DEFAULT_PROJECT_PACKAGE_ZIP, base_dir=out_dir)
    project_registry_signature_href = _safe_rel_href(DEFAULT_PROJECT_REGISTRY_SIGNATURE, base_dir=out_dir)
    batch_job_report_href = _safe_rel_href(DEFAULT_BATCH_JOB_REPORT_JSON, base_dir=out_dir)
    hero_meta_markup = render_token_row(
        items=[
            f"Canton case: {html.escape(str(canton.get('selected_case_id', '') or 'n/a'))}",
            f"Changed proposals: {int(optimized_summary.get('proposed_change_count', 0) or 0)}",
            {"content": f"Manifest: <a href='{html.escape(manifest_href, quote=True)}'>JSON</a>"},
        ],
        container_class="hero-meta",
        item_class="chip",
        quote="'",
    )
    toolbar_links_markup = render_link_pills(
        links=[
            ("Open MIDAS33 optimized drawing review", optimized_drawing_review_href),
            ("Open results explorer", structural_optimization_viewer_href),
            ("Open committee dashboard", committee_dashboard_href),
            ("Open validation boundary", release_gap_report_href),
            ("Open project registry", project_registry_href),
            ("Open project package zip", project_package_href),
            ("Open registry signature", project_registry_signature_href),
            ("Open batch job report", batch_job_report_href),
        ],
        link_class="toolbar-link",
        container_class="toolbar-actions",
        quote="'",
    )
    canton_heading_markup = render_section_heading(
        eyebrow="Benchmark Lane",
        title="Canton Tower Reduced-Order Review",
        lead=(
            "Measured-window demand ranking 기반 proxy drawing을 baseline / AI optimized lane으로 나란히 검토합니다. "
            "Projection 교체와 요약 수치를 같은 시야 안에서 유지해 위원회 검토 흐름이 끊기지 않도록 구성합니다."
        ),
        actions_markup=render_token_row(
            items=[
                f"Case {html.escape(str(canton.get('selected_case_id', '') or 'n/a'))}",
                f"Views {len(projection_names)}",
                f"Changes {int(optimized_summary.get('proposed_change_count', 0) or 0)}",
            ],
            container_class="section-token-row",
            item_class="pill",
            quote="'",
        ),
        shell_class="section-heading",
        body_class="section-heading__body",
        eyebrow_class="section-heading__eyebrow",
        title_class="section-heading__title",
        lead_class="section-heading__lead",
        actions_class="section-heading__actions",
        quote="'",
    )
    peer_heading_markup = render_section_heading(
        eyebrow="Blind Benchmark",
        title="PEER Blind Prediction Review",
        lead=(
            "문서근거형 bridge bent proxy geometry를 baseline / AI optimized sheet로 비교하고, "
            "readiness 근거와 geometry provenance를 같은 review family 안에서 이어서 확인합니다."
        ),
        actions_markup=render_token_row(
            items=[
                f"Case {html.escape(str(peer.get('selected_case_id', '') or 'n/a'))}",
                f"Views {len(peer_projection_names)}",
                f"Changes {int(peer_optimized_summary.get('proposed_change_count', 0) or 0)}",
            ],
            container_class="section-token-row",
            item_class="pill",
            quote="'",
        ),
        shell_class="section-heading",
        body_class="section-heading__body",
        eyebrow_class="section-heading__eyebrow",
        title_class="section-heading__title",
        lead_class="section-heading__lead",
        actions_class="section-heading__actions",
        quote="'",
    )
    peer_sheet_heading_markup = render_section_heading(
        eyebrow="Readiness Sheet",
        title="PEER Blind Prediction Readiness Evidence",
        lead=(
            "공식 compare lane과 함께, 원본 bundle / geometry provenance / normalize 상태를 같은 evidence desk에서 "
            "연속적으로 볼 수 있게 readiness sheet를 별도 panel로 유지합니다."
        ),
        actions_markup=render_token_row(
            items=[
                f"Geometry basis {html.escape(str(peer_optimized_summary.get('geometry_provenance_label', '') or 'n/a'))}",
                f"Detail layers {html.escape(', '.join(f'{k}={v}' for k, v in ((peer_optimized_summary.get('detail_layers') or {}).items())) or 'n/a')}",
            ],
            container_class="section-token-row",
            item_class="pill",
            quote="'",
        ),
        shell_class="section-heading",
        body_class="section-heading__body",
        eyebrow_class="section-heading__eyebrow",
        title_class="section-heading__title",
        lead_class="section-heading__lead",
        actions_class="section-heading__actions",
        quote="'",
    )
    route_context_banner_markup = render_route_context_banner(quote="'")
    hero_markup = render_split_hero(
        section_id="benchmark-hero",
        main_classes="card hero-main",
        side_classes="card hero-side",
        main_markup=f"""        <h1>Benchmark Optimization Review</h1>
        <p>midas33 최적화 도면처럼, 벤치마크 구조물도 HTML에서 바로 비교할 수 있게 baseline / AI optimized 도면을 묶었습니다. Canton Tower와 PEER blind benchmark 둘 다 HTML 안에서 baseline / AI optimized 비교가 가능하고, PEER는 readiness sheet도 같이 제공합니다.</p>
        {hero_meta_markup}""",
        side_markup="""        <h2>AI Optimization Notes</h2>
        <ul>
          <li>Canton Tower는 measured-window demand ranking 기반 reduced-order proxy 도면입니다.</li>
          <li>PEER blind benchmark는 공식 drawing PDF에서 추출한 문서근거형 bridge bent proxy geometry를 baseline / AI optimized sheet로 제공합니다.</li>
          <li>이 페이지는 baseline/optimized SVG를 `HTML에서 바로 넘겨보는` benchmark review surface입니다.</li>
        </ul>""",
        quote="'",
    )

    return f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Benchmark Optimization Review</title>
<style>
{build_signal_desk_dark_css()}
:root {{
  --panel-2:#1a2a3d;
  --frame-bg:#081018;
  --frame-line:rgba(150,168,187,.18);
  --shell-shadow:0 22px 48px rgba(0,0,0,.24);
  --soft-glow:rgba(79,183,173,.16);
}}
*{{box-sizing:border-box}}
body{{margin:0}}
a{{color:inherit}}
.page{{max-width:1720px;margin:0 auto;padding:28px 22px 40px}}
.route-focus-target{{outline:3px solid rgba(79,183,173,.42);outline-offset:6px;border-radius:18px;animation:routeFocusPulse 1.8s ease-out 1}}
.route-selection-target{{box-shadow:0 0 0 3px rgba(79,183,173,.24);animation:routeSelectionPulse 1.8s ease-out 1}}
@keyframes routeFocusPulse{{0%{{box-shadow:0 0 0 0 rgba(79,183,173,.30)}}100%{{box-shadow:0 0 0 18px rgba(79,183,173,0)}}}}
@keyframes routeSelectionPulse{{0%{{box-shadow:0 0 0 0 rgba(79,183,173,.24)}}100%{{box-shadow:0 0 0 14px rgba(79,183,173,0)}}}}
.hero{{display:grid;grid-template-columns:1.2fr .8fr;gap:18px;margin-bottom:18px}}
.card{{background:linear-gradient(180deg,#111c29 0%,#152435 100%);border:1px solid var(--line);border-radius:24px;box-shadow:var(--shell-shadow)}}
.hero-main{{padding:28px;border:1px solid rgba(79,183,173,.18);background:
  radial-gradient(circle at 14% 12%, rgba(244,181,107,.18), transparent 24%),
  linear-gradient(135deg,#0e2533 0%,#113b4b 38%,#0f6a73 76%,#4fb7ad 100%)}}
.hero-main h1{{margin:0 0 10px;font-size:42px;line-height:1.03;letter-spacing:-.04em}}
.hero-main p{{margin:0;color:rgba(236,242,246,.86);line-height:1.7;max-width:78ch}}
.hero-meta{{margin-top:16px;display:flex;flex-wrap:wrap;gap:10px}}
.chip{{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;border-radius:999px;font-size:12px;font-weight:700}}
.hero-side{{padding:24px;position:relative;overflow:hidden}}
.hero-side::before{{content:'';position:absolute;inset:auto -10% 0 auto;width:180px;height:180px;border-radius:50%;background:radial-gradient(circle, rgba(244,181,107,.16), transparent 70%);pointer-events:none}}
.hero-side h2{{margin:0 0 12px;font-size:18px;color:var(--text)}}
.hero-side ul{{margin:0;padding-left:18px;color:var(--muted);line-height:1.7}}
.hero-side li + li{{margin-top:8px}}
.toolbar{{display:grid;grid-template-columns:repeat(2,minmax(220px,max-content)) 1fr;gap:12px 16px;align-items:start;padding:18px 20px;margin-bottom:24px}}
.toolbar-actions{{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end;align-self:center}}
.toolbar-link{{display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:999px;border:1px solid rgba(79,183,173,.2);background:linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));font-size:12px;font-weight:700;text-decoration:none;transition:transform 160ms ease,border-color 160ms ease,box-shadow 160ms ease}}
.toolbar-link:hover{{transform:translateY(-1px);border-color:rgba(244,181,107,.4);box-shadow:0 12px 22px rgba(0,0,0,.14)}}
.field{{display:flex;flex-direction:column;gap:8px;min-width:220px}}
.field label{{font-size:11px;color:var(--muted);font-weight:700;letter-spacing:.12em;text-transform:uppercase}}
.field select{{background:rgba(21,36,53,.92);color:var(--ink);border:1px solid var(--line);border-radius:14px;padding:11px 12px;font-size:13px;font-weight:600;box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}}
.section-heading{{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin:0 0 14px}}
.section-heading__body{{max-width:880px}}
.section-heading__eyebrow{{color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}}
.section-heading__title{{margin:8px 0 6px;font-size:28px;line-height:1.08;color:var(--text)}}
.section-heading__lead{{margin:0;color:var(--muted);line-height:1.7;font-size:14px}}
.section-heading__actions{{display:flex;justify-content:flex-end}}
.section-token-row{{display:flex;flex-wrap:wrap;gap:8px;justify-content:flex-end}}
.comparison-section + .comparison-section{{margin-top:26px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.grid-narrow{{grid-template-columns:repeat(2,minmax(300px,520px));justify-content:center}}
.panel{{padding:16px}}
.panel-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:12px}}
.panel-kicker{{font-size:11px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}}
.panel h3{{margin:0;font-size:17px;line-height:1.25;color:var(--text)}}
.panel-meta{{max-width:220px;color:var(--muted);font-size:12px;line-height:1.5;text-align:right}}
.frame-shell{{padding:12px;border-radius:18px;border:1px solid var(--frame-line);background:
  radial-gradient(circle at top right, var(--soft-glow), transparent 34%),
  linear-gradient(180deg, rgba(8,16,24,.98) 0%, rgba(13,24,36,.98) 100%)}}
.frame{{height:780px;border-radius:14px;overflow:hidden;border:1px solid rgba(255,255,255,.06);background:var(--frame-bg)}}
.frame-canton{{height:920px}}
.frame-peer{{height:720px}}
.frame object{{width:100%;height:100%;border:0;background:white}}
.summary{{margin-top:18px;display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.summary-card{{padding:18px 20px;position:relative;overflow:hidden}}
.summary-card::before{{content:'';position:absolute;inset:0 auto auto 0;width:100%;height:1px;background:linear-gradient(90deg, rgba(79,183,173,.42), rgba(244,181,107,0));pointer-events:none}}
.summary-card h4{{margin:0 0 10px;font-size:16px;color:var(--text)}}
.summary-card dl{{display:grid;grid-template-columns:max-content 1fr;gap:8px 12px;margin:0}}
.summary-card dt{{color:var(--muted)}}
.summary-card dd{{margin:0;font-weight:700}}
.summary-card ul{{margin:12px 0 0;padding-left:18px;line-height:1.7;color:var(--muted)}}
.summary-card li + li{{margin-top:8px}}
.summary-card em{{color:rgba(244,181,107,.94);font-style:normal}}
.summary-card strong{{color:var(--text)}}
.peer-sheet{{margin-top:18px;padding:16px}}
.peer-sheet .frame{{height:720px}}
.readiness-note{{color:var(--muted);margin:0 0 12px;line-height:1.7}}
@media (max-width: 1200px) {{
  .hero,.grid,.summary{{grid-template-columns:1fr}}
  .toolbar{{grid-template-columns:1fr}}
  .toolbar-actions,.section-heading__actions,.section-token-row{{justify-content:flex-start}}
  .section-heading{{flex-direction:column;align-items:stretch}}
}}
</style>
</head>
<body class='signal-desk-dark'>
  <div class='page'>
    {route_context_banner_markup}
    {hero_markup}

    <section class='card toolbar' id='benchmark-toolbar'>
      <div class='field'>
        <label for='projection'>Canton Projection</label>
        <select id='projection'>{projection_options}</select>
      </div>
      <div class='field'>
        <label for='peer-projection'>PEER Projection</label>
        <select id='peer-projection'>{peer_projection_options}</select>
      </div>
      {toolbar_links_markup}
    </section>

    <section class='comparison-section'>
      {canton_heading_markup}
      <section class='grid grid-narrow' id='canton-review' data-route-benchmark-family='canton' data-route-case-id='{html.escape(str(canton.get("selected_case_id", "") or ""), quote=True)}'>
        <div class='card panel'>
          <div class='panel-head'>
            <div>
              <div class='panel-kicker'>Baseline Lane</div>
              <h3>Canton Tower Baseline</h3>
            </div>
            <div class='panel-meta'>Original benchmark drawing lane for side-by-side audit.</div>
          </div>
          <div class='frame-shell'><div class='frame frame-canton'><object id='baseline-frame' type='image/svg+xml' data='{html.escape(initial_baseline, quote=True)}'></object></div></div>
        </div>
        <div class='card panel'>
          <div class='panel-head'>
            <div>
              <div class='panel-kicker'>AI Optimized Lane</div>
              <h3>Canton Tower AI Optimized</h3>
            </div>
            <div class='panel-meta'>Same projection lane with proposal-ready optimized sheet.</div>
          </div>
          <div class='frame-shell'><div class='frame frame-canton'><object id='optimized-frame' type='image/svg+xml' data='{html.escape(initial_optimized, quote=True)}'></object></div></div>
        </div>
      </section>

      <section class='summary' id='benchmark-canton-summary' data-route-benchmark-family='canton' data-route-case-id='{html.escape(str(canton.get("selected_case_id", "") or ""), quote=True)}'>
        <div class='card summary-card'>
          <div class='panel-kicker'>Baseline Evidence</div>
        <h4>Baseline Summary</h4>
        <dl>
          <dt>Case</dt><dd>{html.escape(str(baseline_summary.get('case_id', '') or 'n/a'))}</dd>
          <dt>Topology</dt><dd>{html.escape(str(baseline_summary.get('topology_type', '') or 'n/a'))}</dd>
          <dt>Element mix</dt><dd>{html.escape(str(baseline_summary.get('element_mix', '') or 'n/a'))}</dd>
          <dt>Nodes</dt><dd>{int(baseline_summary.get('node_count', 0) or 0)}</dd>
          <dt>Elements</dt><dd>{int(baseline_summary.get('element_count', 0) or 0)}</dd>
          <dt>Drift</dt><dd>{float(baseline_summary.get('drift_ratio_pct', 0.0) or 0.0):.3f}%</dd>
        </dl>
        </div>
        <div class='card summary-card'>
          <div class='panel-kicker'>Optimized Evidence</div>
        <h4>AI Optimized Summary</h4>
        <dl>
          <dt>Case</dt><dd>{html.escape(str(optimized_summary.get('case_id', '') or 'n/a'))}</dd>
          <dt>Mode</dt><dd>{html.escape(str(optimized_summary.get('optimization_mode', '') or 'n/a'))}</dd>
          <dt>Proposals</dt><dd>{int(optimized_summary.get('proposed_change_count', 0) or 0)}</dd>
          <dt>Base shear</dt><dd>{float(optimized_summary.get('base_shear_kN', 0.0) or 0.0):.6f} kN</dd>
        </dl>
        <ul>{change_markup or "<li>No proposal rows were generated for this representative case.</li>"}</ul>
        </div>
      </section>
    </section>

    <section class='comparison-section'>
      {peer_heading_markup}
      <section class='grid' id='peer-benchmark' data-route-benchmark-family='peer' data-route-case-id='{html.escape(str(peer.get("selected_case_id", "") or ""), quote=True)}'>
        <div class='card panel'>
          <div class='panel-head'>
            <div>
              <div class='panel-kicker'>Baseline Lane</div>
              <h3>PEER Blind Prediction Baseline</h3>
            </div>
            <div class='panel-meta'>Document-derived baseline sheet for direct compare review.</div>
          </div>
          <div class='frame-shell'><div class='frame frame-peer'><object id='peer-baseline-frame' type='image/svg+xml' data='{html.escape(peer_initial_baseline, quote=True)}'></object></div></div>
        </div>
        <div class='card panel'>
          <div class='panel-head'>
            <div>
              <div class='panel-kicker'>AI Optimized Lane</div>
              <h3>PEER Blind Prediction AI Optimized</h3>
            </div>
            <div class='panel-meta'>Proposal-ready compare lane with geometry provenance continuity.</div>
          </div>
          <div class='frame-shell'><div class='frame frame-peer'><object id='peer-optimized-frame' type='image/svg+xml' data='{html.escape(peer_initial_optimized, quote=True)}'></object></div></div>
        </div>
      </section>

      <section class='summary' id='benchmark-peer-summary' data-route-benchmark-family='peer' data-route-case-id='{html.escape(str(peer.get("selected_case_id", "") or ""), quote=True)}'>
        <div class='card summary-card'>
          <div class='panel-kicker'>Baseline Evidence</div>
        <h4>PEER Baseline Summary</h4>
        <dl>
          <dt>Case</dt><dd>{html.escape(str(peer_baseline_summary.get('case_id', '') or 'n/a'))}</dd>
          <dt>Topology</dt><dd>{html.escape(str(peer_baseline_summary.get('topology_type', '') or 'n/a'))}</dd>
          <dt>Element mix</dt><dd>{html.escape(str(peer_baseline_summary.get('element_mix', '') or 'n/a'))}</dd>
          <dt>Channels</dt><dd>{int(peer_baseline_summary.get('acceleration_channel_count', 0) or 0)}/{int(peer_baseline_summary.get('drift_channel_count', 0) or 0)}</dd>
          <dt>Nodes</dt><dd>{int(peer_baseline_summary.get('node_count', 0) or 0)}</dd>
          <dt>Elements</dt><dd>{int(peer_baseline_summary.get('element_count', 0) or 0)}</dd>
        </dl>
        </div>
        <div class='card summary-card'>
          <div class='panel-kicker'>Optimized Evidence</div>
        <h4>PEER AI Optimized Summary</h4>
        <dl>
          <dt>Case</dt><dd>{html.escape(str(peer_optimized_summary.get('case_id', '') or 'n/a'))}</dd>
          <dt>Mode</dt><dd>{html.escape(str(peer_optimized_summary.get('optimization_mode', '') or 'n/a'))}</dd>
          <dt>Proposals</dt><dd>{int(peer_optimized_summary.get('proposed_change_count', 0) or 0)}</dd>
          <dt>Geometry basis</dt><dd>{html.escape(str(peer_optimized_summary.get('geometry_provenance_label', '') or 'n/a'))}</dd>
          <dt>Detail layers</dt><dd>{html.escape(", ".join(f"{k}={v}" for k, v in ((peer_optimized_summary.get('detail_layers') or {}).items())) or 'n/a')}</dd>
        </dl>
        <ul>{peer_change_markup or "<li>No proposal rows were generated for this PEER representative case.</li>"}</ul>
        </div>
      </section>
    </section>

    <section class='comparison-section'>
      {peer_sheet_heading_markup}
      <section class='card peer-sheet' id='benchmark-peer-sheet'>
        <p class='readiness-note'>공식 compare lane과 함께, 원본 bundle / geometry provenance / normalize 상태를 review sheet로 같이 둡니다.</p>
        <div class='frame-shell'><div class='frame'><object type='image/svg+xml' data='{html.escape(peer_sheet_href, quote=True)}'></object></div></div>
      </section>
    </section>
  </div>
<script>
const baselineMap = {baseline_json};
const optimizedMap = {optimized_json};
const peerBaselineMap = {peer_baseline_json};
const peerOptimizedMap = {peer_optimized_json};
const projection = document.getElementById('projection');
const peerProjection = document.getElementById('peer-projection');
const baselineFrame = document.getElementById('baseline-frame');
const optimizedFrame = document.getElementById('optimized-frame');
const peerBaselineFrame = document.getElementById('peer-baseline-frame');
const peerOptimizedFrame = document.getElementById('peer-optimized-frame');
projection.addEventListener('change', () => {{
  const key = projection.value;
  baselineFrame.data = baselineMap[key] || '';
  optimizedFrame.data = optimizedMap[key] || '';
}});
peerProjection.addEventListener('change', () => {{
  const key = peerProjection.value;
  peerBaselineFrame.data = peerBaselineMap[key] || '';
  peerOptimizedFrame.data = peerOptimizedMap[key] || '';
}});
</script>
<script>
(() => {{
  const params = new URL(window.location.href).searchParams;
  const title = String(params.get('route_title') || '').trim();
  const banner = document.getElementById('route-context-banner');
  if (!banner || !title) return;

  const renderText = (id, value) => {{
    const element = document.getElementById(id);
    if (!element) return;
    const text = String(value || '').trim();
    element.textContent = text;
    element.hidden = !text;
  }};

  const reviewMode = String(params.get('review_mode') || '').replace(/[_-]+/g, ' ').trim();
  const routeStep = String(params.get('route_step') || '').trim();
  const fromLabel = String(params.get('from_label') || '').trim();
  const targetLabel = String(params.get('target_label') || '').trim();
  const selectionStatus = String(params.get('selection_status') || '').trim();
  const sourceLabel = String(params.get('source_label') || '').trim();
  const targetSurface = String(params.get('target_surface') || '').trim();

  renderText('route-context-title', title);
  renderText('route-context-step', [routeStep ? `step ${{routeStep}}` : '', reviewMode].filter(Boolean).join(' | '));
  renderText('route-context-source', fromLabel ? `from ${{fromLabel}}` : '');
  renderText('route-context-target', targetLabel ? `target ${{targetLabel}}` : '');
  renderText('route-context-status', selectionStatus ? `selection ${{selectionStatus}}` : '');
  renderText(
    'route-context-note',
    [sourceLabel ? `snapshot ${{sourceLabel}}` : '', targetSurface ? `surface ${{targetSurface}}` : '']
      .filter(Boolean)
      .join(' | '),
  );

  const returnTo = String(params.get('return_to') || '').trim();
  const returnLabel = String(params.get('return_label') || 'Structural Optimization Workbench').trim();
  const returnLink = document.getElementById('route-context-return');
  if (returnLink && returnTo) {{
    returnLink.href = returnTo;
    returnLink.textContent = returnLabel;
    returnLink.hidden = false;
  }}

  banner.hidden = false;
  const routeFocusId = String(params.get('route_focus') || '').trim();
  const routeFocusTarget = routeFocusId ? document.getElementById(routeFocusId) : null;
  if (routeFocusTarget) {{
    window.requestAnimationFrame(() => {{
      routeFocusTarget.classList.add('route-focus-target');
      routeFocusTarget.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      window.setTimeout(() => routeFocusTarget.classList.remove('route-focus-target'), 2200);
    }});
  }}

  const flashRouteSelection = (node) => {{
    if (!node) return;
    window.requestAnimationFrame(() => {{
      node.classList.add('route-selection-target');
      node.scrollIntoView({{ behavior: 'smooth', block: 'center', inline: 'nearest' }});
      window.setTimeout(() => node.classList.remove('route-selection-target'), 2200);
    }});
  }};
  const routeBenchmarkFamily = String(params.get('route_benchmark_family') || '').trim().toLowerCase();
  const routeProjection = String(params.get('route_projection') || '').trim();
  const routeCaseId = String(params.get('route_case_id') || '').trim();
  const benchmarkSections = [...document.querySelectorAll('[data-route-benchmark-family]')];
  const routeBenchmarkTarget = benchmarkSections.find((node) => {{
    const familyMatch = routeBenchmarkFamily
      ? String(node.getAttribute('data-route-benchmark-family') || '').trim().toLowerCase() === routeBenchmarkFamily
      : false;
    const caseMatch = routeCaseId
      ? String(node.getAttribute('data-route-case-id') || '').trim() === routeCaseId
      : false;
    return familyMatch || caseMatch;
  }}) || null;

  if (routeBenchmarkFamily === 'peer' && routeProjection && peerProjection && peerBaselineMap[routeProjection] && peerOptimizedMap[routeProjection]) {{
    peerProjection.value = routeProjection;
    peerProjection.dispatchEvent(new Event('change'));
  }} else if (routeBenchmarkFamily === 'canton' && routeProjection && projection && baselineMap[routeProjection] && optimizedMap[routeProjection]) {{
    projection.value = routeProjection;
    projection.dispatchEvent(new Event('change'));
  }}

  if (routeBenchmarkTarget) {{
    flashRouteSelection(routeBenchmarkTarget);
  }}
}})();
</script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HTML benchmark optimization drawing review UI.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-html", type=Path, default=DEFAULT_OUT_HTML)
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_OUT_SUMMARY)
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    html_text = build_review_html(manifest=manifest, manifest_path=args.manifest, out_html=args.out_html)
    args.out_html.parent.mkdir(parents=True, exist_ok=True)
    args.out_html.write_text(html_text, encoding="utf-8")

    summary = {
        "schema_version": "benchmark_optimization_review.v1",
        "generated_at": _now_utc(),
        "manifest": str(args.manifest),
        "output_html": str(args.out_html),
        "canton_case_id": str((manifest.get("canton_tower_reduced_shm") or {}).get("selected_case_id", "") or ""),
        "peer_case_id": str((manifest.get("peer_blind_prediction") or {}).get("selected_case_id", "") or ""),
        "peer_drawing_kind": str((manifest.get("peer_blind_prediction") or {}).get("drawing_kind", "") or ""),
        "peer_sheet_path": str((((manifest.get("peer_blind_prediction") or {}).get("readiness_sheet") or {}).get("sheet_path", "") or "")),
        "artifact_links": {
            "optimized_drawing_review_html": _safe_rel_href(
                DEFAULT_OPTIMIZED_DRAWING_REVIEW_HTML,
                base_dir=args.summary_out.parent,
            ),
            "structural_optimization_viewer_html": _safe_rel_href(
                DEFAULT_STRUCTURAL_OPTIMIZATION_VIEWER_HTML,
                base_dir=args.summary_out.parent,
            ),
            "committee_dashboard_html": _safe_rel_href(
                DEFAULT_COMMITTEE_DASHBOARD_HTML,
                base_dir=args.summary_out.parent,
            ),
            "release_gap_report_json": _safe_rel_href(
                DEFAULT_RELEASE_GAP_REPORT_JSON,
                base_dir=args.summary_out.parent,
            ),
            "project_registry_report": _safe_rel_href(
                DEFAULT_PROJECT_REGISTRY_JSON,
                base_dir=args.summary_out.parent,
            ),
            "project_registry_json": _safe_rel_href(
                DEFAULT_PROJECT_REGISTRY_JSON,
                base_dir=args.summary_out.parent,
            ),
            "project_package_zip": _safe_rel_href(
                DEFAULT_PROJECT_PACKAGE_ZIP,
                base_dir=args.summary_out.parent,
            ),
            "project_registry_signature": _safe_rel_href(
                DEFAULT_PROJECT_REGISTRY_SIGNATURE,
                base_dir=args.summary_out.parent,
            ),
            "external_benchmark_batch_job_report_json": _safe_rel_href(
                DEFAULT_BATCH_JOB_REPORT_JSON,
                base_dir=args.summary_out.parent,
            ),
        },
    }
    args.summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Benchmark optimization review UI: {args.out_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
