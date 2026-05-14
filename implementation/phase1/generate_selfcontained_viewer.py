"""
Phase I-4: Self-contained HTML Viewer 생성기

구조 해석 결과를 JSON 데이터 인라인 임베딩된 단독 실행 가능한 HTML 파일로 생성합니다.
외부 전문가에게 배포할 수 있는 완전한 뷰어를 생성합니다.

Usage:
    python generate_selfcontained_viewer.py --input model.json --output viewer.html
    python generate_selfcontained_viewer.py --demo  # 데모 모델로 생성
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import math
import random
import re
import shutil
from pathlib import Path

from implementation.phase1.singlefile_viewer_support import inline_design_theme_stylesheet

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWER_ROOT = REPO_ROOT / "src" / "structure-viewer"
VENDOR_ROOT = VIEWER_ROOT / "vendor"
RELEASE_VISUALIZATION_DIR = REPO_ROOT / "implementation" / "phase1" / "release" / "visualization"
ARTIFACT_PRESET_INPUTS = {
    "midas33": REPO_ROOT / "implementation" / "phase1" / "open_data" / "midas" / "midas_generator_33.json",
    "midas33_pr": REPO_ROOT
    / "implementation"
    / "phase1"
    / "open_data"
    / "midas"
    / "midas_generator_33.pr_recheck.json",
    "midas33_optimized": REPO_ROOT
    / "implementation"
    / "phase1"
    / "open_data"
    / "midas"
    / "midas_generator_33.optimized.roundtrip.json",
}


def generate_demo_model() -> dict:
    """데모용 8층 RC 구조 모델 생성."""
    random.seed(42)
    nodes, elements = [], []
    nx, ny, nstory = 6, 4, 8
    span_x, span_y, story_h = 8.0, 7.0, 3.5
    nid, eid = 0, 0
    grid = {}

    for s in range(nstory + 1):
        for i in range(nx + 1):
            for j in range(ny + 1):
                zr = (s * story_h) / (nstory * story_h)
                dx = (zr ** 2) * 0.08 * (1 + 0.3 * math.sin(i * span_x * 0.2))
                dy = (zr ** 2) * 0.04 * (1 + 0.2 * math.cos(j * span_y * 0.3))
                dz = -zr * 0.01
                nodes.append({
                    "id": nid, "x": i * span_x, "y": j * span_y, "z": s * story_h,
                    "dx": round(dx, 6), "dy": round(dy, 6), "dz": round(dz, 6),
                    "disp_mag": round(math.sqrt(dx**2 + dy**2 + dz**2), 6),
                    "stress_vm": round(20 + zr * 180 + random.random() * 40, 2),
                    "dcr": 0, "axial": 0, "moment": 0, "shear": 0,
                })
                grid[f"{i}_{j}_{s}"] = nid
                nid += 1

    # Columns
    for s in range(nstory):
        for i in range(nx + 1):
            for j in range(ny + 1):
                n1 = grid.get(f"{i}_{j}_{s}")
                n2 = grid.get(f"{i}_{j}_{s+1}")
                if n1 is not None and n2 is not None:
                    elements.append({
                        "id": eid, "type": "column", "node_ids": [n1, n2],
                        "section": "H400x400x13x21",
                        "dcr": round(0.3 + random.random() * 0.6, 3),
                        "axial": round(-500 - random.random() * 2000, 1),
                        "moment": round(50 + random.random() * 300, 1),
                        "shear": round(20 + random.random() * 100, 1),
                    })
                    eid += 1

    # Beams X-dir
    for s in range(1, nstory + 1):
        for i in range(nx):
            for j in range(ny + 1):
                n1 = grid.get(f"{i}_{j}_{s}")
                n2 = grid.get(f"{i+1}_{j}_{s}")
                if n1 is not None and n2 is not None:
                    elements.append({
                        "id": eid, "type": "beam", "node_ids": [n1, n2],
                        "section": "H500x200x10x16",
                        "dcr": round(0.2 + random.random() * 0.5, 3),
                        "axial": round(-10 + random.random() * 50, 1),
                        "moment": round(100 + random.random() * 500, 1),
                        "shear": round(50 + random.random() * 200, 1),
                    })
                    eid += 1

    # Beams Y-dir
    for s in range(1, nstory + 1):
        for i in range(nx + 1):
            for j in range(ny):
                n1 = grid.get(f"{i}_{j}_{s}")
                n2 = grid.get(f"{i}_{j+1}_{s}")
                if n1 is not None and n2 is not None:
                    elements.append({
                        "id": eid, "type": "beam", "node_ids": [n1, n2],
                        "section": "H400x200x8x13",
                        "dcr": round(0.2 + random.random() * 0.5, 3),
                        "axial": round(-5 + random.random() * 30, 1),
                        "moment": round(80 + random.random() * 400, 1),
                        "shear": round(40 + random.random() * 150, 1),
                    })
                    eid += 1

    # Core walls
    cx, cy = nx // 2, ny // 2
    for s in range(nstory):
        bl = grid.get(f"{cx}_{cy}_{s}")
        br = grid.get(f"{cx+1}_{cy}_{s}")
        tl = grid.get(f"{cx}_{cy}_{s+1}")
        tr = grid.get(f"{cx+1}_{cy}_{s+1}")
        if all(v is not None for v in [bl, br, tl, tr]):
            elements.append({
                "id": eid, "type": "wall", "node_ids": [bl, br, tr, tl],
                "section": "W300",
                "dcr": round(0.15 + random.random() * 0.3, 3),
                "axial": round(-1000 - random.random() * 3000, 1),
                "moment": round(200 + random.random() * 800, 1),
                "shear": round(100 + random.random() * 400, 1),
            })
            eid += 1

    return {
        "nodes": nodes,
        "elements": elements,
        "meta": {
            "name": "8F RC Mixed Structure Demo",
            "stories": nstory, "spans_x": nx, "spans_y": ny,
            "span_x_m": span_x, "span_y_m": span_y, "story_h_m": story_h,
            "generated_by": "generate_selfcontained_viewer.py",
        },
    }


def generate_selfcontained_html(model_data: dict) -> str:
    """모델 데이터를 인라인 임베딩한 Self-contained HTML을 생성합니다."""
    three_import_url, orbit_controls_import_url = build_inline_vendor_import_urls()

    # Read the 3D viewer HTML template
    viewer_html_path = VIEWER_ROOT / "index.html"

    if viewer_html_path.exists():
        html_content = viewer_html_path.read_text(encoding="utf-8")
        html_content = _remove_sidecar_data_bootstrap(html_content)
        html_content = _remove_importmap_bootstrap(html_content)
        html_content = inline_design_theme_stylesheet(html_content)
        html_content = _inline_vendor_module_imports(
            html_content,
            three_import_url=three_import_url,
            orbit_controls_import_url=orbit_controls_import_url,
        )
        viewer_module_import_urls = _build_inline_viewer_module_import_urls()
        html_content = _inline_local_viewer_module_imports(html_content, viewer_module_import_urls)
        html_content = _inline_viewer_worker_module_urls(html_content, viewer_module_import_urls)
        embedded_json = json.dumps(model_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

        # Inline JSON is preferred by the viewer when opened over file://
        injection = f"""
