# Expert API Quickstart Guide

> Structural Analysis Viewer — Data Format & Integration Guide  
> Version: 1.1 | Date: 2026-05-19

## Overview

This guide describes the data formats used by the Structural Analysis Viewer and how external experts can load, review, and extend the visualization data.

Current integration status:

- Source viewers live under `src/structure-viewer/` and are intended for local QA, evidence review, and deterministic rebuilds.
- Generated release viewers are produced by `implementation/phase1/generate_selfcontained_viewer.py` and must remain self-contained delivery artifacts.
- The project workspace can browse manifest-driven projects/drawings, including MIDAS33 release views and release visualization entries.
- Review packages now preserve selected-member provenance, evidence ingest/import summaries, solver receipt slots, commercial-tool crosswalk rows, lineage drilldown, and SVG sheet/revision/callout viewer deep-links.
- The commercial claim remains `engineer-in-loop commercial assist only` until strict EB/RH external evidence is closed.

---

## 0. Viewer Surfaces

Use the source viewer for development and review:

```text
src/structure-viewer/index.html?project=midas33_release&drawing=midas33_optimized&variant=optimized
```

Use generated single-file viewers for delivery:

```bash
python3 implementation/phase1/generate_selfcontained_viewer.py --preset midas33_optimized --output viewer.html
```

The source/export boundary is documented in `docs/viewer-contract.md` and checked by:

```bash
python3 scripts/verify_structure_viewer_contracts.py --dry-run
node scripts/verify-structure-viewer-project-manifest.mjs
```

## 1. Model Data Format (`model.json`)

The core model data follows a simple JSON schema:

```json
{
  "nodes": [
    {
      "id": 0,
      "x": 0.0, "y": 0.0, "z": 0.0,
      "dx": 0.001, "dy": 0.0005, "dz": -0.0001,
      "disp_mag": 0.00112,
      "stress_vm": 42.5
    }
  ],
  "elements": [
    {
      "id": 0,
      "type": "column",
      "node_ids": [0, 1],
      "section": "H400x400x13x21",
      "dcr": 0.723,
      "axial": -1250.5,
      "moment": 185.3,
      "shear": 67.2
    }
  ],
  "meta": {
    "name": "8F RC Mixed Structure",
    "stories": 8,
    "design_code": "KDS 41 17 00:2022"
  }
}
```

### Node Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `id` | int | — | Unique node identifier |
| `x`, `y`, `z` | float | m | Global coordinates |
| `dx`, `dy`, `dz` | float | m | Displacement (analysis result) |
| `disp_mag` | float | m | Displacement magnitude |
| `stress_vm` | float | MPa | von Mises stress |

### Element Fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| `id` | int | — | Unique element identifier |
| `type` | string | — | `beam`, `column`, `wall`, `slab`, `brace` |
| `node_ids` | int[] | — | Connected node IDs (2 for line, 4 for quad) |
| `section` | string | — | Section designation |
| `dcr` | float | — | Demand/Capacity Ratio (< 1.0 = OK) |
| `axial` | float | kN | Axial force (neg = compression) |
| `moment` | float | kN·m | Bending moment |
| `shear` | float | kN | Shear force |

### Element Types

| Type | Description | Node Count |
|------|-------------|------------|
| `column` | Vertical member | 2 (bottom, top) |
| `beam` | Horizontal member | 2 (start, end) |
| `wall` | Shear wall panel | 4 (quad corners) |
| `slab` | Floor slab panel | 4 (quad corners) |
| `brace` | Diagonal bracing | 2 (start, end) |

---

## 2. Loading Data in Python

```python
import json

with open("demo_5f_rc_office.json", "r", encoding="utf-8") as f:
    model = json.load(f)

# Access nodes and elements
nodes = {n["id"]: n for n in model["nodes"]}
elements = model["elements"]

# Find NG elements (DCR > 1.0)
ng_elements = [e for e in elements if e["dcr"] > 1.0]
print(f"NG count: {len(ng_elements)}")

# Get max displacement
max_disp = max(n["disp_mag"] for n in model["nodes"])
print(f"Max displacement: {max_disp*1000:.2f} mm")

# Filter by type
columns = [e for e in elements if e["type"] == "column"]
beams = [e for e in elements if e["type"] == "beam"]
```

