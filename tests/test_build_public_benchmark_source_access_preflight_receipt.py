from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "scripts"
    / "build_public_benchmark_source_access_preflight_receipt.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "build_public_benchmark_source_access_preflight_receipt",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_source_plan(tmp_path: Path) -> Path:
    source_plan = {
        "official_source_receipt_plan": {
            "source_access_preflight_policy": {
                "license_or_accession_review_required_before_payload_use": True,
                "network_probe_only": True,
                "raw_payload_committed_by_plan": False,
                "raw_payload_downloaded_by_plan": False,
                "source_checksum_required_after_operator_acquisition": True,
            },
            "source_access_preflight_rows": [
                {
                    "source_id": "primary_then_fallback",
                    "source_family": "Test",
                    "access_mode": "public_download_with_operator_checksum_receipt",
                    "primary_url": "https://example.invalid/primary",
                    "fallback_url": "https://example.invalid/fallback",
                    "primary_head_command": (
                        "curl --head --location --max-time 20 "
                        "'https://example.invalid/primary'"
                    ),
                    "fallback_head_command": (
                        "curl --head --location --max-time 20 "
                        "'https://example.invalid/fallback'"
                    ),
                    "operator_success_criteria": [
                        "primary_or_fallback_url_resolves",
                        "http_status_is_2xx_3xx_or_documented_auth_gate",
                    ],
                    "source_payload_policy": {
                        "network_probe_only": True,
                        "raw_payload_downloaded_by_plan": False,
                        "raw_payload_committed_by_plan": False,
                    },
                    "claim_boundary": "HEAD-only test row.",
                },
                {
                    "source_id": "auth_gate",
                    "source_family": "Test",
                    "access_mode": "operator_download_and_license_or_accession_receipt_required",
                    "primary_url": "https://example.invalid/auth",
                    "fallback_url": "https://example.invalid/auth-fallback",
                    "primary_head_command": (
                        "curl --head --location --max-time 20 "
                        "'https://example.invalid/auth'"
                    ),
                    "fallback_head_command": (
                        "curl --head --location --max-time 20 "
                        "'https://example.invalid/auth-fallback'"
                    ),
                    "operator_success_criteria": [
                        "license_or_accession_review_recorded_before_payload_use",
                    ],
                    "claim_boundary": "HEAD-only auth row.",
                },
            ],
        }
    }
    source_plan_path = tmp_path / "source_plan.json"
    source_plan_path.write_text(json.dumps(source_plan), encoding="utf-8")
    return source_plan_path


def test_source_access_receipt_defaults_to_network_probe_required(
    tmp_path: Path,
) -> None:
    source_plan_path = _write_source_plan(tmp_path)

    payload = module.build_public_benchmark_source_access_preflight_receipt(
        repo_root=tmp_path,
        source_plan=source_plan_path,
    )

    assert payload["schema_version"] == (
        "public-benchmark-source-access-preflight-receipt.v1"
    )
    assert payload["status"] == "network_probe_required"
    assert payload["contract_pass"] is True
    assert payload["network_probe_performed"] is False
    assert payload["source_access_ready"] is False
    assert payload["summary"] == {
        "blocked_count": 0,
        "known_content_length_probe_count": 0,
        "largest_known_payload_bytes": 0,
        "largest_known_payload_source_id": "",
        "missing_preflight_row_count": 0,
        "network_probe_performed": False,
        "not_run_count": 2,
        "reachable_count": 0,
        "source_access_probe_row_count": 2,
        "source_access_ready": False,
        "total_known_content_length_bytes": 0,
        "total_known_content_length_gib": 0.0,
    }
    assert payload["network_probe_command"].endswith("--probe-network")
    first_row = payload["source_access_probe_rows"][0]
    assert first_row["status"] == "network_probe_not_run"
    assert first_row["blockers"] == ["source_access_network_probe_not_run"]
    assert first_row["primary_probe"]["attempted"] is False
    assert first_row["source_payload_policy"]["network_probe_only"] is True
    assert (
        first_row["source_payload_policy"]["raw_payload_downloaded_by_plan"]
        is False
    )
    assert "does not download" in payload["claim_boundary"]


