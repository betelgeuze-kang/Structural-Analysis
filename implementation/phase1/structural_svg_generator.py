"""
Phase I-3: 고품질 구조 SVG 도면 생성기

상용툴 수준의 구조 도면 SVG를 생성합니다.
기존 _placeholder_svg() 대신 실 구조 데이터를 기반으로 렌더링합니다.

생성:
  - Plan View (XY 평면도)
  - Elevation View (XZ 정면도)
  - Isometric View (등각투영도)
  - D/C Ratio 컬러 오버레이

Usage:
    from structural_svg_generator import StructuralSVGGenerator
    gen = StructuralSVGGenerator(model_data)
    svg_plan = gen.plan_view(story=3)
    svg_elev = gen.elevation_view(axis='x', grid_index=0)
    svg_iso = gen.isometric_view()
"""

from __future__ import annotations

import html
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


# ─── Color Maps ───
COLORMAPS = {
    "jet": lambda t: _jet(t),
    "viridis": lambda t: _viridis(t),
    "coolwarm": lambda t: _coolwarm(t),
}

TYPE_COLORS = {
    "beam": "#4FB7AD",
    "column": "#EF7D73",
    "wall": "#63C7A1",
    "slab": "#E6A95D",
    "brace": "#F4B56B",
    "truss": "#fb923c",
}
TYPE_STROKE_WIDTH = {
    "beam": 2.0,
    "column": 3.0,
    "wall": 1.5,
    "slab": 1.0,
    "brace": 1.5,
}

SVG_DARK_SURFACE = "#111C29"
SVG_DARK_SURFACE_SOFT = "#152435"
SVG_DARK_SURFACE_STRONG = "#0D1824"
SVG_DARK_LINE = "#2B3D50"
SVG_TEXT_ON_DARK = "#ECF2F6"
SVG_MUTED_ON_DARK = "#96A8BB"
SVG_ACCENT_COOL = "#4FB7AD"
SVG_ACCENT_WARM = "#F4B56B"
SVG_TEXT_SOFT = "#C9D4DF"
SVG_UI_FONT = '"IBM Plex Sans KR","Pretendard","Noto Sans KR",sans-serif'
SVG_TITLE_FONT = '"Space Grotesk","IBM Plex Sans KR","Pretendard",sans-serif'


def _clamp(v: float, lo: float = 0, hi: float = 1) -> float:
    return max(lo, min(hi, v))


def _jet(t: float) -> str:
    t = _clamp(t)
    if t < 0.25:
        r, g, b = 0, t * 4, 1
    elif t < 0.5:
        r, g, b = 0, 1, 2 - t * 4
    elif t < 0.75:
        r, g, b = (t - 0.5) * 4, 1, 0
    else:
        r, g, b = 1, 4 - t * 4, 0
    return f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"


def _viridis(t: float) -> str:
    t = _clamp(t)
    h = 0.75 - t * 0.75
    s, l = 0.85, 0.15 + t * 0.55
    return _hsl_to_rgb_str(h, s, l)


def _coolwarm(t: float) -> str:
    t = _clamp(t)
    if t < 0.5:
        r, g, b = 0.2 + t * 0.4, 0.2 + t * 1.2, 0.8
    else:
        r, g, b = 0.8 + (t - 0.5) * 0.4, 1.4 - t * 1.2, 0.2
    r, g, b = _clamp(r), _clamp(g), _clamp(b)
    return f"rgb({int(r*255)},{int(g*255)},{int(b*255)})"


def _hsl_to_rgb_str(h: float, s: float, l: float) -> str:
    """HSL (0-1 range) to rgb() string."""
    if s == 0:
        v = int(l * 255)
        return f"rgb({v},{v},{v})"
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def hue2rgb(p_, q_, t_):
        if t_ < 0:
            t_ += 1
        if t_ > 1:
            t_ -= 1
        if t_ < 1 / 6:
            return p_ + (q_ - p_) * 6 * t_
        if t_ < 1 / 2:
            return q_
        if t_ < 2 / 3:
            return p_ + (q_ - p_) * (2 / 3 - t_) * 6
        return p_

    r = int(hue2rgb(p, q, h + 1 / 3) * 255)
    g = int(hue2rgb(p, q, h) * 255)
    b = int(hue2rgb(p, q, h - 1 / 3) * 255)
    return f"rgb({r},{g},{b})"


@dataclass
class Node:
    id: int
    x: float
    y: float
    z: float
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0


@dataclass
class Element:
    id: int
    type: str
    node_ids: list[int] = field(default_factory=list)
    section: str = ""
    dcr: float = 0.0
    story: int = -1