## 3. Loading Data in JavaScript

```javascript
// In browser (Self-contained HTML viewer)
const data = JSON.parse(document.getElementById('model-data').textContent);

// Or via fetch
const response = await fetch('demo_5f_rc_office.json');
const model = await response.json();

// Access
const nodeMap = new Map(model.nodes.map(n => [n.id, n]));
const ngElements = model.elements.filter(e => e.dcr > 1.0);
```

## 4. Generating SVG Drawings

```python
from implementation.phase1.structural_svg_generator import StructuralSVGGenerator

with open("demo_5f_rc_office.json") as f:
    model = json.load(f)

gen = StructuralSVGGenerator(model, colormap="jet")

# Plan view at specific story level
svg_plan = gen.plan_view(story_z=9.9)  # 3rd floor

# Elevation view
svg_elev = gen.elevation_view(axis="x")

# Isometric view
svg_iso = gen.isometric_view()

# Full drawing set → saves SVG files
drawings = gen.full_drawing_set(output_dir="output/drawings")
```

## 5. Generating Self-contained HTML Viewer

```bash
# From demo model
python3 implementation/phase1/generate_selfcontained_viewer.py --demo --output viewer.html

# From custom model JSON
python3 implementation/phase1/generate_selfcontained_viewer.py --input my_model.json --output my_viewer.html

# From a repository artifact preset
python3 implementation/phase1/generate_selfcontained_viewer.py --preset midas33_optimized --output midas33_viewer.html
```

The generated HTML file can be opened directly in any browser — no server required.

## 6. Review Package Fields

Viewer reports and exported HTML/PDF evidence should preserve these review fields when available:

| Field group | Purpose |
|-------------|---------|
| `member`, `load_case`, `combination`, `focus_member` | Shared selection and deep-link restore keys |
| `provenance` | Source path, artifact family, row pointer, and evidence level |
| `solver_receipts` | Solver run/receipt slots used to explain analysis origin |
| `lineage` | Source to analysis to optimization to report trail |
| `commercial_tool_crosswalk` | ETABS/SAP/RFEM/Tekla/Revit-aware member matching and mismatch isolation |
| `drawing_sheet_package` | SVG sheet link, revision, callout id/label, and viewer deep-link |
| `ingest_summary` | Imported JSON/CSV/IFC/MIDAS evidence preview and attachment state |

## 7. Demo Models Available

| Model | Stories | Nodes | Elements | Type |
|-------|---------|-------|----------|------|
| `demo_5f_rc_office.json` | 5 | 120 | 255 | RC Frame |
| `demo_15f_rc_corewall.json` | 15 | 384 | 975 | RC + Core Wall |
| `demo_30f_composite_highrise.json` | 30 | 1,085 | 3,060 | SRC + Wall |

## 8. Design Code Check Report

The `code_check_summary` in each model provides:

```json
{
  "total_members": 255,
  "pass": 250,
  "ng": 5,
  "max_dcr": 1.12,
  "design_code": "KDS 41 17 00:2022"
}
```

## 9. Product Readiness Boundary

For GitHub-facing documentation and external handoff, keep the product claim aligned with the current gate:

```bash
python3 scripts/check_independent_product_readiness.py --json
```

As of 2026-05-19, runtime packaging, production ops/security hardening, support bundle, and viewer workflow packaging are ready. Independent commercial replacement remains blocked at `80/100` because strict EB receipt is `0/4` and RH closure evidence is `0/3`.

---

## Contact

For questions about data formats or integration, refer to `docs/viewer-contract.md`, `docs/structure-viewer-product-workspace.md`, and `docs/architecture-definition-document.md`.
