from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np


def test_generate_group_local_connection_detailing_payloads_projects_rows(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    dataset = tmp_path / "dataset.npz"
    changes = tmp_path / "changes.json"
    projection = tmp_path / "connection_projection.json"

    model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 11, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 31, "material_id": 3}
                    ],
                    "metadata": {},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    np.savez_compressed(
        dataset,
        member_ids=np.asarray(["11"], dtype="<U16"),
        group_ids=np.asarray(["S05:transfer:nogroup:beam:SB800X7001.82"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S05:transfer:nogroup:beam:SB800X7001.82",
                        "member_type": "beam",
                        "action_family": "connection_detailing",
                        "action_name": "connection_detailing_down",
                        "before_rebar_ratio": 0.018,
                        "after_rebar_ratio": 0.018,
                        "before_detailing_quality": 0.55,
                        "after_detailing_quality": 0.60,
                        "zone_label": "transfer",
                        "story_band": 5,
                        "semantic_group": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_group_local_connection_detailing_payloads.py",
            "--parsed-model-json",
            str(model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--projection-json-out",
            str(projection),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(projection.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["group_local_connection_detailing_payload_available_count"] == 1
    row = payload["group_local_connection_detailing_payloads"][0]
    assert row["group_id"] == "S05:transfer:nogroup:beam:SB800X7001.82"
    assert row["payload_present"] is True
    assert row["mapping_source"] == "direct_group_id"
    assert row["element_id_count"] == 1
    assert row["baseline_detailing_quality"] == 0.55
    assert row["target_detailing_quality"] == 0.60
    assert row["review_priority"] == "high"
    assert row["followup_type"] == "connection_detailing_manual_update"


def test_generate_group_local_connection_detailing_payloads_uses_signature_zone_member_fallback(tmp_path: Path) -> None:
    model = tmp_path / "model_fallback.json"
    dataset = tmp_path / "dataset_fallback.npz"
    changes = tmp_path / "changes_fallback.json"
    projection = tmp_path / "connection_projection_fallback.json"

    model.write_text(
        json.dumps(
            {
                "model": {
                    "elements": [
                        {"id": 41, "type": "BEAM", "family": "beam", "node_ids": [1, 2], "section_id": 31, "material_id": 3}
                    ],
                    "metadata": {},
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    np.savez_compressed(
        dataset,
        member_ids=np.asarray(["41"], dtype="<U16"),
        group_ids=np.asarray(["S05:core:nogroup:beam:SB1200X1200"], dtype="<U64"),
    )
    changes.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "changes": [
                    {
                        "group_id": "S00:core:nogroup:beam:SB1200X1200",
                        "member_type": "beam",
                        "action_family": "connection_detailing",
                        "action_name": "connection_detailing_down",
                        "before_rebar_ratio": 0.018,
                        "after_rebar_ratio": 0.018,
                        "before_detailing_quality": 0.55,
                        "after_detailing_quality": 0.60,
                        "zone_label": "core",
                        "story_band": 0,
                        "semantic_group": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_group_local_connection_detailing_payloads.py",
            "--parsed-model-json",
            str(model),
            "--dataset-npz",
            str(dataset),
            "--changes-json",
            str(changes),
            "--projection-json-out",
            str(projection),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(projection.read_text(encoding="utf-8"))
    row = payload["group_local_connection_detailing_payloads"][0]
    assert row["mapping_source"] == "signature_zone_member_fallback"
    assert row["element_id_count"] == 1