<script type="application/json" id="embedded-model-data">
{embedded_json}
</script>
"""
        html_content = html_content.replace("</body>", f"{injection}\n</body>")
        return _mark_structural_singlefile_html(html_content)

    return _mark_structural_singlefile_html(_render_premium_dark_fallback_viewer_html(
        model_data,
        three_import_url=three_import_url,
        orbit_controls_import_url=orbit_controls_import_url,
    ))


def _render_premium_dark_fallback_viewer_html(
    model_data: dict,
    *,
    three_import_url: str,
    orbit_controls_import_url: str,
) -> str:
    """Render the standalone fallback shell using the shared dark review family."""

    meta = model_data.get("meta", {}) if isinstance(model_data, dict) else {}
    title = str(meta.get("name") or "Structure")
    node_count = len(model_data.get("nodes", [])) if isinstance(model_data, dict) else 0
    element_count = len(model_data.get("elements", [])) if isinstance(model_data, dict) else 0
    story_value = meta.get("stories")
    if isinstance(story_value, int):
        story_label = f"{story_value}F"
    elif isinstance(story_value, float) and story_value.is_integer():
        story_label = f"{int(story_value)}F"
    elif story_value not in (None, ""):
        story_label = str(story_value)
    else:
        story_label = "--"

    escaped_title = html.escape(title, quote=True)
    escaped_lede = html.escape(
        "Portable geometry-review shell for offline handoff, evidence capture, and file-safe sharing.",
        quote=True,
    )
    escaped_story_label = html.escape(story_label, quote=True)
    model_json = json.dumps(model_data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    template = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Structural Analysis Review Desk — __TITLE__</title>
<style>
*{box-sizing:border-box}
html,body{height:100%}
body{
margin:0;
overflow:hidden;
color:#ecf2f6;
font-family:'IBM Plex Sans KR','Pretendard','Noto Sans KR',sans-serif;
background:
radial-gradient(circle at 12% 8%, rgba(79,183,173,.16), transparent 24%),
radial-gradient(circle at 84% 12%, rgba(244,181,107,.12), transparent 20%),
radial-gradient(circle at 50% -12%, rgba(255,255,255,.06), transparent 30%),
linear-gradient(180deg,#07111c 0%,#0b1621 44%,#111c29 100%);
position:relative
}
body::before{
content:'';
position:fixed;
inset:0;
pointer-events:none;
opacity:.22;
background-image:
linear-gradient(rgba(255,255,255,.04) 1px, transparent 1px),
linear-gradient(90deg, rgba(255,255,255,.04) 1px, transparent 1px);
background-size:30px 30px;
mask-image:radial-gradient(circle at center, black 24%, transparent 84%)
}
canvas{
position:fixed;
inset:0;
width:100%!important;
height:100%!important;
display:block;
background:
radial-gradient(circle at 18% 16%, rgba(79,183,173,.08), transparent 18%),
radial-gradient(circle at 82% 14%, rgba(244,181,107,.06), transparent 15%),
linear-gradient(180deg,#08121d 0%,#0b1621 45%,#111c29 100%)
}
#info{
position:fixed;
top:14px;
left:14px;
width:min(390px, calc(100vw - 28px));
max-height:calc(100vh - 28px);
z-index:10;
padding:16px 18px 18px;
border-radius:26px;
border:1px solid rgba(148,168,190,.18);
background:
linear-gradient(180deg, rgba(18,30,44,.94), rgba(12,22,33,.92)),
rgba(17,28,41,.88);
box-shadow:0 24px 60px rgba(0,0,0,.28);
backdrop-filter:blur(18px);
-webkit-backdrop-filter:blur(18px);
display:flex;
flex-direction:column;
gap:14px;
pointer-events:none;
user-select:none
}
#info::before{
content:'';
position:absolute;
left:18px;
right:18px;
top:0;
height:2px;
background:linear-gradient(90deg, rgba(79,183,173,0), rgba(79,183,173,.56), rgba(244,181,107,.48), rgba(79,183,173,0))
}
#info .eyebrow{
margin:0;
color:#96a8bb;
font-size:11px;
font-weight:700;
letter-spacing:.12em;
text-transform:uppercase
}
#info h2{
margin:0;
font-family:'Space Grotesk','IBM Plex Sans KR',sans-serif;
color:#ecf2f6;
font-size:clamp(24px,4vw,32px);
line-height:1.02;
letter-spacing:-.04em
}
#info .lede{
margin:0;
color:#96a8bb;
font-size:13px;
line-height:1.55
}
#info .stats{
display:grid;
grid-template-columns:repeat(2,minmax(0,1fr));
gap:10px
}
#info .stat{
padding:12px 13px 11px;
border-radius:18px;
border:1px solid rgba(148,168,190,.16);
background:
linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.015)),
rgba(10,18,29,.56);
box-shadow:inset 0 1px 0 rgba(255,255,255,.03)
}
#info .stat span{
display:block;
margin-bottom:4px;
color:#96a8bb;
font-size:10px;
font-weight:700;
letter-spacing:.12em;
text-transform:uppercase
}
#info .stat strong{
display:block;
color:#ecf2f6;
font-family:'Space Grotesk','IBM Plex Sans KR',sans-serif;
font-size:22px;
line-height:1;
letter-spacing:-.03em
}
#info .chips{
display:flex;
flex-wrap:wrap;
gap:8px
}
#info .chip{
display:inline-flex;
align-items:center;
min-height:32px;
padding:8px 12px;
border-radius:999px;
border:1px solid rgba(148,168,190,.18);
background:
linear-gradient(180deg, rgba(255,255,255,.05), rgba(255,255,255,.02)),
rgba(14,24,35,.58);
color:#ecf2f6;
font-size:12px;
line-height:1
}
#info .chip-primary{
border-color:rgba(79,183,173,.38);
background:linear-gradient(135deg, rgba(79,183,173,.22), rgba(79,183,173,.10))
}
#info .chip-warm{
border-color:rgba(244,181,107,.36);
background:linear-gradient(135deg, rgba(244,181,107,.20), rgba(244,181,107,.08))
}
#info .footer-note{
margin:0;
padding-left:10px;
border-left:2px solid rgba(79,183,173,.52);
color:#96a8bb;
font-size:12px;
line-height:1.45
}
@media (max-width:520px){
#info{
left:10px;
top:10px;
width:calc(100vw - 20px);
padding:14px
}
#info .stats{
grid-template-columns:1fr
}
}
</style>
</head>
<body>
<div id="info" role="status" aria-live="polite">
  <div class="eyebrow">Structural review / demo shell</div>
  <h2>__TITLE__</h2>
  <p class="lede">__LEDE__</p>
  <div class="stats">
    <div class="stat"><span>Nodes</span><strong>__NODE_COUNT__</strong></div>
    <div class="stat"><span>Elements</span><strong>__ELEMENT_COUNT__</strong></div>
    <div class="stat"><span>Stories</span><strong>__STORY_COUNT__</strong></div>
    <div class="stat"><span>Mode</span><strong>Offline</strong></div>
  </div>
  <div class="chips">
    <span class="chip chip-primary">Teal review</span>
    <span class="chip">Warm brass</span>
    <span class="chip chip-warm">Single-file ready</span>
  </div>
  <p class="footer-note">Open the full 3D viewer HTML for interactive visualization.</p>
</div>
<script type="application/json" id="model-data">__MODEL_JSON__</script>
<script type="module">
import*as THREE from'__THREE_IMPORT_URL__';
import{OrbitControls}from'__ORBIT_CONTROLS_URL__';
const data=JSON.parse(document.getElementById('model-data').textContent);
const scene=new THREE.Scene();scene.background=new THREE.Color(0x08121d);
const cam=new THREE.PerspectiveCamera(50,innerWidth/innerHeight,.1,2000);
cam.position.set(80,60,80);
const r=new THREE.WebGLRenderer({antialias:true});r.setSize(innerWidth,innerHeight);
r.setPixelRatio(Math.min(devicePixelRatio,2));document.body.appendChild(r.domElement);
const ctrl=new OrbitControls(cam,r.domElement);ctrl.enableDamping=true;
scene.add(new THREE.AmbientLight(0x31465a,.7));
const d=new THREE.DirectionalLight(0xf7f1e8,1.1);d.position.set(60,80,40);scene.add(d);
const nm=new Map();data.nodes.forEach(n=>nm.set(n.id,n));
const C={beam:0x4fb7ad,column:0xf4b56b,wall:0x96a8bb};
data.elements.forEach(el=>{
const ns=el.node_ids.map(id=>nm.get(id)).filter(Boolean);if(ns.length<2)return;
const t=el.type.toLowerCase(),c=C[t]||0x94a3b8;
if(t==='beam'||t==='column'){
const pts=ns.map(n=>new THREE.Vector3(n.x,n.z,n.y));
const geo=new THREE.BufferGeometry().setFromPoints(pts);
scene.add(new THREE.Line(geo,new THREE.LineBasicMaterial({color:c})));
}else if(t==='wall'&&ns.length>=4){
const v=ns.map(n=>new THREE.Vector3(n.x,n.z,n.y));
const geo=new THREE.BufferGeometry();
const p=new Float32Array([v[0].x,v[0].y,v[0].z,v[1].x,v[1].y,v[1].z,v[2].x,v[2].y,v[2].z,v[0].x,v[0].y,v[0].z,v[2].x,v[2].y,v[2].z,v[3].x,v[3].y,v[3].z]);
geo.setAttribute('position',new THREE.BufferAttribute(p,3));geo.computeVertexNormals();
scene.add(new THREE.Mesh(geo,new THREE.MeshPhongMaterial({color:c,transparent:true,opacity:.4,side:THREE.DoubleSide})));
}});
const box=new THREE.Box3().setFromObject(scene);const ctr=box.getCenter(new THREE.Vector3());
ctrl.target.copy(ctr);cam.position.copy(ctr).add(new THREE.Vector3(50,35,50));
(function anim(){requestAnimationFrame(anim);ctrl.update();r.render(scene,cam)})();
addEventListener('resize',()=>{cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix();r.setSize(innerWidth,innerHeight)});
</script>
</body>
</html>"""

    return (
        template.replace("__TITLE__", escaped_title)
        .replace("__LEDE__", escaped_lede)
        .replace("__NODE_COUNT__", f"{node_count:,}")
        .replace("__ELEMENT_COUNT__", f"{element_count:,}")
        .replace("__STORY_COUNT__", escaped_story_label)
        .replace("__THREE_IMPORT_URL__", three_import_url)
        .replace("__ORBIT_CONTROLS_URL__", orbit_controls_import_url)
        .replace("__MODEL_JSON__", model_json)
    )


