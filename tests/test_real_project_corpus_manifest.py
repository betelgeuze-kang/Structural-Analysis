from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "implementation/phase1/real_project_corpus_manifest.schema.json"
SEED_MANIFEST_PATH = REPO_ROOT / "implementation/phase1/real_project_corpus_seed_manifest.json"
VALIDATOR = REPO_ROOT / "implementation/phase1/validate_real_project_corpus_manifest.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_seed_manifest_locks_p0_p1_p2_closeout_order_and_sources() -> None:
    payload = json.loads(SEED_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "real_project_corpus_manifest.v1"
    assert [phase["phase_id"] for phase in payload["phase_closeout_order"]] == ["P0", "P1", "P2"]
    assert all(phase["exit_gates"] for phase in payload["phase_closeout_order"])

    source_ids = {source["source_id"] for source in payload["source_families"]}
    assert {"koneps_turnkey_design_docs", "peer_tbi_tall_buildings"} <= source_ids
    assert all(source["priority_phase"] == "P0" for source in payload["source_families"])

    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--schema",
            str(SCHEMA_PATH),
            "--manifest",
            str(SEED_MANIFEST_PATH),
            "--show-summary",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Real project corpus manifest OK" in proc.stdout
    assert "p0_ready_sources=2/2" in proc.stdout


def test_validator_rejects_unverified_redistribution_and_missing_artifact_hash(tmp_path: Path) -> None:
    manifest = tmp_path / "bad_manifest.json"
    _write_json(
        manifest,
        {
            "schema_version": "real_project_corpus_manifest.v1",
            "generated_at": "2026-04-27T00:00:00+09:00",
            "phase_closeout_order": [
                {"phase_id": "P0", "title": "provenance", "exit_gates": ["legal gate"]},
                {"phase_id": "P1", "title": "coverage", "exit_gates": ["coverage gate"]},
                {"phase_id": "P2", "title": "automation", "exit_gates": ["automation gate"]},
            ],
            "source_families": [
                {
                    "source_id": "unsafe_koneps",
                    "source_label": "Unsafe KONEPS candidate",
                    "priority_phase": "P0",
                    "official_entrypoint_url": "https://www.data.go.kr/data/15058815/openapi.do",
                    "source_kind": "public_procurement_design_documents",
                    "jurisdiction": "KR",
                    "access_policy": {
                        "classification": "restricted",
                        "redistribution_allowed": True,
                        "requires_manual_review": False,
                        "license_basis": "assumed public",
                    },
                    "target_file_types": [".mgt"],
                    "p0_exit_gates": ["provenance"],
                }
            ],
            "artifact_rows": [
                {
                    "artifact_id": "bad-artifact",
                    "source_id": "unsafe_koneps",
                    "retrieval_status": "downloaded",
                    "source_url": "https://example.invalid/model.mgt",
                    "access_policy": {
                        "classification": "public",
                        "redistribution_allowed": True,
                        "requires_manual_review": False,
                        "license_basis": "test fixture",
                    },
                    "file_inventory": [{"path": "model.mgt", "role": "midas_model"}],
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--schema",
            str(SCHEMA_PATH),
            "--manifest",
            str(manifest),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "restricted sources cannot be marked redistribution_allowed" in proc.stderr
    assert "downloaded artifacts require sha256 and bytes" in proc.stderr
