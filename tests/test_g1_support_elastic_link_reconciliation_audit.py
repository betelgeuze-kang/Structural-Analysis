from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_g1_support_elastic_link_reconciliation_audit.py"
SPEC = importlib.util.spec_from_file_location("build_g1_support_elastic_link_reconciliation_audit", SCRIPT_PATH)
assert SPEC and SPEC.loader
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write(path, json.dumps(payload))


def test_support_elastic_reconciliation_audit_maps_dominant_dofs(tmp_path: Path) -> None:
    mgt = tmp_path / "model.mgt"
    _write(
        mgt,
        "\n".join(
            [
                "*NODE",
                "1, 0, 0, 0",
                "2, 1, 0, 0",
                "3, 2, 0, 0",
                "*CONSTRAINT",
                "1, 111111",
                "*ELASTICLINK",
                "1, 2, 3, GEN, 0, NO, NO, NO, NO, NO, NO, 1, 1, 1, 1, 1, 1",
            ]
        ),
    )
    near_null = tmp_path / "near_null.json"
    _write_json(
        near_null,
        {
            "load_scale": 0.1,
            "frame_service_tangent_source": "real_per_element",
            "singularity_indicators": {"near_null_mode_count": 1},
            "assembled_tangent": {"free_dof_count": 12},
            "mode_rows": [
                {
                    "mode_index": 0,
                    "diagnosis": "translation_mechanism_like",
                    "dominant_nodes": [
                        {"node_id": 2, "dof": "UX", "amplitude": 0.9},
                        {"node_id": 1, "dof": "RX", "amplitude": 0.2},
                    ],
                }
            ],
        },
    )
    entity = tmp_path / "entity.json"
    spring = tmp_path / "spring.json"
    _write_json(entity, {"status": "partial", "summary": {}})
    _write_json(
        spring,
        {
            "status": "ready",
            "summary": {"direct_support_link_node_intersection_count": 0},
            "support": {"global_frame_shell_tangent_integration_ready": False},
        },
    )

    payload = audit_module.build_audit(
        repo_root=tmp_path,
        mgt_path=mgt,
        near_null_path=near_null,
        support_entity_path=entity,
        support_spring_path=spring,
    )

    assert payload["status"] == "ready"
    rows = payload["dominant_dof_rows"]
    by_node = {row["node_id"]: row for row in rows}
    assert by_node[1]["support_member"] is True
    assert by_node[1]["dof_restrained_by_authored_support"] is True
    assert by_node[2]["elastic_link_degree"] == 1
    assert by_node[2]["elastic_link_support_reachable"] is False
    assert payload["promotes_g1_closure"] is False
    assert any(item["finding_id"] == "boundary_spring_context_not_full_global_tangent" for item in payload["ranked_findings"])


def test_support_elastic_reconciliation_blocks_on_missing_inputs(tmp_path: Path) -> None:
    payload = audit_module.build_audit(repo_root=tmp_path)

    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_REQUIRED_INPUTS_MISSING"
    assert payload["promotes_g1_closure"] is False