def _remove_sidecar_data_bootstrap(html_content: str) -> str:
    """Remove template-side data bootstrap when embedded JSON is present."""

    return re.sub(
        r"\s*<script\s+src=[\"'](?:\./)?index\.data\.js[\"']\s*>\s*</script>\s*",
        "\n",
        html_content,
        count=1,
    )


def _remove_importmap_bootstrap(html_content: str) -> str:
    """Remove template-side importmaps so the generated HTML stays single-file."""

    return re.sub(
        r"\s*<script\s+type=[\"']importmap[\"']\s*>.*?</script>\s*",
        "\n",
        html_content,
        count=1,
        flags=re.DOTALL,
    )


def _encode_js_module_data_url(module_source: str) -> str:
    encoded = base64.b64encode(module_source.encode("utf-8")).decode("ascii")
    return f"data:text/javascript;base64,{encoded}"


def _mark_structural_singlefile_html(html_content: str) -> str:
    marker = "window.__STRUCTURAL_SINGLEFILE__=true;"
    if marker in html_content:
        return html_content
    return html_content.replace("</head>", f"<script>{marker}</script>\n</head>", 1)


def _build_inline_viewer_module_import_urls() -> dict[str, str]:
    """Return data-URL module imports for local viewer helpers used by index.html."""

    data_loader_url = _encode_js_module_data_url((VIEWER_ROOT / "viewer-data-loader.js").read_text(encoding="utf-8"))
    model_normalizer_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-model-normalizer.js").read_text(encoding="utf-8")
    )
    direct_normalizer_source = (VIEWER_ROOT / "viewer-direct-model-normalizer.js").read_text(encoding="utf-8")
    direct_normalizer_source = direct_normalizer_source.replace(
        "from './viewer-model-normalizer.js';",
        f"from '{model_normalizer_url}';",
    )
    direct_normalizer_url = _encode_js_module_data_url(direct_normalizer_source)
    render_picking_geometry_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-render-picking-geometry.js").read_text(encoding="utf-8")
    )
    large_model_picking_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-large-model-picking.js").read_text(encoding="utf-8")
    )
    pick_broadphase_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-pick-broadphase.js").read_text(encoding="utf-8")
    )
    render_mesh_builders_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-render-mesh-builders.js").read_text(encoding="utf-8")
    )
    contour_materials_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-contour-materials.js").read_text(encoding="utf-8")
    )
    deformed_rendering_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-deformed-rendering.js").read_text(encoding="utf-8")
    )
    real_drawing_browser_state_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-real-drawing-browser-state.js").read_text(encoding="utf-8")
    )
    real_drawing_quality_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-real-drawing-quality.js").read_text(encoding="utf-8")
    )
    shared_selection_state_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-shared-selection-state.js").read_text(encoding="utf-8")
    )
    real_drawing_selection_source = (VIEWER_ROOT / "viewer-real-drawing-selection.js").read_text(encoding="utf-8")
    real_drawing_selection_source = real_drawing_selection_source.replace(
        "from './viewer-real-drawing-quality.js';",
        f"from '{real_drawing_quality_url}';",
    )
    real_drawing_selection_source = real_drawing_selection_source.replace(
        "from './viewer-shared-selection-state.js';",
        f"from '{shared_selection_state_url}';",
    )
    real_drawing_selection_url = _encode_js_module_data_url(real_drawing_selection_source)
    stats_summary_source = (VIEWER_ROOT / "viewer-stats-summary.js").read_text(encoding="utf-8")
    stats_summary_source = stats_summary_source.replace(
        "from './viewer-real-drawing-quality.js';",
        f"from '{real_drawing_quality_url}';",
    )
    stats_summary_url = _encode_js_module_data_url(stats_summary_source)
    real_drawing_panel_renderer_source = (VIEWER_ROOT / "viewer-real-drawing-panel-renderer.js").read_text(
        encoding="utf-8"
    )
    real_drawing_panel_renderer_source = real_drawing_panel_renderer_source.replace(
        "from './viewer-real-drawing-quality.js';",
        f"from '{real_drawing_quality_url}';",
    )
    real_drawing_panel_renderer_url = _encode_js_module_data_url(real_drawing_panel_renderer_source)
    real_drawing_panel_model_source = (VIEWER_ROOT / "viewer-real-drawing-panel-model.js").read_text(
        encoding="utf-8"
    )
    real_drawing_panel_model_source = real_drawing_panel_model_source.replace(
        "from './viewer-real-drawing-quality.js';",
        f"from '{real_drawing_quality_url}';",
    )
    real_drawing_panel_model_url = _encode_js_module_data_url(real_drawing_panel_model_source)
    real_drawing_panel_events_source = (VIEWER_ROOT / "viewer-real-drawing-panel-events.js").read_text(
        encoding="utf-8"
    )
    real_drawing_panel_events_source = real_drawing_panel_events_source.replace(
        "from './viewer-real-drawing-quality.js';",
        f"from '{real_drawing_quality_url}';",
    )
    real_drawing_panel_events_url = _encode_js_module_data_url(real_drawing_panel_events_source)
    real_drawing_tree_model_source = (VIEWER_ROOT / "viewer-real-drawing-tree-model.js").read_text(
        encoding="utf-8"
    )
    real_drawing_tree_model_source = real_drawing_tree_model_source.replace(
        "from './viewer-real-drawing-quality.js';",
        f"from '{real_drawing_quality_url}';",
    )
    real_drawing_tree_model_url = _encode_js_module_data_url(real_drawing_tree_model_source)
    side_panel_model_url = _encode_js_module_data_url(
        (VIEWER_ROOT / "viewer-side-panel-model.js").read_text(encoding="utf-8")
    )
    search_results_model_source = (VIEWER_ROOT / "viewer-search-results-model.js").read_text(encoding="utf-8")
    search_results_model_source = search_results_model_source.replace(
        "from './viewer-shared-selection-state.js';",
        f"from '{shared_selection_state_url}';",
    )
    search_results_model_url = _encode_js_module_data_url(search_results_model_source)
    selection_summary_model_source = (VIEWER_ROOT / "viewer-selection-summary-model.js").read_text(encoding="utf-8")
    selection_summary_model_source = selection_summary_model_source.replace(
        "from './viewer-shared-selection-state.js';",
        f"from '{shared_selection_state_url}';",
    )
    selection_summary_model_url = _encode_js_module_data_url(selection_summary_model_source)
    return {
        "./viewer-data-loader.js": data_loader_url,
        "./viewer-model-normalizer.js": model_normalizer_url,
        "./viewer-direct-model-normalizer.js": direct_normalizer_url,
        "./viewer-render-picking-geometry.js": render_picking_geometry_url,
        "./viewer-large-model-picking.js": large_model_picking_url,
        "./viewer-pick-broadphase.js": pick_broadphase_url,
        "./viewer-render-mesh-builders.js": render_mesh_builders_url,
        "./viewer-contour-materials.js": contour_materials_url,
        "./viewer-deformed-rendering.js": deformed_rendering_url,
        "./viewer-real-drawing-browser-state.js": real_drawing_browser_state_url,
        "./viewer-real-drawing-quality.js": real_drawing_quality_url,
        "./viewer-shared-selection-state.js": shared_selection_state_url,
        "./viewer-real-drawing-selection.js": real_drawing_selection_url,
        "./viewer-stats-summary.js": stats_summary_url,
        "./viewer-real-drawing-panel-renderer.js": real_drawing_panel_renderer_url,
        "./viewer-real-drawing-panel-model.js": real_drawing_panel_model_url,
        "./viewer-real-drawing-panel-events.js": real_drawing_panel_events_url,
        "./viewer-real-drawing-tree-model.js": real_drawing_tree_model_url,
        "./viewer-side-panel-model.js": side_panel_model_url,
        "./viewer-search-results-model.js": search_results_model_url,
        "./viewer-selection-summary-model.js": selection_summary_model_url,
    }