def test_source_access_receipt_uses_primary_fallback_and_auth_gate_statuses(
    tmp_path: Path,
) -> None:
    source_plan_path = _write_source_plan(tmp_path)
    seen: list[tuple[str, int]] = []

    def fake_probe(url: str, timeout_seconds: int) -> dict[str, Any]:
        seen.append((url, timeout_seconds))
        if url.endswith("/primary"):
            return {
                "http_status": 500,
                "final_url": url,
                "error": "HTTPError",
                "content_length_bytes": 11,
            }
        if url.endswith("/fallback"):
            return {
                "http_status": 302,
                "final_url": url,
                "error": "",
                "content_length_bytes": 123,
                "last_modified": "Tue, 01 Jan 2030 00:00:00 GMT",
                "etag": "\"fallback\"",
                "accept_ranges": "bytes",
            }
        if url.endswith("/auth"):
            return {
                "http_status": 403,
                "final_url": url,
                "error": "HTTPError",
                "content_length_bytes": 456,
                "content_type": "application/octet-stream",
            }
        return {
            "http_status": 0,
            "final_url": "",
            "error": "URLError",
            "content_length_bytes": 0,
        }

    payload = module.build_public_benchmark_source_access_preflight_receipt(
        repo_root=tmp_path,
        source_plan=source_plan_path,
        probe_network=True,
        timeout_seconds=7,
        probe_func=fake_probe,
    )

    rows = {row["source_id"]: row for row in payload["source_access_probe_rows"]}
    assert payload["status"] == "reachable"
    assert payload["contract_pass"] is True
    assert payload["network_probe_performed"] is True
    assert payload["summary"]["reachable_count"] == 2
    assert payload["summary"]["blocked_count"] == 0
    assert payload["summary"]["known_content_length_probe_count"] == 2
    assert payload["summary"]["total_known_content_length_bytes"] == 579
    assert payload["summary"]["largest_known_payload_source_id"] == "auth_gate"
    assert payload["summary"]["largest_known_payload_bytes"] == 456
    assert rows["primary_then_fallback"]["status"] == "fallback_reachable"
    assert rows["primary_then_fallback"]["primary_probe"]["http_status"] == 500
    assert rows["primary_then_fallback"]["fallback_probe"]["http_status"] == 302
    assert rows["primary_then_fallback"]["selected_probe_role"] == "fallback"
    assert rows["primary_then_fallback"]["selected_content_length_bytes"] == 123
    assert rows["primary_then_fallback"]["fallback_probe"]["etag"] == "\"fallback\""
    assert rows["auth_gate"]["status"] == "primary_reachable"
    assert rows["auth_gate"]["primary_probe"]["http_status"] == 403
    assert rows["auth_gate"]["selected_probe_role"] == "primary"
    assert rows["auth_gate"]["selected_content_length_bytes"] == 456
    assert seen == [
        ("https://example.invalid/primary", 7),
        ("https://example.invalid/fallback", 7),
        ("https://example.invalid/auth", 7),
        ("https://example.invalid/auth-fallback", 7),
    ]


def test_source_access_receipt_writer_creates_json_and_markdown(
    tmp_path: Path,
) -> None:
    source_plan_path = _write_source_plan(tmp_path)
    out = tmp_path / "receipt.json"
    out_md = tmp_path / "receipt.md"

    payload = module.write_public_benchmark_source_access_preflight_receipt(
        repo_root=tmp_path,
        source_plan=source_plan_path,
        out=out,
        out_md=out_md,
    )

    assert json.loads(out.read_text(encoding="utf-8"))["status"] == payload["status"]
    markdown = out_md.read_text(encoding="utf-8")
    assert "# Public Benchmark Source Access Preflight Receipt" in markdown
    assert "`network_probe_required`" in markdown
