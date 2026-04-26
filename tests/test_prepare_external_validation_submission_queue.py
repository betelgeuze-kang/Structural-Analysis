from __future__ import annotations

import json
from pathlib import Path

import implementation.phase1.prepare_external_validation_submission as submission


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_exact_topology_queue_refreshes_existing_rows_and_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    release_dir = tmp_path / "release"
    queue_dir = release_dir / "midas_native_roundtrip"
    queue_json = queue_dir / "exact_topology_structural_preview_promotion_queue.json"
    queue_md = queue_dir / "exact_topology_structural_preview_promotion_queue.md"
    _write_json(
        queue_json,
        {
            "generated_at": "2026-04-10T00:00:00Z",
            "summary": {
                "candidate_total": 4,
                "pending_candidate_count": 1,
                "promoted_candidate_count": 3,
                "public_archive_promoted_candidate_count": 3,
                "korean_candidate_total": 1,
                "korean_pending_candidate_count": 1,
                "state": "open",
            },
            "pending_candidate_rows": [
                {
                    "source_id": "bridge_a",
                    "queue_reason": "stale",
                    "promotion_receipt_json": "keep-me.json",
                    "bridge_report_json": "old-bridge-a.json",
                }
            ],
        },
    )
    queue_md.write_text("# stale queue markdown", encoding="utf-8")

    current_candidate_rows = [
        {
            "source_id": "bridge_a",
            "structure_type": "bridge",
            "status": "pending_promotion",
            "promoted_now": False,
            "supported_structural_preview": True,
            "preview_surface_status_label": "structural preview",
            "viewer_ready": True,
            "exact_topology_candidate": True,
            "bridge_report_json": "bridge-a.report.json",
            "model_json": "bridge-a.model.json",
        },
        {
            "source_id": "stair_b",
            "structure_type": "stair",
            "status": "pending_promotion",
            "promoted_now": False,
            "supported_structural_preview": True,
            "preview_surface_status_label": "structural preview",
            "viewer_ready": True,
            "exact_topology_candidate": True,
            "bridge_report_json": "stair-b.report.json",
            "model_json": "stair-b.model.json",
        },
        {
            "source_id": "ramp_c",
            "structure_type": "ramp",
            "status": "promoted",
            "promoted_now": True,
            "supported_structural_preview": True,
            "preview_surface_status_label": "structural preview",
            "viewer_ready": True,
            "exact_topology_candidate": True,
            "bridge_report_json": "ramp-c.report.json",
            "model_json": "ramp-c.model.json",
        },
    ]

    monkeypatch.setattr(
        submission,
        "_exact_topology_archive_candidate_rows",
        lambda: [dict(row) for row in current_candidate_rows],
    )
    monkeypatch.setattr(
        submission,
        "_render_exact_topology_structural_preview_promotion_queue_markdown",
        lambda payload: json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )

    out_json, out_md = submission._write_exact_topology_structural_preview_promotion_queue(release_dir)
    payload = json.loads(Path(out_json).read_text(encoding="utf-8"))

    assert out_json == str(queue_json.as_posix())
    assert out_md == str(queue_md.as_posix())
    assert payload["summary"]["candidate_total"] == 4
    assert payload["summary"]["pending_candidate_count"] == 2
    assert payload["summary"]["promoted_candidate_count"] == 2
    assert payload["summary"]["public_archive_promoted_candidate_count"] == 1
    assert payload["summary"]["korean_candidate_total"] == 1
    assert payload["summary"]["korean_pending_candidate_count"] == 1
    assert payload["summary"]["state"] == "open"
    assert [row["source_id"] for row in payload["pending_candidate_rows"]] == ["bridge_a", "stair_b"]
    assert payload["pending_candidate_rows"][0]["promotion_receipt_json"] == "keep-me.json"
    assert payload["pending_candidate_rows"][0]["bridge_report_json"] == "bridge-a.report.json"
    markdown = Path(out_md).read_text(encoding="utf-8")
    assert "stair_b" in markdown
    assert "pending_candidate_count" in markdown


def test_exact_topology_queue_drops_stale_rows_when_current_queue_closes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    release_dir = tmp_path / "release"
    queue_dir = release_dir / "midas_native_roundtrip"
    queue_json = queue_dir / "exact_topology_structural_preview_promotion_queue.json"
    queue_md = queue_dir / "exact_topology_structural_preview_promotion_queue.md"
    _write_json(
        queue_json,
        {
            "generated_at": "2026-04-10T00:00:00Z",
            "summary": {
                "candidate_total": 2,
                "pending_candidate_count": 1,
                "promoted_candidate_count": 1,
                "public_archive_promoted_candidate_count": 1,
                "korean_candidate_total": 0,
                "korean_pending_candidate_count": 0,
                "state": "open",
            },
            "pending_candidate_rows": [
                {
                    "source_id": "bridge_a",
                    "bridge_report_json": "old-bridge-a.json",
                }
            ],
        },
    )
    queue_md.write_text("# stale queue markdown", encoding="utf-8")

    monkeypatch.setattr(
        submission,
        "_exact_topology_archive_candidate_rows",
        lambda: [
            {
                "source_id": "bridge_a",
                "structure_type": "bridge",
                "status": "promoted",
                "promoted_now": True,
                "supported_structural_preview": True,
                "preview_surface_status_label": "structural preview",
                "viewer_ready": True,
                "exact_topology_candidate": True,
                "bridge_report_json": "bridge-a.report.json",
                "model_json": "bridge-a.model.json",
            }
        ],
    )
    monkeypatch.setattr(
        submission,
        "_render_exact_topology_structural_preview_promotion_queue_markdown",
        lambda payload: json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )

    out_json, out_md = submission._write_exact_topology_structural_preview_promotion_queue(release_dir)
    payload = json.loads(Path(out_json).read_text(encoding="utf-8"))

    assert payload["summary"]["candidate_total"] == 2
    assert payload["summary"]["pending_candidate_count"] == 0
    assert payload["summary"]["promoted_candidate_count"] == 2
    assert payload["summary"]["public_archive_promoted_candidate_count"] == 1
    assert payload["summary"]["state"] == "closed_until_new_public_archive_exact_topology_candidate"
    assert payload["pending_candidate_rows"] == []
    markdown = Path(out_md).read_text(encoding="utf-8")
    assert "bridge_a" not in markdown
    assert "closed_until_new_public_archive_exact_topology_candidate" in markdown