def build_inline_vendor_import_urls() -> tuple[str, str]:
    """Return data-URL module imports for Three.js and OrbitControls."""

    three_source = (VENDOR_ROOT / "three.module.js").read_text(encoding="utf-8")
    three_import_url = _encode_js_module_data_url(three_source)

    orbit_source = (VENDOR_ROOT / "OrbitControls.js").read_text(encoding="utf-8")
    orbit_source = orbit_source.replace(
        "from './three.module.js';",
        f"from '{three_import_url}';",
    )
    orbit_controls_import_url = _encode_js_module_data_url(orbit_source)
    return three_import_url, orbit_controls_import_url


def _inline_vendor_module_imports(
    html_content: str,
    *,
    three_import_url: str,
    orbit_controls_import_url: str,
) -> str:
    html_content, three_count = re.subn(
        r"import\s+\*\s+as\s+THREE\s+from\s+['\"]\.\/vendor\/three\.module\.js['\"];",
        f"import * as THREE from '{three_import_url}';",
        html_content,
        count=1,
    )
    html_content, orbit_count = re.subn(
        r"import\s+\{\s*OrbitControls\s*\}\s+from\s+['\"]\.\/vendor\/OrbitControls\.js['\"];",
        f"import {{OrbitControls}} from '{orbit_controls_import_url}';",
        html_content,
        count=1,
    )
    if three_count != 1 or orbit_count != 1:
        raise RuntimeError("Failed to inline viewer vendor module imports from the template HTML")
    return html_content


