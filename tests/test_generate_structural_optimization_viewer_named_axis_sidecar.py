from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/generate_structural_optimization_visualization_viewer.py"
    )
    spec = importlib.util.spec_from_file_location("viewer_named_axis_sidecar_module", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_midas_kds_geometry_bridge_payload_uses_curated_named_axis_sidecar(tmp_path: Path) -> None:
    module = _load_module()
    model_json = tmp_path / "named_axis_case.json"
    sidecar_json = tmp_path / "named_axis_case.named_axis_refs.curated.json"

    model_json.write_text(
        json.dumps(
            {
                "model": {
                    "metadata": {},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    sidecar_json.write_text(
        json.dumps(
            {
                "schema_version": "midas_named_axis_refs.curated.v1",
                "source_mode": "curated_named_axis_sidecar",
                "note": "Curated test axis refs",
                "axis_refs": {
                    "x": [{"label": "A", "value": 0.0}, {"label": "B", "value": 8.0}],
                    "y": [{"label": "1", "value": 0.0}, {"label": "2", "value": 6.0}],
                    "z": [{"label": "L1", "value": 0.0}, {"label": "L2", "value": 3.6}],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    bridge_payload, source_label = module._midas_kds_geometry_bridge_payload(model_json)

    assert bridge_payload["axis_ref_source_mode"] == "curated_named_axis_sidecar"
    assert bridge_payload["axis_ref_source_path"] == str(sidecar_json)
    assert bridge_payload["axis_refs"]["x"][0]["label"] == "A"
    assert bridge_payload["axis_refs"]["y"][1]["label"] == "2"
    assert bridge_payload["summary"]["axis_ref_counts"] == {"x": 2, "y": 2, "z": 2}
    assert "axis sidecar" in source_label
