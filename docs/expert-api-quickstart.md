# Expert API Quickstart Guide

> Structural Analysis Viewer — Data Format & Integration Guide  
> Version: 1.0 | Date: 2026-04-12

## Overview

This guide describes the data formats used by the Structural Analysis Viewer and how external experts can load, review, and extend the visualization data.

---

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
from structural_svg_generator import StructuralSVGGenerator

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
python generate_selfcontained_viewer.py --demo --output viewer.html

# From custom model JSON
python generate_selfcontained_viewer.py --input my_model.json --output my_viewer.html
```

The generated HTML file can be opened directly in any browser — no server required.

## 6. Demo Models Available

| Model | Stories | Nodes | Elements | Type |
|-------|---------|-------|----------|------|
| `demo_5f_rc_office.json` | 5 | 120 | 255 | RC Frame |
| `demo_15f_rc_corewall.json` | 15 | 384 | 975 | RC + Core Wall |
| `demo_30f_composite_highrise.json` | 30 | 1,085 | 3,060 | SRC + Wall |

## 7. Design Code Check Report

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

---

## Contact

For questions about data formats or integration, refer to the project's `docs/architecture-definition-document.md`.