def _inline_local_viewer_module_imports(html_content: str, module_import_urls: dict[str, str]) -> str:
    """Inline local helper ESM imports so generated viewer HTML remains single-file."""

    for module_path, module_url in module_import_urls.items():
        html_content, replacement_count = re.subn(
            rf"from\s+['\"]{re.escape(module_path)}['\"];",
            f"from '{module_url}';",
            html_content,
            count=1,
        )
        if replacement_count != 1:
            raise RuntimeError(f"Failed to inline viewer module import: {module_path}")
    return html_content


def _inline_viewer_worker_module_urls(html_content: str, module_import_urls: dict[str, str]) -> str:
    """Inline module URLs consumed by the Blob module worker in single-file output."""

    replacements = {
        "modelNormalizer: new URL('./viewer-model-normalizer.js', import.meta.url).href,": (
            f"modelNormalizer: {json.dumps(module_import_urls['./viewer-model-normalizer.js'])},"
        ),
        "directModelNormalizer: new URL('./viewer-direct-model-normalizer.js', import.meta.url).href,": (
            f"directModelNormalizer: {json.dumps(module_import_urls['./viewer-direct-model-normalizer.js'])},"
        ),
    }
    for needle, replacement in replacements.items():
        if needle not in html_content:
            raise RuntimeError(f"Failed to inline viewer worker module URL: {needle}")
        html_content = html_content.replace(needle, replacement, 1)
    return html_content


