"""
Phase III-1: 다중 데모 모델 데이터셋 생성기

외부 전문가 제공용 합성 데모 모델 3종을 생성합니다:
  - 5F RC Rahmen (저층 사무실)
  - 15F RC Core-Wall (중층 주거)
  - 30F Composite High-Rise (고층 복합)

Usage:
    python generate_demo_datasets.py
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any


def _make_grid(nx: int, ny: int, nstory: int, span_x: float, span_y: float, story_h: float) -> tuple[list, dict]:
    nodes, grid = [], {}
    nid = 0
    for s in range(nstory + 1):
        for i in range(nx + 1):
            for j in range(ny + 1):
                z = s * story_h
                zr = z / (nstory * story_h) if nstory > 0 else 0
                dx = (zr ** 2) * 0.06 * (1 + 0.3 * math.sin(i * 0.5))
                dy = (zr ** 2) * 0.04 * (1 + 0.2 * math.cos(j * 0.4))
                nodes.append({
                    "id": nid, "x": round(i * span_x, 2), "y": round(j * span_y, 2), "z": round(z, 2),
                    "dx": round(dx, 6), "dy": round(dy, 6), "dz": round(-zr * 0.008, 6),
                    "disp_mag": round(math.sqrt(dx**2 + dy**2 + (zr*0.008)**2), 6),
                    "stress_vm": round(20 + zr * 150 + random.random() * 30, 2),
                })
                grid[f"{i}_{j}_{s}"] = nid
                nid += 1
    return nodes, grid


def _add_columns(elements: list, grid: dict, nx: int, ny: int, nstory: int, eid: int) -> int:
    for s in range(nstory):
        for i in range(nx + 1):
            for j in range(ny + 1):
                n1, n2 = grid.get(f"{i}_{j}_{s}"), grid.get(f"{i}_{j}_{s+1}")
                if n1 is not None and n2 is not None:
                    elements.append({
                        "id": eid, "type": "column", "node_ids": [n1, n2],
                        "section": "H400x400x13x21",
                        "dcr": round(0.25 + random.random() * 0.65, 3),
                        "axial": round(-400 - random.random() * 2500, 1),
                        "moment": round(40 + random.random() * 350, 1),
                        "shear": round(15 + random.random() * 120, 1),
                    })
                    eid += 1
    return eid


def _add_beams(elements: list, grid: dict, nx: int, ny: int, nstory: int, eid: int) -> int:
    for s in range(1, nstory + 1):
        for i in range(nx):
            for j in range(ny + 1):
                n1, n2 = grid.get(f"{i}_{j}_{s}"), grid.get(f"{i+1}_{j}_{s}")
                if n1 is not None and n2 is not None:
                    elements.append({
                        "id": eid, "type": "beam", "node_ids": [n1, n2],
                        "section": "H500x200x10x16",
                        "dcr": round(0.15 + random.random() * 0.55, 3),
                        "axial": round(-5 + random.random() * 40, 1),
                        "moment": round(80 + random.random() * 500, 1),
                        "shear": round(30 + random.random() * 200, 1),
                    })
                    eid += 1
        for i in range(nx + 1):
            for j in range(ny):
                n1, n2 = grid.get(f"{i}_{j}_{s}"), grid.get(f"{i}_{j+1}_{s}")
                if n1 is not None and n2 is not None:
                    elements.append({
                        "id": eid, "type": "beam", "node_ids": [n1, n2],
                        "section": "H400x200x8x13",
                        "dcr": round(0.15 + random.random() * 0.5, 3),
                        "axial": round(-3 + random.random() * 25, 1),
                        "moment": round(60 + random.random() * 400, 1),
                        "shear": round(20 + random.random() * 150, 1),
                    })
                    eid += 1
    return eid


def generate_5f_rc() -> dict:
    """5F RC Rahmen 저층 사무실."""
    random.seed(101)
    nx, ny, ns = 4, 3, 5
    nodes, grid = _make_grid(nx, ny, ns, 8.0, 7.0, 3.3)
    elements = []
    eid = _add_columns(elements, grid, nx, ny, ns, 0)
    eid = _add_beams(elements, grid, nx, ny, ns, eid)
    return {
        "nodes": nodes, "elements": elements,
        "meta": {"name": "5F RC Rahmen Office", "stories": ns, "type": "RC",
                 "total_area_m2": (nx * 8) * (ny * 7) * ns, "location": "Seoul, KR"},
        "code_check_summary": {
            "total_members": len(elements),
            "pass": sum(1 for e in elements if e["dcr"] <= 1.0),
            "ng": sum(1 for e in elements if e["dcr"] > 1.0),
            "max_dcr": max(e["dcr"] for e in elements),
            "design_code": "KDS 41 17 00:2022",
        },
    }


def generate_15f_rc_corewall() -> dict:
    """15F RC Core-Wall 중층 주거."""
    random.seed(202)
    nx, ny, ns = 5, 3, 15
    nodes, grid = _make_grid(nx, ny, ns, 8.0, 7.5, 3.0)
    elements = []
    eid = _add_columns(elements, grid, nx, ny, ns, 0)
    eid = _add_beams(elements, grid, nx, ny, ns, eid)
    # Core walls
    cx, cy = nx // 2, ny // 2
    for s in range(ns):
        for di, dj in [(0, 0), (1, 0), (0, 1)]:
            bl = grid.get(f"{cx+di}_{cy+dj}_{s}")
            br = grid.get(f"{cx+di+1}_{cy+dj}_{s}")
            tl = grid.get(f"{cx+di}_{cy+dj}_{s+1}")
            tr = grid.get(f"{cx+di+1}_{cy+dj}_{s+1}")
            if all(v is not None for v in [bl, br, tl, tr]):
                elements.append({
                    "id": eid, "type": "wall", "node_ids": [bl, br, tr, tl],
                    "section": "W350", "dcr": round(0.1 + random.random() * 0.35, 3),
                    "axial": round(-800 - random.random() * 4000, 1),
                    "moment": round(150 + random.random() * 1000, 1),
                    "shear": round(80 + random.random() * 500, 1),
                })
                eid += 1
    return {
        "nodes": nodes, "elements": elements,
        "meta": {"name": "15F RC Core-Wall Residential", "stories": ns, "type": "RC+Wall",
                 "total_area_m2": (nx * 8) * (ny * 7.5) * ns, "location": "Seoul, KR"},
        "code_check_summary": {
            "total_members": len(elements),
            "pass": sum(1 for e in elements if e["dcr"] <= 1.0),
            "ng": sum(1 for e in elements if e["dcr"] > 1.0),
            "max_dcr": max(e["dcr"] for e in elements),
            "design_code": "KDS 41 17 00:2022",
        },
    }


def generate_30f_composite() -> dict:
    """30F Composite High-Rise."""
    random.seed(303)
    nx, ny, ns = 6, 4, 30
    nodes, grid = _make_grid(nx, ny, ns, 9.0, 8.0, 3.5)
    elements = []
    eid = _add_columns(elements, grid, nx, ny, ns, 0)
    eid = _add_beams(elements, grid, nx, ny, ns, eid)
    # Core walls
    cx, cy = nx // 2 - 1, ny // 2 - 1
    for s in range(ns):
        for di in range(3):
            for dj in range(3):
                bl = grid.get(f"{cx+di}_{cy+dj}_{s}")
                br = grid.get(f"{cx+di+1}_{cy+dj}_{s}")
                tl = grid.get(f"{cx+di}_{cy+dj}_{s+1}")
                tr = grid.get(f"{cx+di+1}_{cy+dj}_{s+1}")
                if all(v is not None for v in [bl, br, tl, tr]):
                    elements.append({
                        "id": eid, "type": "wall", "node_ids": [bl, br, tr, tl],
                        "section": "W500", "dcr": round(0.1 + random.random() * 0.4, 3),
                        "axial": round(-1500 - random.random() * 6000, 1),
                        "moment": round(300 + random.random() * 2000, 1),
                        "shear": round(150 + random.random() * 800, 1),
                    })
                    eid += 1
    return {
        "nodes": nodes, "elements": elements,
        "meta": {"name": "30F Composite High-Rise", "stories": ns, "type": "SRC+Wall",
                 "total_area_m2": (nx * 9) * (ny * 8) * ns, "location": "Seoul, KR"},
        "code_check_summary": {
            "total_members": len(elements),
            "pass": sum(1 for e in elements if e["dcr"] <= 1.0),
            "ng": sum(1 for e in elements if e["dcr"] > 1.0),
            "max_dcr": max(e["dcr"] for e in elements),
            "design_code": "KDS 41 17 00:2022",
        },
    }


def main():
    out_dir = Path(__file__).parent
    models = {
        "demo_5f_rc_office": generate_5f_rc(),
        "demo_15f_rc_corewall": generate_15f_rc_corewall(),
        "demo_30f_composite_highrise": generate_30f_composite(),
    }
    for name, data in models.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        n_nodes = len(data["nodes"])
        n_elems = len(data["elements"])
        cs = data["code_check_summary"]
        print(f"✅ {name}.json — {n_nodes} nodes, {n_elems} elements, "
              f"PASS={cs['pass']}, NG={cs['ng']}, max DCR={cs['max_dcr']:.3f}")
    # Index file
    index = {
        "description": "Demo structural models for expert review",
        "generated": "2026-04-12",
        "models": {n: {"file": f"{n}.json", "nodes": len(d["nodes"]), "elements": len(d["elements"]),
                       "stories": d["meta"]["stories"], "type": d["meta"]["type"]}
                   for n, d in models.items()},
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"\n📁 Output: {out_dir}")


if __name__ == "__main__":
    main()
