from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.interoperability_gateway import build_interoperability_report, load_interoperability_source


def test_load_interoperability_source_supports_midas_opensees_etabs_and_ifc(tmp_path: Path) -> None:
    etabs_path = tmp_path / "etabs_model.json"
    etabs_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "model": {
                    "stories": [{"id": "L1"}, {"id": "L2"}],
                    "points": [{"id": "P1"}, {"id": "P2"}, {"id": "P3"}],
                    "frame_objects": [{"id": "F1"}, {"id": "F2"}],
                    "area_objects": [{"id": "A1"}],
                    "frame_sections": [{"id": "W18X35"}],
                    "area_sections": [{"id": "SLAB200"}],
                    "materials": [{"id": "STEEL"}],
                    "load_patterns": [{"name": "DEAD"}],
                    "units": "kN-m",
                },
            }
        ),
        encoding="utf-8",
    )
    ifc_path = tmp_path / "sample.ifc"
    ifc_path.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#10=IFCBUILDINGSTOREY('id1',$,$,$,$,$,$,$);",
                "#20=IFCBEAM('b1',$,$,$,$,$,$,$);",
                "#21=IFCCOLUMN('c1',$,$,$,$,$,$,$);",
                "#22=IFCSLAB('s1',$,$,$,$,$,$,$);",
                "ENDSEC;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    midas = load_interoperability_source(Path("implementation/phase1/open_data/midas/midas_generator_33.json"))
    opensees = load_interoperability_source(Path("implementation/phase1/opensees_topology_report.json"))
    etabs = load_interoperability_source(etabs_path)
    ifc = load_interoperability_source(ifc_path)

    assert midas["source_tool"] == "MIDAS"
    assert int(midas["counts"]["node_count"]) > 1000
    assert int(midas["counts"]["member_count"]) > 1000
    assert opensees["source_tool"] == "OpenSees"
    assert int(opensees["counts"]["node_count"]) > 0
    assert int(opensees["counts"]["member_count"]) > 0
    assert etabs["source_tool"] == "ETABS"
    assert etabs["counts"] == {
        "node_count": 3,
        "member_count": 3,
        "storey_count": 2,
        "section_count": 2,
        "material_count": 1,
    }
    assert ifc["source_tool"] == "IFC"
    assert ifc["counts"]["member_count"] == 3
    assert ifc["counts"]["storey_count"] == 1


def test_build_interoperability_report_and_cli_smoke(tmp_path: Path) -> None:
    etabs_path = tmp_path / "etabs_smoke.json"
    etabs_path.write_text(
        json.dumps(
            {
                "stories": [{"id": "L1"}],
                "points": [{"id": "P1"}, {"id": "P2"}],
                "frame_objects": [{"id": "F1"}],
                "area_objects": [],
                "frame_sections": [{"id": "COL"}],
                "materials": [{"id": "CONC"}],
            }
        ),
        encoding="utf-8",
    )
    ifc_path = tmp_path / "smoke.ifc"
    ifc_path.write_text(
        "\n".join(
            [
                "ISO-10303-21;",
                "#1=IFCBUILDINGSTOREY('id1',$,$,$,$,$,$,$);",
                "#2=IFCBEAM('beam1',$,$,$,$,$,$,$);",
                "ENDSEC;",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "interop_report.json"
    source_paths = [
        Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
        Path("implementation/phase1/opensees_topology_report.json"),
        etabs_path,
        ifc_path,
    ]

    report = build_interoperability_report(inputs=source_paths, target_tools=["midas", "opensees", "ifc"])
    assert report["contract_pass"] is True
    assert report["summary"]["source_count"] == 4
    assert report["summary"]["successful_import_count"] == 4
    assert report["summary"]["export_count"] == 12
    assert report["summary"]["zero_geometry_diff_count"] == 12
    assert report["summary"]["tool_histogram"] == {
        "MIDAS": 1,
        "OpenSees": 1,
        "ETABS": 1,
        "IFC": 1,
    }
    assert report["checks"]["all_imports_succeeded"] is True
    assert report["checks"]["zero_geometry_diff_pass"] is True
    assert report["summary_line"].startswith("Interoperability gateway: PASS")

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/interoperability_gateway.py",
            "--inputs",
            ",".join(str(path) for path in source_paths),
            "--targets",
            "midas,opensees,ifc",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["zero_geometry_diff_count"] == 12
    assert payload["summary_line"].startswith("Interoperability gateway: PASS")