def ensure_local_vendor_bundle(output_html_path: Path) -> list[Path]:
    """Copy local viewer vendor assets next to the generated HTML when needed."""

    vendor_src = VENDOR_ROOT
    if not vendor_src.exists():
        return []

    vendor_dst = output_html_path.resolve().parent / "vendor"
    vendor_dst.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for name in ("three.module.js", "OrbitControls.js"):
        src = vendor_src / name
        if not src.exists():
            continue
        dst = vendor_dst / name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def extract_viewer_model_payload(model_data: dict) -> dict:
    """Return the actual viewer model payload even when wrapped in an artifact envelope."""

    if isinstance(model_data, dict):
        nested = model_data.get("model")
        if isinstance(nested, dict) and isinstance(nested.get("nodes"), list) and isinstance(nested.get("elements"), list):
            return nested
        if isinstance(model_data.get("nodes"), list) and isinstance(model_data.get("elements"), list):
            return model_data
    return {}


def summarize_model_data(model_data: dict) -> tuple[int, int]:
    payload = extract_viewer_model_payload(model_data)
    return len(payload.get("nodes", [])), len(payload.get("elements", []))


def load_model_data(*, input_path: str | None, preset: str | None, demo: bool) -> tuple[dict, str]:
    """Load demo data, an explicit input JSON, or a checked-in artifact preset."""

    normalized_preset = str(preset or "").strip()
    if input_path and normalized_preset:
        raise ValueError("--input and --preset cannot be used together")

    if demo or (not input_path and not normalized_preset):
        return generate_demo_model(), "demo"

    if normalized_preset:
        artifact_path = ARTIFACT_PRESET_INPUTS.get(normalized_preset)
        if artifact_path is None:
            raise ValueError(f"unknown preset: {normalized_preset}")
        return json.loads(artifact_path.read_text(encoding="utf-8")), str(artifact_path.relative_to(REPO_ROOT))

    input_file = Path(str(input_path))
    return json.loads(input_file.read_text(encoding="utf-8")), str(input_file)