@dataclass
class StructuralModel:
    nodes: dict[int, Node] = field(default_factory=dict)
    elements: list[Element] = field(default_factory=list)
    stories: list[float] = field(default_factory=list)
    grid_x: list[float] = field(default_factory=list)
    grid_y: list[float] = field(default_factory=list)
    name: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class StructuralSVGGenerator:
    """구조 모델 데이터를 기반으로 고품질 SVG 도면을 생성합니다."""

    def __init__(
        self,
        model: dict[str, Any] | StructuralModel,
        *,
        colormap: str = "jet",
        scalar_field: str = "dcr",
    ):
        if isinstance(model, dict):
            self.model = self._parse_dict(model)
        else:
            self.model = model
        self.colormap_fn = COLORMAPS.get(colormap, COLORMAPS["jet"])
        self.scalar_field = scalar_field
        self._compute_bounds()

    @staticmethod
    def _parse_dict(d: dict) -> StructuralModel:
        meta = d.get("meta", {}) if isinstance(d.get("meta", {}), dict) else {}
        m = StructuralModel(name=meta.get("name", ""), meta=dict(meta))
        for nd in d.get("nodes", []):
            n = Node(
                id=nd["id"],
                x=nd.get("x", 0),
                y=nd.get("y", 0),
                z=nd.get("z", 0),
                dx=nd.get("dx", 0),
                dy=nd.get("dy", 0),
                dz=nd.get("dz", 0),
            )
            m.nodes[n.id] = n
        for ed in d.get("elements", []):
            e = Element(
                id=ed["id"],
                type=ed.get("type", "other"),
                node_ids=ed.get("node_ids", []),
                section=ed.get("section", ""),
                dcr=ed.get("dcr", 0),
            )
            m.elements.append(e)
        # Auto-detect stories/grids
        zvals = sorted({round(n.z, 2) for n in m.nodes.values()})
        m.stories = zvals
        m.grid_x = sorted({round(n.x, 2) for n in m.nodes.values()})
        m.grid_y = sorted({round(n.y, 2) for n in m.nodes.values()})
        return m

    def _compute_bounds(self):
        xs = [n.x for n in self.model.nodes.values()]
        ys = [n.y for n in self.model.nodes.values()]
        zs = [n.z for n in self.model.nodes.values()]
        self.min_x, self.max_x = min(xs, default=0), max(xs, default=1)
        self.min_y, self.max_y = min(ys, default=0), max(ys, default=1)
        self.min_z, self.max_z = min(zs, default=0), max(zs, default=1)
        dcrs = [e.dcr for e in self.model.elements if e.dcr > 0]
        self.dcr_min = min(dcrs) if dcrs else 0
        self.dcr_max = max(dcrs) if dcrs else 1

    def _dcr_color(self, dcr: float) -> str:
        if self.dcr_max <= self.dcr_min:
            t = 0
        else:
            t = (dcr - self.dcr_min) / (self.dcr_max - self.dcr_min)
        return self.colormap_fn(t)

    def _svg_root_style(self) -> str:
        return (
            f"background:{SVG_DARK_SURFACE};"
            f"font-family:{SVG_UI_FONT};"
            "text-rendering:geometricPrecision;"
            "shape-rendering:geometricPrecision;"
        )

    def _render_sheet_skin(self, *, width: float, height: float) -> list[str]:
        return [
            "<defs>",
            (
                "<linearGradient id='sheet-bg-gradient' x1='0' y1='0' x2='0' y2='1'>"
                f"<stop offset='0%' stop-color='{SVG_DARK_SURFACE_SOFT}'/>"
                f"<stop offset='100%' stop-color='{SVG_DARK_SURFACE}'/>"
                "</linearGradient>"
            ),
            (
                "<linearGradient id='sheet-panel-gradient' x1='0' y1='0' x2='0' y2='1'>"
                f"<stop offset='0%' stop-color='{SVG_DARK_SURFACE_SOFT}'/>"
                f"<stop offset='100%' stop-color='{SVG_DARK_SURFACE_STRONG}'/>"
                "</linearGradient>"
            ),
            (
                "<filter id='glow'><feGaussianBlur stdDeviation='1.5' result='blur'/>"
                "<feMerge><feMergeNode in='blur'/><feMergeNode in='SourceGraphic'/></feMerge></filter>"
            ),
            "</defs>",
            (
                f"<rect x='0' y='0' width='{width}' height='{height}' "
                "fill='url(#sheet-bg-gradient)' pointer-events='none'/>"
            ),
        ]

    def _label_width(self, text: str, font_size: float = 8.0) -> float:
        return max(len(str(text).strip()), 1) * font_size * 0.58 + 6

    def _assign_horizontal_label_lanes(
        self,
        labels: Sequence[tuple[float, str]],
        *,
        font_size: float = 8.0,
        min_gap: float = 4.0,
    ) -> list[int]:
        lane_right_edges: list[float] = []
        lanes = [0] * len(labels)
        ordered = sorted(
            enumerate(labels),
            key=lambda item: item[1][0] - self._label_width(item[1][1], font_size) / 2,
        )
        for index, (center, text) in ordered:
            width = self._label_width(text, font_size)
            left = center - width / 2
            right = center + width / 2
            lane = 0
            while lane < len(lane_right_edges) and left < lane_right_edges[lane] + min_gap:
                lane += 1
            if lane == len(lane_right_edges):
                lane_right_edges.append(right)
            else:
                lane_right_edges[lane] = right
            lanes[index] = lane
        return lanes

    def _assign_vertical_label_lanes(
        self,
        centers: Sequence[float],
        *,
        label_height: float = 9.0,
        min_gap: float = 3.0,
    ) -> list[int]:
        lane_bottom_edges: list[float] = []
        lanes = [0] * len(centers)
        ordered = sorted(enumerate(centers), key=lambda item: item[1] - label_height / 2)
        for index, center in ordered:
            top = center - label_height / 2
            bottom = center + label_height / 2
            lane = 0
            while lane < len(lane_bottom_edges) and top < lane_bottom_edges[lane] + min_gap:
                lane += 1
            if lane == len(lane_bottom_edges):
                lane_bottom_edges.append(bottom)
            else:
                lane_bottom_edges[lane] = bottom
            lanes[index] = lane
        return lanes

    def _title_block_fields(self, view_label: str, sheet_code: str) -> dict[str, str]:
        meta = self.model.meta if isinstance(getattr(self.model, "meta", None), dict) else {}
        title_block = meta.get("title_block", {}) if isinstance(meta.get("title_block", {}), dict) else {}
        project_name = (
            title_block.get("project")
            or meta.get("project_name")
            or self.model.name
            or "Structural Drawing Set"
        )
        issued_by = (
            title_block.get("issued_by")
            or meta.get("issued_by")
            or meta.get("generator")
            or "StructuralSVGGenerator"
        )
        revision = (
            title_block.get("revision_code")
            or title_block.get("revision")
            or meta.get("revision_code")
            or meta.get("revision")
            or meta.get("release_tag")
            or "-"
        )
        status = (
            title_block.get("revision_status")
            or title_block.get("status")
            or meta.get("revision_status")
            or meta.get("status")
            or "PRELIMINARY"
        )
        resolved_sheet_code = str(title_block.get("sheet") or sheet_code)
        sheet_set = (
            title_block.get("sheet_set")
            or meta.get("sheet_set")
            or title_block.get("package")
            or meta.get("package_name")
            or ""
        )
        sheet_index = title_block.get("sheet_index") or meta.get("sheet_index") or ""
        sheet_total = title_block.get("sheet_total") or meta.get("sheet_total") or ""
        issue_date = (
            title_block.get("date")
            or title_block.get("issue_date")
            or meta.get("issue_date")
            or meta.get("generated_date")
            or meta.get("date")
            or ""
        )
        sheet_register = f"SHEET {resolved_sheet_code}"
        if sheet_total:
            sheet_register = f"{sheet_register} / {sheet_total}"
        if sheet_set:
            sheet_register = f"{sheet_set} | {sheet_register}"
        return {
            "project_name": html.escape(str(project_name), quote=True),
            "view_label": html.escape(str(view_label), quote=True),
            "sheet_code": html.escape(resolved_sheet_code, quote=True),
            "revision": html.escape(str(revision), quote=True),
            "issued_by": html.escape(str(issued_by), quote=True),
            "status": html.escape(str(status), quote=True),
            "sheet_set": html.escape(str(sheet_set), quote=True),
            "sheet_index": html.escape(str(sheet_index), quote=True),
            "sheet_total": html.escape(str(sheet_total), quote=True),
            "sheet_register": html.escape(sheet_register, quote=True),
            "issue_date": html.escape(str(issue_date), quote=True),
        }

    def _revision_history_fields(self) -> list[dict[str, str]]:
        meta = self.model.meta if isinstance(getattr(self.model, "meta", None), dict) else {}
        title_block = meta.get("title_block", {}) if isinstance(meta.get("title_block", {}), dict) else {}
        raw_entries = title_block.get("revision_history")
        if not isinstance(raw_entries, list):
            raw_entries = meta.get("revision_history")
        if not isinstance(raw_entries, list):
            return []
        entries: list[dict[str, str]] = []
        for entry in raw_entries[:3]:
            if not isinstance(entry, dict):
                continue
            revision = entry.get("revision_code") or entry.get("revision") or entry.get("rev") or "-"
            status = entry.get("status") or entry.get("note") or entry.get("label") or ""
            issue_date = entry.get("date") or entry.get("issue_date") or entry.get("issued_on") or ""
            if not any(str(value).strip() for value in (revision, status, issue_date)):
                continue
            entries.append(
                {
                    "revision": html.escape(str(revision), quote=True),
                    "status": html.escape(str(status), quote=True),
                    "issue_date": html.escape(str(issue_date), quote=True),
                }
            )
        return entries

    def _svg_sheet_metadata_attributes(self, *, fields: dict[str, str]) -> str:
        attrs = [
            ("data-sheet-code", fields["sheet_code"]),
            ("data-sheet-set", fields["sheet_set"]),
            ("data-sheet-index", fields["sheet_index"]),
            ("data-sheet-total", fields["sheet_total"]),
            ("data-sheet-register", fields["sheet_register"]),
            ("data-revision-code", fields["revision"]),
            ("data-revision-status", fields["status"]),
            ("data-revision-date", fields["issue_date"]),
        ]
        return " ".join(f"{name}='{value}'" for name, value in attrs if value)

    def _render_title_block(
        self,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
        view_label: str,
        sheet_code: str,
    ) -> list[str]:
        fields = self._title_block_fields(view_label, sheet_code)
        split_x = x + width * 0.68
        row_mid = y + height * 0.52
        revision_history = self._revision_history_fields()
        register_line = []
        if fields["sheet_set"] or fields["sheet_total"] or fields["issue_date"]:
            register_text = fields["sheet_register"]
            if fields["issue_date"]:
                register_text = f"{register_text} · {fields['issue_date']}"
            register_line.append(
                f"<text x='{x:.1f}' y='{y - 6:.1f}' fill='{SVG_MUTED_ON_DARK}' font-size='7.5' class='sheet-register'>{register_text}</text>"
            )
        history_lines: list[str] = []
        if revision_history:
            history_y = y - 16
            for index, entry in enumerate(revision_history):
                parts = [entry["revision"]]
                if entry["status"]:
                    parts.append(entry["status"])
                if entry["issue_date"]:
                    parts.append(entry["issue_date"])
                history_lines.append(
                    f"<text x='{x:.1f}' y='{history_y - (len(revision_history) - index - 1) * 9:.1f}' fill='{SVG_MUTED_ON_DARK}' "
                    f"font-size='7' class='revision-history-line'>{' · '.join(parts)}</text>"
                )
        return register_line + history_lines + [
            (
                f"<g class='title-block' data-sheet-code='{fields['sheet_code']}' "
                f"data-view-label='{fields['view_label']}' "
                f"data-sheet-set='{fields['sheet_set']}' "
                f"data-sheet-index='{fields['sheet_index']}' "
                f"data-sheet-total='{fields['sheet_total']}' "
                f"data-sheet-register='{fields['sheet_register']}' "
                f"data-revision-code='{fields['revision']}' "
                f"data-revision-status='{fields['status']}' "
                f"data-revision-date='{fields['issue_date']}'>"
            ),
            (
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{width:.1f}' height='{height:.1f}' "
                f"rx='8' class='title-block-shell' fill='url(#sheet-panel-gradient)' stroke='{SVG_DARK_LINE}' stroke-width='1'/>"
            ),
            (
                f"<line x1='{split_x:.1f}' y1='{y:.1f}' x2='{split_x:.1f}' y2='{y + height:.1f}' "
                f"class='title-block-divider' stroke='{SVG_DARK_LINE}' stroke-width='1'/>"
            ),
            (
                f"<line x1='{x:.1f}' y1='{row_mid:.1f}' x2='{x + width:.1f}' y2='{row_mid:.1f}' "
                f"class='title-block-divider' stroke='{SVG_DARK_LINE}' stroke-width='1'/>"
            ),
            f"<text x='{x + 10:.1f}' y='{y + 14:.1f}' fill='{SVG_MUTED_ON_DARK}' font-size='8' class='title-block-label'>PROJECT</text>",
            (
                f"<text x='{x + 10:.1f}' y='{y + 29:.1f}' fill='{SVG_TEXT_ON_DARK}' font-size='11' "
                f"font-weight='700' class='title-block-value title-block-value--project'>{fields['project_name']}</text>"
            ),
            f"<text x='{x + 10:.1f}' y='{row_mid + 12:.1f}' fill='{SVG_MUTED_ON_DARK}' font-size='8' class='title-block-label'>VIEW</text>",
            (
                f"<text x='{x + 10:.1f}' y='{row_mid + 27:.1f}' fill='{SVG_TEXT_ON_DARK}' font-size='10' "
                f"font-weight='600' class='title-block-value title-block-value--view'>{fields['view_label']}</text>"
            ),
            f"<text x='{split_x + 10:.1f}' y='{y + 14:.1f}' fill='{SVG_MUTED_ON_DARK}' font-size='8' class='title-block-label'>SHEET / REV</text>",
            (
                f"<text x='{split_x + 10:.1f}' y='{y + 29:.1f}' fill='{SVG_TEXT_ON_DARK}' font-size='10' "
                f"font-weight='700' class='title-block-value title-block-value--sheet'>{fields['sheet_code']} · {fields['revision']}</text>"
            ),
            f"<text x='{split_x + 10:.1f}' y='{row_mid + 12:.1f}' fill='{SVG_MUTED_ON_DARK}' font-size='8' class='title-block-label'>STATUS / ISSUE</text>",
            (
                f"<text x='{split_x + 10:.1f}' y='{row_mid + 27:.1f}' fill='{SVG_ACCENT_WARM}' font-size='9' "
                f"font-weight='600' class='title-block-value title-block-value--status'>{fields['status']} · {fields['issued_by']}</text>"
            ),
            "</g>",
        ]

    def _viewer_base_href(self) -> str:
        meta = self.model.meta if isinstance(getattr(self.model, "meta", None), dict) else {}
        viewer_href = (
            meta.get("viewer_href")
            or meta.get("viewer_url")
            or "../../../src/structure-viewer/index.html"
        )
        return str(viewer_href)

    def _build_viewer_href(self, member_id: int | str, *, sheet_key: str, view_label: str) -> str:
        parts = urlsplit(self._viewer_base_href())
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        member_label = str(member_id)
        query["member"] = member_label
        query["focus_member"] = member_label
        query["drawing_sheet"] = sheet_key
        query["drawing_view"] = view_label
        return html.escape(
            urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)),
            quote=True,
        )

    def _wrap_member_link(
        self,
        member_id: int | str,
        markup: str,
        *,
        sheet_key: str,
        view_label: str,
    ) -> str:
        member_label = html.escape(str(member_id), quote=True)
        href = self._build_viewer_href(member_id, sheet_key=sheet_key, view_label=view_label)
        return (
            f"<a class='member-link' data-viewer-member-id='{member_label}' href='{href}' "
            f"target='_blank'>{markup}</a>"
        )

    def _render_svg_interactivity(
        self,
        *,
        width: float,
        sheet_key: str,
        view_label: str,
    ) -> list[str]:
        viewer_base_href = html.escape(self._viewer_base_href(), quote=True)
        safe_sheet_key = html.escape(sheet_key, quote=True)
        safe_view_label = html.escape(view_label, quote=True)
        return [
            (
                "<style><![CDATA["
                ".structural-svg{text-rendering:geometricPrecision;shape-rendering:geometricPrecision;}"
                f".structural-svg text{{font-family:{SVG_UI_FONT};}}"
                f".structural-svg .sheet-title{{font-family:{SVG_TITLE_FONT};font-weight:700;letter-spacing:-0.03em;fill:{SVG_TEXT_ON_DARK};}}"
                f".structural-svg .title-block-label{{fill:{SVG_MUTED_ON_DARK};font-size:8px;font-weight:700;letter-spacing:0.12em;}}"
                f".structural-svg .title-block-value{{fill:{SVG_TEXT_ON_DARK};font-weight:700;}}"
                f".structural-svg .title-block-value--project,.structural-svg .title-block-value--sheet{{font-family:{SVG_TITLE_FONT};letter-spacing:-0.02em;}}"
                f".structural-svg .title-block-value--status{{fill:{SVG_ACCENT_WARM};}}"
                f".structural-svg .sheet-register{{fill:{SVG_MUTED_ON_DARK};font-size:7.5px;letter-spacing:0;}}"
                f".structural-svg .revision-history-line{{fill:{SVG_MUTED_ON_DARK};font-size:7px;letter-spacing:0;}}"
                f".structural-svg .title-block-shell{{fill:url(#sheet-panel-gradient);stroke:{SVG_DARK_LINE};stroke-width:1;}}"
                f".structural-svg .title-block-divider{{stroke:{SVG_DARK_LINE};stroke-width:1;}}"
                ".structural-svg .member-link{cursor:pointer}"
                ".structural-svg .member-link [data-member-id]{transition:opacity .12s ease,stroke .12s ease,fill-opacity .12s ease}"
                f".structural-svg .member-link:hover [data-member-id]{{opacity:1;stroke:{SVG_ACCENT_COOL} !important}}"
                f".structural-svg [data-member-id].is-active{{stroke:{SVG_TEXT_ON_DARK} !important;stroke-width:3 !important;fill-opacity:0.35}}"
                ".structural-svg .member-callout-leader,.structural-svg .member-callout-anchor{pointer-events:none}"
                ".structural-svg .member-callout [data-callout-box]{transition:stroke .12s ease,fill .12s ease}"
                f".structural-svg .member-callout-link:hover [data-callout-box]{{stroke:{SVG_ACCENT_COOL} !important}}"
                f".structural-svg .member-callout.is-active [data-callout-box]{{stroke:{SVG_ACCENT_COOL} !important;fill:url(#sheet-panel-gradient) !important}}"
                f".structural-svg .member-callout-label{{fill:{SVG_ACCENT_COOL};font-size:9px;font-weight:700;}}"
                f".structural-svg .member-callout-meta,.structural-svg .member-callout-note{{fill:{SVG_TEXT_SOFT};font-size:8px;}}"
                f".structural-svg #svg-review-toolbar rect{{fill:url(#sheet-panel-gradient);stroke:{SVG_DARK_LINE};}}"
                f".structural-svg #svg-review-toolbar text{{pointer-events:none;fill:{SVG_ACCENT_COOL};font-size:10px;font-weight:700;}}"
                "]]></style>"
            ),
            (
                f"<g id='svg-review-toolbar' visibility='hidden' data-sheet-key='{safe_sheet_key}' "
                f"transform='translate({width - 184:.1f},16)'>"
                "<rect width='168' height='26' rx='8' fill='url(#sheet-panel-gradient)' stroke='#2B3D50' stroke-width='1'/>"
                "<a id='svg-open-viewer-link' target='_blank'>"
                f"<text id='svg-open-viewer-label' x='84' y='17' text-anchor='middle' fill='{SVG_ACCENT_COOL}' font-size='10' font-weight='700'>Open 3D Viewer</text>"
                "</a>"
                "</g>"
            ),
            (
                f"<script><![CDATA[(function(){{const svg=document.currentScript&&document.currentScript.ownerSVGElement;if(!svg)return;"
                f"const params=new URLSearchParams(window.location.search);"
                f"const activeMember=(params.get('member')||params.get('member_id')||'').trim();"
                f"const viewerParam=(params.get('viewer')||'').trim();"
                f"const baseHref=viewerParam||svg.getAttribute('data-viewer-base-url')||'{viewer_base_href}';"
                f"const sheetKey=svg.getAttribute('data-sheet-key')||'{safe_sheet_key}';"
                f"const currentView=svg.getAttribute('data-view-label')||'{safe_view_label}';"
                "function buildHref(memberId){if(!memberId)return'';try{const url=new URL(baseHref,window.location.href);"
                "url.searchParams.set('member',memberId);url.searchParams.set('focus_member',memberId);"
                "url.searchParams.set('drawing_sheet',sheetKey);url.searchParams.set('drawing_view',currentView);"
                "return url.href;}catch(_err){return baseHref;}}"
                "svg.querySelectorAll('[data-viewer-member-id]').forEach(anchor=>{const memberId=(anchor.getAttribute('data-viewer-member-id')||'').trim();"
                "const href=buildHref(memberId);if(href)anchor.setAttribute('href',href);anchor.setAttribute('target','_blank');});"
                "const toolbar=svg.querySelector('#svg-review-toolbar');const toolbarLink=svg.querySelector('#svg-open-viewer-link');"
                "const toolbarLabel=svg.querySelector('#svg-open-viewer-label');"
                "if(activeMember){svg.querySelectorAll('[data-member-id]').forEach(node=>{node.classList.toggle('is-active',(node.getAttribute('data-member-id')||'').trim()===activeMember);});"
                "svg.querySelectorAll('[data-callout-member-id]').forEach(node=>{node.classList.toggle('is-active',(node.getAttribute('data-callout-member-id')||'').trim()===activeMember);});"
                "if(toolbar&&toolbarLink){const href=buildHref(activeMember);if(href){toolbarLink.setAttribute('href',href);toolbar.setAttribute('visibility','visible');"
                "if(toolbarLabel)toolbarLabel.textContent='Open 3D Viewer · #'+activeMember;}}}"
                "})();]]></script>"
            ),
        ]

    def _callout_specs(
        self,
        *,
        sheet_key: str,
        view_label: str,
        story_z: float | None = None,
        axis: str | None = None,
    ) -> list[dict[str, Any]]:
        meta = self.model.meta if isinstance(getattr(self.model, "meta", None), dict) else {}
        title_block = meta.get("title_block", {}) if isinstance(meta.get("title_block", {}), dict) else {}
        raw_callouts: Any = None
        for source in (title_block, meta):
            for key in ("callouts", "annotations", "review_callouts"):
                if isinstance(source.get(key), list):
                    raw_callouts = source.get(key)
                    break
            if raw_callouts is not None:
                break
        if not isinstance(raw_callouts, list):
            return []

        view_tokens = {
            view_label.lower(),
            sheet_key.lower(),
        }
        if sheet_key.startswith("plan_"):
            view_tokens.update({"plan", "plan_view"})
        elif sheet_key.startswith("elevation_"):
            view_tokens.update({"elevation", "elevation_view"})
        elif sheet_key == "isometric":
            view_tokens.update({"isometric", "isometric_view", "iso"})

        callouts: list[dict[str, Any]] = []
        for index, entry in enumerate(raw_callouts):
            if not isinstance(entry, dict):
                continue
            member_id = entry.get("member_id") or entry.get("element_id") or entry.get("id")
            if member_id is None:
                continue
            target_sheet = str(entry.get("sheet_key") or entry.get("sheet") or "").strip().lower()
            if target_sheet and target_sheet != sheet_key.lower():
                continue
            target_view = str(entry.get("view") or entry.get("projection") or entry.get("view_label") or "").strip().lower()
            if target_view and target_view not in view_tokens:
                continue
            target_story = entry.get("story_z")
            if target_story is not None and story_z is not None:
                try:
                    if not math.isclose(float(target_story), story_z, abs_tol=1e-6):
                        continue
                except (TypeError, ValueError):
                    continue
            target_axis = str(entry.get("axis") or "").strip().lower()
            if target_axis and axis is not None and target_axis != axis.lower():
                continue
            callouts.append(
                {
                    "member_id": str(member_id),
                    "label": html.escape(str(entry.get("label") or entry.get("title") or f"Member {member_id}"), quote=True),
                    "note": html.escape(str(entry.get("note") or entry.get("text") or entry.get("copy") or ""), quote=True),
                    "tone": html.escape(str(entry.get("tone") or entry.get("status") or ""), quote=True),
                    "priority": entry.get("priority", 0),
                    "order": index,
                }
            )
        def _priority_value(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        callouts.sort(key=lambda item: (-_priority_value(item["priority"]), item["order"]))
        return callouts

    def _render_member_callouts(
        self,
        *,
        callouts: Sequence[dict[str, Any]],
        member_positions: dict[str, tuple[float, float]],
        width: float,
        height: float,
        sheet_key: str,
        view_label: str,
    ) -> list[str]:
        entries: list[dict[str, Any]] = []
        for callout in callouts:
            anchor = member_positions.get(str(callout["member_id"]))
            if anchor is None:
                continue
            note = str(callout["note"])
            box_height = 54.0 if note else 42.0
            entries.append(
                {
                    **callout,
                    "anchor_x": anchor[0],
                    "anchor_y": anchor[1],
                    "box_height": box_height,
                    "ideal_y": anchor[1] - box_height / 2,
                }
            )
        if not entries:
            return []

        entries.sort(key=lambda item: (item["ideal_y"], item["order"]))
        top = 54.0
        gap = 8.0
        box_width = min(190.0, max(150.0, width * 0.24))
        right_padding = 20.0
        box_x = max(16.0, width - box_width - right_padding)
        bottom = max(top + max(entry["box_height"] for entry in entries), height - 94.0)
        cursor = top
        for entry in entries:
            y = max(entry["ideal_y"], cursor)
            entry["box_y"] = min(y, bottom - entry["box_height"])
            cursor = entry["box_y"] + entry["box_height"] + gap
        if entries[-1]["box_y"] + entries[-1]["box_height"] > bottom:
            cursor = bottom
            for entry in reversed(entries):
                cursor -= entry["box_height"]
                entry["box_y"] = min(entry["box_y"], cursor)
                cursor = entry["box_y"] - gap
            if entries[0]["box_y"] < top:
                shift = top - entries[0]["box_y"]
                for entry in entries:
                    entry["box_y"] += shift

        rendered: list[str] = []
        for lane, entry in enumerate(entries):
            member_id = str(entry["member_id"])
            href = self._build_viewer_href(member_id, sheet_key=sheet_key, view_label=view_label)
            box_y = entry["box_y"]
            box_mid_y = box_y + entry["box_height"] / 2
            line_end_x = box_x
            line_end_y = min(max(entry["anchor_y"], box_y + 12.0), box_y + entry["box_height"] - 12.0)
            meta_text = f"#{member_id}"
            if entry["tone"]:
                meta_text = f"{meta_text} · {entry['tone']}"
            safe_sheet_key = html.escape(sheet_key, quote=True)
            rendered.extend(
                [
                    (
                        f"<g class='member-callout' data-callout-sheet='{safe_sheet_key}' "
                        f"data-callout-member-id='{member_id}' data-callout-lane='{lane}'>"
                    ),
                    (
                        f"<line class='member-callout-leader' x1='{entry['anchor_x']:.1f}' y1='{entry['anchor_y']:.1f}' "
                        f"x2='{line_end_x:.1f}' y2='{line_end_y:.1f}' stroke='{SVG_MUTED_ON_DARK}' stroke-width='1' "
                        f"stroke-dasharray='4 3' opacity='0.9'/>"
                    ),
                    (
                        f"<circle class='member-callout-anchor' cx='{entry['anchor_x']:.1f}' cy='{entry['anchor_y']:.1f}' "
                        f"r='2.3' fill='{SVG_TEXT_ON_DARK}' stroke='{SVG_DARK_SURFACE}' stroke-width='1'/>"
                    ),
                    f"<a class='member-link member-callout-link' data-viewer-member-id='{member_id}' href='{href}' target='_blank'>",
                    (
                        f"<rect x='{box_x:.1f}' y='{box_y:.1f}' width='{box_width:.1f}' height='{entry['box_height']:.1f}' "
                        f"rx='9' fill='url(#sheet-panel-gradient)' stroke='{SVG_DARK_LINE}' stroke-width='1' data-callout-box='true'/>"
                    ),
                    (
                        f"<text x='{box_x + 10:.1f}' y='{box_y + 16:.1f}' fill='{SVG_ACCENT_COOL}' font-size='9' "
                        f"font-weight='700' class='member-callout-label'>{entry['label']}</text>"
                    ),
                    (
                        f"<text x='{box_x + 10:.1f}' y='{box_y + 29:.1f}' fill='{SVG_TEXT_ON_DARK}' font-size='8.5' "
                        f"class='member-callout-meta'>{meta_text}</text>"
                    ),
                ]
            )
            if entry["note"]:
                rendered.append(
                    f"<text x='{box_x + 10:.1f}' y='{box_y + 42:.1f}' fill='{SVG_TEXT_SOFT}' font-size='8' class='member-callout-note'>{entry['note']}</text>"
                )
            rendered.append("</a>")
            rendered.append("</g>")
        return rendered

    # ─── Plan View ───
    def plan_view(
        self,
        *,
        story_z: float | None = None,
        width: int = 800,
        height: int = 600,
        show_grid: bool = True,
        show_dcr: bool = True,
        show_labels: bool = True,
        show_dimensions: bool = True,
        show_title: bool = True,
        show_title_block: bool = True,
        show_legend: bool = True,
    ) -> str:
        """XY 평면도 SVG 생성."""
        if story_z is None:
            story_z = self.model.stories[-1] if self.model.stories else self.max_z
        sheet_key = f"plan_z{story_z:.1f}"
        sheet_code = f"PLAN-Z{story_z:.1f}"
        view_label = f"Plan View — Z = {story_z:.1f}m"
        title_fields = self._title_block_fields(view_label, sheet_code)
        svg_metadata_attrs = self._svg_sheet_metadata_attributes(fields=title_fields)

        margin_left = 60
        margin_right = 60
        margin_top = 60
        margin_bottom = 60
        sx = (width - margin_left - margin_right) / max(self.max_x - self.min_x, 0.1)
        sy = (height - margin_top - margin_bottom) / max(self.max_y - self.min_y, 0.1)
        scale = min(sx, sy)

        def tx(v):
            return margin_left + (v - self.min_x) * scale

        def ty(v):
            return height - margin_bottom - (v - self.min_y) * scale

        parts = [
            f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' "
            f"role='img' aria-label='Plan View at z={story_z:.1f}' class='structural-svg plan-view' "
            f"style='{self._svg_root_style()}' "
            f"data-viewer-base-url='{html.escape(self._viewer_base_href(), quote=True)}' "
            f"data-sheet-key='{html.escape(sheet_key, quote=True)}' "
            f"data-view-label='{html.escape(view_label, quote=True)}' {svg_metadata_attrs}>",
        ]
        parts.extend(self._render_sheet_skin(width=width, height=height))

        # Grid lines
        if show_grid:
            for i, gx in enumerate(self.model.grid_x):
                x = tx(gx)
                parts.append(
                    f"<line x1='{x:.1f}' y1='{margin_top-20}' x2='{x:.1f}' y2='{height-margin_bottom+10}' "
                    f"stroke='{SVG_DARK_LINE}' stroke-width='0.5' stroke-dasharray='4 4'/>"
                )
                if show_labels:
                    label = chr(65 + i) if i < 26 else str(i + 1)
                    parts.append(
                        f"<text x='{x:.1f}' y='{margin_top-28}' text-anchor='middle' fill='{SVG_MUTED_ON_DARK}' "
                        f"font-size='10' font-weight='600'>{label}</text>"
                    )
            for j, gy in enumerate(self.model.grid_y):
                y = ty(gy)
                parts.append(
                    f"<line x1='{margin_left-20}' y1='{y:.1f}' x2='{width-margin_right+10}' y2='{y:.1f}' "
                    f"stroke='{SVG_DARK_LINE}' stroke-width='0.5' stroke-dasharray='4 4'/>"
                )
                if show_labels:
                    parts.append(
                        f"<text x='{margin_left-28}' y='{y + 4:.1f}' text-anchor='middle' fill='{SVG_MUTED_ON_DARK}' "
                        f"font-size='10' font-weight='600'>{j+1}</text>"
                    )

            if show_dimensions and len(self.model.grid_x) >= 2:
                horizontal_labels = []
                for i in range(len(self.model.grid_x)-1):
                    x1, x2 = tx(self.model.grid_x[i]), tx(self.model.grid_x[i+1])
                    val = self.model.grid_x[i+1] - self.model.grid_x[i]
                    my = margin_top - 10
                    parts.append(f"<line x1='{x1:.1f}' y1='{my}' x2='{x2:.1f}' y2='{my}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                    parts.append(f"<line x1='{x1:.1f}' y1='{my-3}' x2='{x1:.1f}' y2='{my+3}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                    parts.append(f"<line x1='{x2:.1f}' y1='{my-3}' x2='{x2:.1f}' y2='{my+3}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                    horizontal_labels.append(((x1 + x2) / 2, f"{val:.1f}", my))
                lanes = self._assign_horizontal_label_lanes([(center, text) for center, text, _ in horizontal_labels])
                for (center, text, my), lane in zip(horizontal_labels, lanes):
                    label_y = my - 4 - lane * 11
                    parts.append(
                        f"<text x='{center:.1f}' y='{label_y:.1f}' text-anchor='middle' fill='{SVG_MUTED_ON_DARK}' "
                        f"font-size='8' class='dimension-label dimension-label-x' data-dim-axis='x' "
                        f"data-dim-lane='{lane}'>{text}</text>"
                    )

            if show_dimensions and len(self.model.grid_y) >= 2:
                vertical_labels = []
                for j in range(len(self.model.grid_y)-1):
                    y1, y2 = ty(self.model.grid_y[j]), ty(self.model.grid_y[j+1])
                    val = self.model.grid_y[j+1] - self.model.grid_y[j]
                    mx = margin_left - 10
                    parts.append(f"<line x1='{mx}' y1='{y1:.1f}' x2='{mx}' y2='{y2:.1f}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                    parts.append(f"<line x1='{mx-3}' y1='{y1:.1f}' x2='{mx+3}' y2='{y1:.1f}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                    parts.append(f"<line x1='{mx-3}' y1='{y2:.1f}' x2='{mx+3}' y2='{y2:.1f}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                    vertical_labels.append((((y1 + y2) / 2) + 3, f"{abs(val):.1f}", mx))
                lanes = self._assign_vertical_label_lanes([center for center, _, _ in vertical_labels])
                for (center, text, mx), lane in zip(vertical_labels, lanes):
                    label_x = mx - 4 - lane * 22
                    parts.append(
                        f"<text x='{label_x:.1f}' y='{center:.1f}' text-anchor='end' fill='{SVG_MUTED_ON_DARK}' "
                        f"font-size='8' class='dimension-label dimension-label-y' data-dim-axis='y' "
                        f"data-dim-lane='{lane}'>{text}</text>"
                    )

        # Elements at this story level (tolerance ±0.5)
        tol = 0.5
        layer_groups = {"column": [], "beam": [], "wall": [], "slab": [], "other": []}
        member_positions: dict[str, tuple[float, float]] = {}
        
        for el in self.model.elements:
            ns = [self.model.nodes.get(nid) for nid in el.node_ids]
            ns = [n for n in ns if n is not None]
            if not ns:
                continue
            avg_z = sum(n.z for n in ns) / len(ns)
            etype = el.type.lower()

            # Columns: show at their XY position if they span this story
            if etype == "column" and len(ns) >= 2:
                zmin_e = min(n.z for n in ns)
                zmax_e = max(n.z for n in ns)
                if zmin_e <= story_z <= zmax_e + tol:
                    cx = sum(n.x for n in ns) / len(ns)
                    cy = sum(n.y for n in ns) / len(ns)
                    center = (tx(cx), ty(cy))
                    color = self._dcr_color(el.dcr) if show_dcr else TYPE_COLORS.get(etype, "#94a3b8")
                    element_markup = (
                        f"  <rect x='{center[0]-4:.1f}' y='{center[1]-4:.1f}' width='8' height='8' "
                        f"fill='{color}' rx='1' data-member-id='{el.id}' data-type='{etype}' "
                        f"opacity='0.9' filter='url(#glow)'>"
                        f"<title>Column #{el.id} DCR={el.dcr:.3f}</title></rect>"
                    )
                    member_positions[str(el.id)] = center
                    layer_groups["column"].append(
                        self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                    )
            # Beams: show at story level
            elif etype in ("beam", "brace", "truss") and len(ns) >= 2:
                if abs(avg_z - story_z) <= tol:
                    x1, y1 = tx(ns[0].x), ty(ns[0].y)
                    x2, y2 = tx(ns[1].x), ty(ns[1].y)
                    member_positions[str(el.id)] = ((x1 + x2) / 2, (y1 + y2) / 2)
                    color = self._dcr_color(el.dcr) if show_dcr else TYPE_COLORS.get(etype, "#94a3b8")
                    element_markup = (
                        f"  <line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                        f"stroke='{color}' stroke-width='2' data-member-id='{el.id}' "
                        f"data-type='{etype}' opacity='0.85'>"
                        f"<title>{etype.title()} #{el.id} DCR={el.dcr:.3f} {el.section}</title></line>"
                    )
                    layer_groups["beam"].append(
                        self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                    )
            # Walls
            elif etype == "wall" and len(ns) >= 4:
                if any(abs(n.z - story_z) <= tol for n in ns):
                    xys = list({(n.x, n.y) for n in ns})
                    if len(xys) >= 2:
                        color = self._dcr_color(el.dcr) if show_dcr else TYPE_COLORS.get(etype, "#94a3b8")
                        member_positions[str(el.id)] = (
                            (tx(xys[0][0]) + tx(xys[1][0])) / 2,
                            (ty(xys[0][1]) + ty(xys[1][1])) / 2,
                        )
                        element_markup = (
                            f"  <line x1='{tx(xys[0][0]):.1f}' y1='{ty(xys[0][1]):.1f}' "
                            f"x2='{tx(xys[1][0]):.1f}' y2='{ty(xys[1][1]):.1f}' "
                            f"stroke='{color}' stroke-width='4' data-member-id='{el.id}' "
                            f"data-type='wall' opacity='0.7'>"
                            f"<title>Wall #{el.id} DCR={el.dcr:.3f}</title></line>"
                        )
                        layer_groups["wall"].append(
                            self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                        )
            # Slabs
            elif etype == "slab" and len(ns) >= 4:
                if abs(avg_z - story_z) <= tol:
                    pts = " ".join(f"{tx(n.x):.1f},{ty(n.y):.1f}" for n in ns)
                    member_positions[str(el.id)] = (
                        sum(tx(n.x) for n in ns) / len(ns),
                        sum(ty(n.y) for n in ns) / len(ns),
                    )
                    color = self._dcr_color(el.dcr) if show_dcr else TYPE_COLORS.get(etype, "#94a3b8")
                    element_markup = (
                        f"  <polygon points='{pts}' fill='{color}' fill-opacity='0.15' "
                        f"stroke='{color}' stroke-width='0.5' stroke-opacity='0.3' "
                        f"data-member-id='{el.id}' data-type='slab'>"
                        f"<title>Slab #{el.id}</title></polygon>"
                    )
                    layer_groups["slab"].append(
                        self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                    )
            else:
                if etype not in layer_groups: layer_groups[etype] = []

        # Add groups to parts
        for l_type, l_parts in layer_groups.items():
            if l_parts:
                parts.append(f"<g class='layer-group layer-{l_type}'>")
                parts.extend(l_parts)
                parts.append("</g>")

        # Nodes
        for n in self.model.nodes.values():
            if abs(n.z - story_z) <= tol:
                parts.append(
                    f"<circle cx='{tx(n.x):.1f}' cy='{ty(n.y):.1f}' r='1.5' fill='{SVG_MUTED_ON_DARK}' opacity='0.5'/>"
                )

        callouts = self._callout_specs(sheet_key=sheet_key, view_label=view_label, story_z=story_z)
        if callouts:
            parts.extend(
                self._render_member_callouts(
                    callouts=callouts,
                    member_positions=member_positions,
                    width=width,
                    height=height,
                    sheet_key=sheet_key,
                    view_label=view_label,
                )
            )

        # Title
        if show_title:
            parts.append(
                f"<text x='{width/2:.1f}' y='24' text-anchor='middle' fill='{SVG_TEXT_ON_DARK}' "
                f"font-size='15' font-weight='700' class='sheet-title'>{view_label}</text>"
            )
        if show_title_block:
            parts.extend(
                self._render_title_block(
                    x=16,
                    y=height - 66,
                    width=260,
                    height=48,
                    view_label=view_label,
                    sheet_code=sheet_code,
                )
            )

        # Legend
        if show_dcr and show_legend:
            parts.extend(self._render_legend(width - 200, height - 35, 160))

        parts.extend(self._render_svg_interactivity(width=width, sheet_key=sheet_key, view_label=view_label))
        parts.append("</svg>")
        return "\n".join(parts)

    # ─── Elevation View ───
    def elevation_view(
        self,
        *,
        axis: str = "x",
        grid_value: float | None = None,
        width: int = 800,
        height: int = 600,
        show_dcr: bool = True,
        show_dimensions: bool = True,
        show_title: bool = True,
        show_title_block: bool = True,
        show_legend: bool = True,
    ) -> str:
        """XZ 또는 YZ 정면도 SVG."""
        margin = 60
        sheet_key = "elevation_xz" if axis == "x" else "elevation_yz"
        if axis == "x":
            h_range = self.max_x - self.min_x
            def h_of(n):
                return n.x
            def filt(n):
                return grid_value is None or abs(n.y - grid_value) < 0.5
            title_axis = "X"
        else:
            h_range = self.max_y - self.min_y
            def h_of(n):
                return n.y
            def filt(n):
                return grid_value is None or abs(n.x - grid_value) < 0.5
            title_axis = "Y"

        v_range = self.max_z - self.min_z
        sh = (width - 2 * margin) / max(h_range, 0.1)
        sv = (height - 2 * margin) / max(v_range, 0.1)
        scale = min(sh, sv)

        if axis == "x":
            def txf(n): return margin + (n.x - self.min_x) * scale
        else:
            def txf(n): return margin + (n.y - self.min_y) * scale

        def tyf(n):
            return height - margin - (n.z - self.min_z) * scale

        grid_label = f" @ {title_axis}={grid_value:.1f}" if grid_value is not None else ""
        view_label = f"Elevation View ({title_axis}-Z){grid_label}"
        sheet_code = f"EL-{title_axis}"
        title_fields = self._title_block_fields(view_label, sheet_code)
        svg_metadata_attrs = self._svg_sheet_metadata_attributes(fields=title_fields)
        parts = [
            f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' "
            f"role='img' aria-label='Elevation View ({title_axis})' class='structural-svg elevation-view' "
            f"style='{self._svg_root_style()}' "
            f"data-viewer-base-url='{html.escape(self._viewer_base_href(), quote=True)}' "
            f"data-sheet-key='{html.escape(sheet_key, quote=True)}' "
            f"data-view-label='{html.escape(view_label, quote=True)}' {svg_metadata_attrs}>",
        ]
        parts.extend(self._render_sheet_skin(width=width, height=height))

        # Story lines
        for sz in self.model.stories:
            y = height - margin - (sz - self.min_z) * scale
            parts.append(
                f"<line x1='{margin-10}' y1='{y:.1f}' x2='{width-margin+10}' y2='{y:.1f}' "
                f"stroke='{SVG_DARK_LINE}' stroke-width='0.5' stroke-dasharray='3 3'/>"
            )
            parts.append(
                f"<text x='{margin-14}' y='{y+4:.1f}' text-anchor='end' fill='{SVG_MUTED_ON_DARK}' "
                f"font-size='9'>{sz:.1f}</text>"
            )
            
        if show_dimensions and len(self.model.stories) >= 2:
            mx = margin - 35
            vertical_labels = []
            for i in range(len(self.model.stories)-1):
                sz1, sz2 = self.model.stories[i], self.model.stories[i+1]
                y1, y2 = height - margin - (sz1 - self.min_z) * scale, height - margin - (sz2 - self.min_z) * scale
                val = sz2 - sz1
                parts.append(f"<line x1='{mx}' y1='{y1:.1f}' x2='{mx}' y2='{y2:.1f}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                parts.append(f"<line x1='{mx-3}' y1='{y1:.1f}' x2='{mx+3}' y2='{y1:.1f}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                parts.append(f"<line x1='{mx-3}' y1='{y2:.1f}' x2='{mx+3}' y2='{y2:.1f}' stroke='{SVG_DARK_LINE}' stroke-width='0.8'/>")
                vertical_labels.append((((y1 + y2) / 2) + 3, f"{val:.1f}", mx))
            lanes = self._assign_vertical_label_lanes([center for center, _, _ in vertical_labels])
            for (center, text, mx), lane in zip(vertical_labels, lanes):
                label_x = mx - 4 - lane * 22
                parts.append(
                    f"<text x='{label_x:.1f}' y='{center:.1f}' text-anchor='end' fill='{SVG_MUTED_ON_DARK}' "
                    f"font-size='8' class='dimension-label dimension-label-z' data-dim-axis='z' "
                    f"data-dim-lane='{lane}'>{text}</text>"
                )

        # Elements
        layer_groups = {}
        member_positions: dict[str, tuple[float, float]] = {}
        for el in self.model.elements:
            ns = [self.model.nodes.get(nid) for nid in el.node_ids]
            ns = [n for n in ns if n is not None and filt(n)]
            if len(ns) < 2:
                continue

            etype = el.type.lower()
            if etype not in layer_groups:
                layer_groups[etype] = []
                
            color = self._dcr_color(el.dcr) if show_dcr else TYPE_COLORS.get(etype, "#94a3b8")
            sw = TYPE_STROKE_WIDTH.get(etype, 1.5)

            if etype in ("beam", "column", "brace", "truss") and len(ns) >= 2:
                x1, y1 = txf(ns[0]), tyf(ns[0])
                x2, y2 = txf(ns[1]), tyf(ns[1])
                member_positions[str(el.id)] = ((x1 + x2) / 2, (y1 + y2) / 2)
                element_markup = (
                    f"  <line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                    f"stroke='{color}' stroke-width='{sw}' data-member-id='{el.id}' opacity='0.85'>"
                    f"<title>{el.type} #{el.id} DCR={el.dcr:.3f}</title></line>"
                )
                layer_groups[etype].append(
                    self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                )
            elif etype == "wall" and len(ns) >= 4:
                pts = " ".join(f"{txf(n):.1f},{tyf(n):.1f}" for n in ns)
                member_positions[str(el.id)] = (
                    sum(txf(n) for n in ns) / len(ns),
                    sum(tyf(n) for n in ns) / len(ns),
                )
                element_markup = (
                    f"  <polygon points='{pts}' fill='{color}' fill-opacity='0.3' "
                    f"stroke='{color}' stroke-width='1.5' data-member-id='{el.id}'>"
                    f"<title>Wall #{el.id} DCR={el.dcr:.3f}</title></polygon>"
                )
                layer_groups[etype].append(
                    self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                )
                
        for l_type, l_parts in layer_groups.items():
            if l_parts:
                parts.append(f"<g class='layer-group layer-{l_type}'>")
                parts.extend(l_parts)
                parts.append("</g>")

        callouts = self._callout_specs(sheet_key=sheet_key, view_label=view_label, axis=axis)
        if callouts:
            parts.extend(
                self._render_member_callouts(
                    callouts=callouts,
                    member_positions=member_positions,
                    width=width,
                    height=height,
                    sheet_key=sheet_key,
                    view_label=view_label,
                )
            )

        # Title
        if show_title:
            parts.append(
                f"<text x='{width/2:.1f}' y='24' text-anchor='middle' fill='{SVG_TEXT_ON_DARK}' "
                f"font-size='15' font-weight='700' class='sheet-title'>{view_label}</text>"
            )
        if show_title_block:
            parts.extend(
                self._render_title_block(
                    x=16,
                    y=height - 66,
                    width=260,
                    height=48,
                    view_label=view_label,
                    sheet_code=sheet_code,
                )
            )

        if show_dcr and show_legend:
            parts.extend(self._render_legend(width - 200, height - 35, 160))

        parts.extend(self._render_svg_interactivity(width=width, sheet_key=sheet_key, view_label=view_label))
        parts.append("</svg>")
        return "\n".join(parts)

    # ─── Isometric View ───
    def isometric_view(
        self,
        *,
        width: int = 900,
        height: int = 700,
        show_dcr: bool = True,
        angle_deg: float = 30,
        show_title: bool = True,
        show_title_block: bool = True,
        show_legend: bool = True,
    ) -> str:
        """등각투영 SVG."""
        margin = 80
        ang = math.radians(angle_deg)
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        sheet_key = "isometric"
        sheet_code = "ISO"
        view_label = f"Isometric View — {self.model.name or 'Structure'}"
        title_fields = self._title_block_fields(view_label, sheet_code)
        svg_metadata_attrs = self._svg_sheet_metadata_attributes(fields=title_fields)

        # Isometric projection: u = x*cos - y*cos, v = x*sin + y*sin + z
        def project(x, y, z):
            u = (x - self.min_x) * cos_a - (y - self.min_y) * cos_a * 0.6
            v = -(x - self.min_x) * sin_a - (y - self.min_y) * sin_a * 0.6 - (z - self.min_z)
            return u, v

        # Compute projected bounds
        corners = [
            (self.min_x, self.min_y, self.min_z), (self.max_x, self.min_y, self.min_z),
            (self.min_x, self.max_y, self.min_z), (self.max_x, self.max_y, self.min_z),
            (self.min_x, self.min_y, self.max_z), (self.max_x, self.min_y, self.max_z),
            (self.min_x, self.max_y, self.max_z), (self.max_x, self.max_y, self.max_z),
        ]
        proj = [project(*c) for c in corners]
        pu = [p[0] for p in proj]
        pv = [p[1] for p in proj]
        u_range = max(pu) - min(pu)
        v_range = max(pv) - min(pv)
        scale = min((width - 2 * margin) / max(u_range, 0.1), (height - 2 * margin) / max(v_range, 0.1))
        u_off = margin - min(pu) * scale
        v_off = height - margin - min(pv) * scale  # Flip V

        def tx(x, y, z):
            u, v = project(x, y, z)
            return u_off + u * scale

        def ty(x, y, z):
            u, v = project(x, y, z)
            return v_off + v * scale

        parts = [
            f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' "
            f"role='img' aria-label='Isometric View' class='structural-svg isometric-view' "
            f"style='{self._svg_root_style()}' "
            f"data-viewer-base-url='{html.escape(self._viewer_base_href(), quote=True)}' "
            f"data-sheet-key='{html.escape(sheet_key, quote=True)}' "
            f"data-view-label='{html.escape(view_label, quote=True)}' {svg_metadata_attrs}>",
        ]
        parts.extend(self._render_sheet_skin(width=width, height=height))

        # Render elements (back to front sorting by depth)
        sorted_els = sorted(self.model.elements, key=lambda e: -sum(
            self.model.nodes[nid].x + self.model.nodes[nid].y
            for nid in e.node_ids if nid in self.model.nodes
        ) / max(len(e.node_ids), 1))

        layer_groups = {}
        member_positions: dict[str, tuple[float, float]] = {}
        for el in sorted_els:
            ns = [self.model.nodes.get(nid) for nid in el.node_ids]
            ns = [n for n in ns if n is not None]
            if len(ns) < 2:
                continue

            etype = el.type.lower()
            if etype not in layer_groups: layer_groups[etype] = []
            
            color = self._dcr_color(el.dcr) if show_dcr else TYPE_COLORS.get(etype, "#94a3b8")
            sw = TYPE_STROKE_WIDTH.get(etype, 1.5)

            if etype in ("beam", "column", "brace", "truss"):
                x1, y1 = tx(ns[0].x, ns[0].y, ns[0].z), ty(ns[0].x, ns[0].y, ns[0].z)
                x2, y2 = tx(ns[1].x, ns[1].y, ns[1].z), ty(ns[1].x, ns[1].y, ns[1].z)
                member_positions[str(el.id)] = ((x1 + x2) / 2, (y1 + y2) / 2)
                element_markup = (
                    f"  <line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
                    f"stroke='{color}' stroke-width='{sw}' opacity='0.8' "
                    f"data-member-id='{el.id}' data-type='{etype}'>"
                    f"<title>{el.type} #{el.id} DCR={el.dcr:.3f}</title></line>"
                )
                layer_groups[etype].append(
                    self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                )
            elif etype in ("wall", "slab") and len(ns) >= 4:
                pts = " ".join(f"{tx(n.x,n.y,n.z):.1f},{ty(n.x,n.y,n.z):.1f}" for n in ns)
                opacity = "0.12" if etype == "slab" else "0.25"
                member_positions[str(el.id)] = (
                    sum(tx(n.x, n.y, n.z) for n in ns) / len(ns),
                    sum(ty(n.x, n.y, n.z) for n in ns) / len(ns),
                )
                element_markup = (
                    f"  <polygon points='{pts}' fill='{color}' fill-opacity='{opacity}' "
                    f"stroke='{color}' stroke-width='0.8' stroke-opacity='0.5' "
                    f"data-member-id='{el.id}' data-type='{etype}'>"
                    f"<title>{el.type} #{el.id}</title></polygon>"
                )
                layer_groups[etype].append(
                    self._wrap_member_link(el.id, element_markup, sheet_key=sheet_key, view_label=view_label)
                )
                
        for l_type, l_parts in layer_groups.items():
            if l_parts:
                parts.append(f"<g class='layer-group layer-{l_type}'>")
                parts.extend(l_parts)
                parts.append("</g>")

        callouts = self._callout_specs(sheet_key=sheet_key, view_label=view_label)
        if callouts:
            parts.extend(
                self._render_member_callouts(
                    callouts=callouts,
                    member_positions=member_positions,
                    width=width,
                    height=height,
                    sheet_key=sheet_key,
                    view_label=view_label,
                )
            )

        if show_title:
            parts.append(
                f"<text x='{width/2:.1f}' y='28' text-anchor='middle' fill='{SVG_TEXT_ON_DARK}' "
                f"font-size='15' font-weight='700' class='sheet-title'>{view_label}</text>"
            )
        if show_title_block:
            parts.extend(
                self._render_title_block(
                    x=16,
                    y=height - 66,
                    width=260,
                    height=48,
                    view_label=view_label,
                    sheet_code=sheet_code,
                )
            )

        if show_dcr and show_legend:
            parts.extend(self._render_legend(width - 220, height - 35, 180))

        parts.extend(self._render_svg_interactivity(width=width, sheet_key=sheet_key, view_label=view_label))
        parts.append("</svg>")
        return "\n".join(parts)

    # ─── Legend ───
    def _render_legend(self, x: float, y: float, w: float, h: float = 12) -> list[str]:
        parts = []
        stops = []
        for i in range(11):
            t = i / 10
            color = self.colormap_fn(t)
            stops.append(f"<stop offset='{t*100}%' stop-color='{color}'/>")
        parts.append(
            f"<defs><linearGradient id='lg_dcr' x1='0' y1='0' x2='1' y2='0'>"
            f"{''.join(stops)}</linearGradient></defs>"
        )
        parts.append(
            f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='3' fill='url(#lg_dcr)' stroke='{SVG_DARK_LINE}'/>"
        )
        parts.append(
            f"<text x='{x}' y='{y+h+10}' fill='{SVG_MUTED_ON_DARK}' font-size='9'>{self.dcr_min:.2f}</text>"
        )
        parts.append(
            f"<text x='{x+w}' y='{y+h+10}' text-anchor='end' fill='{SVG_MUTED_ON_DARK}' font-size='9'>{self.dcr_max:.2f}</text>"
        )
        parts.append(
            f"<text x='{x+w/2}' y='{y-4}' text-anchor='middle' fill='{SVG_TEXT_ON_DARK}' font-size='9' font-weight='700'>D/C Ratio</text>"
        )
        return parts

    # ─── Multi-view ───
    def full_drawing_set(
        self,
        *,
        output_dir: str | Path | None = None,
    ) -> dict[str, str]:
        """전체 도면 세트 생성: plan, elevation_x, elevation_y, isometric."""
        result = {}
        # Plan views per story
        for i, sz in enumerate(self.model.stories):
            result[f"plan_z{sz:.1f}"] = self.plan_view(story_z=sz)
        # Elevations
        result["elevation_xz"] = self.elevation_view(axis="x")
        result["elevation_yz"] = self.elevation_view(axis="y")
        # Isometric
        result["isometric"] = self.isometric_view()

        if output_dir:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            for name, svg in result.items():
                (out / f"{name}.svg").write_text(svg, encoding="utf-8")

        return result


# ─── Standalone execution ───
if __name__ == "__main__":
    import sys

    # Generate demo model and output SVGs
    print("Generating demo structural SVG drawings...")

    # Create a simple demo model
    demo = {
        "nodes": [],
        "elements": [],
        "meta": {"name": "Demo 8F RC Structure", "stories": 8},
    }
    nid = 0
    grid = {}
    nx, ny, nstory = 5, 3, 8
    span_x, span_y, story_h = 8.0, 7.0, 3.5
    for s in range(nstory + 1):
        for i in range(nx + 1):
            for j in range(ny + 1):
                demo["nodes"].append({
                    "id": nid, "x": i * span_x, "y": j * span_y, "z": s * story_h,
                    "dx": 0, "dy": 0, "dz": 0,
                })
                grid[f"{i}_{j}_{s}"] = nid
                nid += 1
    import random
    random.seed(42)
    eid = 0
    # Columns
    for s in range(nstory):
        for i in range(nx + 1):
            for j in range(ny + 1):
                n1, n2 = grid.get(f"{i}_{j}_{s}"), grid.get(f"{i}_{j}_{s+1}")
                if n1 is not None and n2 is not None:
                    demo["elements"].append({
                        "id": eid, "type": "column", "node_ids": [n1, n2],
                        "section": "H400x400", "dcr": 0.3 + random.random() * 0.6,
                    })
                    eid += 1
    # Beams X
    for s in range(1, nstory + 1):
        for i in range(nx):
            for j in range(ny + 1):
                n1, n2 = grid.get(f"{i}_{j}_{s}"), grid.get(f"{i+1}_{j}_{s}")
                if n1 is not None and n2 is not None:
                    demo["elements"].append({
                        "id": eid, "type": "beam", "node_ids": [n1, n2],
                        "section": "H500x200", "dcr": 0.2 + random.random() * 0.5,
                    })
                    eid += 1
    # Beams Y
    for s in range(1, nstory + 1):
        for i in range(nx + 1):
            for j in range(ny):
                n1, n2 = grid.get(f"{i}_{j}_{s}"), grid.get(f"{i}_{j+1}_{s}")
                if n1 is not None and n2 is not None:
                    demo["elements"].append({
                        "id": eid, "type": "beam", "node_ids": [n1, n2],
                        "section": "H400x200", "dcr": 0.2 + random.random() * 0.5,
                    })
                    eid += 1

    out_dir = Path(__file__).parent / "output" / "structural_svg"
    gen = StructuralSVGGenerator(demo)
    drawings = gen.full_drawing_set(output_dir=out_dir)
    print(f"Generated {len(drawings)} SVG drawings in {out_dir}")
    for name in drawings:
        print(f"  - {name}.svg")