def resolve_generation_source(
    *,
    input_path: str | None,
    preset: str | None,
    demo: bool,
    release_artifact: bool,
) -> tuple[str | None, str | None, bool]:
    """Resolve the effective source flags for viewer generation."""

    if release_artifact and not input_path and not preset and not demo:
        return None, "midas33", False
    return input_path, preset, demo


def main():
    parser = argparse.ArgumentParser(description="Self-contained structural viewer generator")
    parser.add_argument("--input", "-i", type=str, help="Input model JSON file")
    parser.add_argument("--preset", choices=sorted(ARTIFACT_PRESET_INPUTS), help="Embed a repo artifact preset")
    parser.add_argument("--output", "-o", type=str, help="Output HTML file")
    parser.add_argument("--demo", action="store_true", help="Generate with demo model")
    parser.add_argument(
        "--release-artifact",
        action="store_true",
        help="Write implementation/phase1/release/visualization/structural_viewer_singlefile.html using the selected input or preset",
    )
    parser.add_argument(
        "--copy-vendor-sidecar",
        action="store_true",
        help="Copy repo-local vendor JS next to the output HTML for compatibility checks",
    )
    args = parser.parse_args()

    input_path, preset, demo = resolve_generation_source(
        input_path=args.input,
        preset=args.preset,
        demo=bool(args.demo),
        release_artifact=bool(args.release_artifact),
    )
    model_data, source_label = load_model_data(input_path=input_path, preset=preset, demo=demo)
    if source_label == "demo":
        print("Generating demo model...")
    else:
        print(f"Loading model from {source_label}...")

    html_content = generate_selfcontained_html(model_data)

    output_path = (
        RELEASE_VISUALIZATION_DIR / "structural_viewer_singlefile.html"
        if args.release_artifact
        else Path(args.output or "structural_viewer.html")
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    copied_assets = ensure_local_vendor_bundle(output_path) if args.copy_vendor_sidecar else []
    node_count, element_count = summarize_model_data(model_data)
    print(f"Generated self-contained viewer: {output_path}")
    print(f"  Nodes: {node_count}")
    print(f"  Elements: {element_count}")
    print(f"  Size: {len(html_content) / 1024:.1f} KB")
    if copied_assets:
        print("  Vendor bundle:")
        for path in copied_assets:
            print(f"    - {path}")


if __name__ == "__main__":
    main()
