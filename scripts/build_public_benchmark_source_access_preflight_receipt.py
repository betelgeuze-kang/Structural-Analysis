#!/usr/bin/env python3
"""Build a HEAD-only source-access preflight receipt for Public Benchmark sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SOURCE_PLAN = (
    PRODUCTIZATION / "public_benchmark_phase2_source_acquisition_plan.json"
)
DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_source_access_preflight_receipt.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "public-benchmark-source-access-preflight-receipt.v1"
DEFAULT_TIMEOUT_SECONDS = 20
USER_AGENT = "codex-public-benchmark-source-access-preflight/1.0"
AUTH_GATE_HTTP_STATUSES = {401, 403}

ProbeFunc = Callable[[str, int], dict[str, Any]]


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = _resolve(repo_root, path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_dict(payload: Any) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _as_list(payload: Any) -> list[Any]:
    return payload if isinstance(payload, list) else []


def _int_header(value: Any) -> int:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return 0
    return parsed if parsed > 0 else 0


def _response_metadata(response: Any) -> dict[str, Any]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
        }
    return {
        "content_length_bytes": _int_header(headers.get("Content-Length")),
        "content_type": str(headers.get("Content-Type") or ""),
        "last_modified": str(headers.get("Last-Modified") or ""),
        "etag": str(headers.get("ETag") or ""),
        "accept_ranges": str(headers.get("Accept-Ranges") or ""),
    }


def _head_probe(url: str, timeout_seconds: int) -> dict[str, Any]:
    request = Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", response.getcode()) or 0)
            return {
                "http_status": status,
                "final_url": str(response.geturl() or url),
                "error": "",
                **_response_metadata(response),
            }
    except HTTPError as exc:
        return {
            "http_status": int(exc.code or 0),
            "final_url": str(exc.geturl() or url),
            "error": exc.__class__.__name__,
            **_response_metadata(exc),
        }
    except (TimeoutError, URLError, OSError) as exc:
        return {
            "http_status": 0,
            "final_url": "",
            "error": exc.__class__.__name__,
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
        }


def _success_http_status(http_status: int) -> bool:
    return 200 <= http_status < 400 or http_status in AUTH_GATE_HTTP_STATUSES


def _probe_target(
    *,
    url: str,
    head_command: str,
    probe_network: bool,
    timeout_seconds: int,
    probe_func: ProbeFunc,
) -> dict[str, Any]:
    if not url:
        return {
            "url": "",
            "head_command": head_command,
            "attempted": False,
            "status": "url_missing",
            "http_status": 0,
            "final_url": "",
            "error": "url_missing",
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
            "success_criteria_met": False,
        }
    if not probe_network:
        return {
            "url": url,
            "head_command": head_command,
            "attempted": False,
            "status": "not_run",
            "http_status": 0,
            "final_url": "",
            "error": "",
            "content_length_bytes": 0,
            "content_type": "",
            "last_modified": "",
            "etag": "",
            "accept_ranges": "",
            "success_criteria_met": False,
        }
    raw_probe = probe_func(url, timeout_seconds)
    http_status = int(raw_probe.get("http_status") or 0)
    success = _success_http_status(http_status)
    return {
        "url": url,
        "head_command": head_command,
        "attempted": True,
        "status": "reachable" if success else "blocked",
        "http_status": http_status,
        "final_url": str(raw_probe.get("final_url") or ""),
        "error": str(raw_probe.get("error") or ""),
        "content_length_bytes": _int_header(raw_probe.get("content_length_bytes")),
        "content_type": str(raw_probe.get("content_type") or ""),
        "last_modified": str(raw_probe.get("last_modified") or ""),
        "etag": str(raw_probe.get("etag") or ""),
        "accept_ranges": str(raw_probe.get("accept_ranges") or ""),
        "success_criteria_met": success,
    }


def _preflight_rows(source_plan: dict[str, Any]) -> list[dict[str, Any]]:
    receipt_plan = _as_dict(source_plan.get("official_source_receipt_plan"))
    rows = _as_list(receipt_plan.get("source_access_preflight_rows"))
    return [row for row in rows if isinstance(row, dict)]


def _row_status(
    *,
    probe_network: bool,
    primary_probe: dict[str, Any],
    fallback_probe: dict[str, Any],
) -> str:
    if not probe_network:
        return "network_probe_not_run"
    if primary_probe["success_criteria_met"]:
        return "primary_reachable"
    if fallback_probe["success_criteria_met"]:
        return "fallback_reachable"
    return "blocked"


def _row_blockers(
    *,
    row_status: str,
    primary_probe: dict[str, Any],
    fallback_probe: dict[str, Any],
) -> list[str]:
    if row_status in {"primary_reachable", "fallback_reachable"}:
        return []
    if row_status == "network_probe_not_run":
        return ["source_access_network_probe_not_run"]
    blockers = []
    if primary_probe["status"] == "url_missing":
        blockers.append("primary_url_missing")
    if fallback_probe["status"] == "url_missing":
        blockers.append("fallback_url_missing")
    if not blockers:
        blockers.append("primary_and_fallback_head_probe_blocked")
    return blockers


def _selected_probe(
    *,
    row_status: str,
    primary_probe: dict[str, Any],
    fallback_probe: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if row_status == "primary_reachable":
        return "primary", primary_probe
    if row_status == "fallback_reachable":
        return "fallback", fallback_probe
    return "", {}


def build_public_benchmark_source_access_preflight_receipt(
    *,
    repo_root: Path = ROOT,
    source_plan: Path = DEFAULT_SOURCE_PLAN,
    probe_network: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    probe_func: ProbeFunc = _head_probe,
) -> dict[str, Any]:
    source_plan_payload = _load_json(repo_root, source_plan)
    receipt_plan = _as_dict(source_plan_payload.get("official_source_receipt_plan"))
    source_payload_policy = _as_dict(
        receipt_plan.get("source_access_preflight_policy")
    )
    source_rows = _preflight_rows(source_plan_payload)
    probe_rows: list[dict[str, Any]] = []
    for row in source_rows:
        primary_probe = _probe_target(
            url=str(row.get("primary_url") or ""),
            head_command=str(row.get("primary_head_command") or ""),
            probe_network=probe_network,
            timeout_seconds=timeout_seconds,
            probe_func=probe_func,
        )
        fallback_probe = _probe_target(
            url=str(row.get("fallback_url") or ""),
            head_command=str(row.get("fallback_head_command") or ""),
            probe_network=probe_network,
            timeout_seconds=timeout_seconds,
            probe_func=probe_func,
        )
        row_status = _row_status(
            probe_network=probe_network,
            primary_probe=primary_probe,
            fallback_probe=fallback_probe,
        )
        blockers = _row_blockers(
            row_status=row_status,
            primary_probe=primary_probe,
            fallback_probe=fallback_probe,
        )
        selected_probe_role, selected_probe = _selected_probe(
            row_status=row_status,
            primary_probe=primary_probe,
            fallback_probe=fallback_probe,
        )
        probe_rows.append(
            {
                "source_id": str(row.get("source_id") or ""),
                "source_family": str(row.get("source_family") or ""),
                "access_mode": str(row.get("access_mode") or ""),
                "status": row_status,
                "blockers": blockers,
                "selected_probe_role": selected_probe_role,
                "selected_content_length_bytes": int(
                    selected_probe.get("content_length_bytes") or 0
                ),
                "operator_success_criteria": [
                    str(item)
                    for item in _as_list(row.get("operator_success_criteria"))
                    if str(item)
                ],
                "source_payload_policy": dict(
                    _as_dict(row.get("source_payload_policy"))
                    or source_payload_policy
                ),
                "primary_probe": primary_probe,
                "fallback_probe": fallback_probe,
                "claim_boundary": str(row.get("claim_boundary") or ""),
            }
        )
    reachable_count = sum(
        1
        for row in probe_rows
        if row["status"] in {"primary_reachable", "fallback_reachable"}
    )
    blocked_count = sum(1 for row in probe_rows if row["status"] == "blocked")
    not_run_count = sum(
        1 for row in probe_rows if row["status"] == "network_probe_not_run"
    )
    missing_row_count = 0 if probe_rows else 1
    known_payload_rows = [
        row
        for row in probe_rows
        if int(row.get("selected_content_length_bytes") or 0) > 0
    ]
    total_known_content_length_bytes = sum(
        int(row.get("selected_content_length_bytes") or 0)
        for row in known_payload_rows
    )
    largest_known_payload = max(
        known_payload_rows,
        key=lambda row: int(row.get("selected_content_length_bytes") or 0),
        default={},
    )
    if not probe_rows:
        status = "source_plan_preflight_rows_missing"
    elif not probe_network:
        status = "network_probe_required"
    elif blocked_count:
        status = "blocked"
    else:
        status = "reachable"
    source_access_ready = bool(probe_rows) and probe_network and blocked_count == 0
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_public_benchmark_source_access_preflight_receipt.py"),
                source_plan,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_source_access_preflight_receipt",
            repo_root=repo_root,
        ),
        "status": status,
        "contract_pass": bool(probe_rows) and (not probe_network or blocked_count == 0),
        "network_probe_performed": bool(probe_network),
        "timeout_seconds": int(timeout_seconds),
        "source_plan_artifact": str(source_plan),
        "source_access_ready": source_access_ready,
        "source_access_preflight_count": len(probe_rows),
        "source_access_probe_rows": probe_rows,
        "source_access_preflight_policy": source_payload_policy,
        "network_probe_command": (
            "python3 scripts/build_public_benchmark_source_access_preflight_receipt.py "
            f"--source-plan {source_plan} --out {DEFAULT_OUT} --out-md {DEFAULT_OUT_MD} "
            "--probe-network"
        ),
        "summary": {
            "source_access_probe_row_count": len(probe_rows),
            "reachable_count": reachable_count,
            "blocked_count": blocked_count,
            "not_run_count": not_run_count,
            "missing_preflight_row_count": missing_row_count,
            "network_probe_performed": bool(probe_network),
            "source_access_ready": source_access_ready,
            "known_content_length_probe_count": len(known_payload_rows),
            "total_known_content_length_bytes": total_known_content_length_bytes,
            "total_known_content_length_gib": round(
                total_known_content_length_bytes / (1024**3),
                3,
            ),
            "largest_known_payload_source_id": str(
                largest_known_payload.get("source_id") or ""
            ),
            "largest_known_payload_bytes": int(
                largest_known_payload.get("selected_content_length_bytes") or 0
            ),
        },
        "claim_boundary": (
            "This receipt performs HEAD-only source access preflight checks. It "
            "does not download, redistribute, checksum, license, or prove raw "
            "benchmark payloads, and it does not close Public Benchmark Phase 2."
        ),
    }


def render_public_benchmark_source_access_preflight_markdown(
    payload: dict[str, Any],
) -> str:
    summary = payload["summary"]
    lines = [
        "# Public Benchmark Source Access Preflight Receipt",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `network_probe_performed`: `{payload['network_probe_performed']}`",
        f"- `source_access_probe_row_count`: `{summary['source_access_probe_row_count']}`",
        f"- `reachable_count`: `{summary['reachable_count']}`",
        f"- `blocked_count`: `{summary['blocked_count']}`",
        f"- `not_run_count`: `{summary['not_run_count']}`",
        "- `known_content_length_probe_count`: "
        f"`{summary['known_content_length_probe_count']}`",
        "- `total_known_content_length_gib`: "
        f"`{summary['total_known_content_length_gib']}`",
        "- `largest_known_payload_source_id`: "
        f"`{summary['largest_known_payload_source_id']}`",
        "",
        "## Probe Rows",
        "",
        "| Source | Status | Size Bytes | Primary Status | Fallback Status | Blockers |",
        "|---|---|---:|---|---|---|",
    ]
    for row in payload["source_access_probe_rows"]:
        blockers = ", ".join(f"`{blocker}`" for blocker in row["blockers"])
        lines.append(
            f"| `{row['source_id']}` | `{row['status']}` | "
            f"`{row['selected_content_length_bytes']}` | "
            f"`{row['primary_probe']['status']}` "
            f"({row['primary_probe']['http_status']}) | "
            f"`{row['fallback_probe']['status']}` "
            f"({row['fallback_probe']['http_status']}) | {blockers} |"
        )
    lines.extend(
        [
            "",
            "## Command",
            "",
            f"- `network_probe_command`: `{payload['network_probe_command']}`",
            "",
            str(payload["claim_boundary"]),
            "",
        ]
    )
    return "\n".join(lines)


def write_public_benchmark_source_access_preflight_receipt(
    *,
    repo_root: Path = ROOT,
    source_plan: Path = DEFAULT_SOURCE_PLAN,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    probe_network: bool = False,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    payload = build_public_benchmark_source_access_preflight_receipt(
        repo_root=repo_root,
        source_plan=source_plan,
        probe_network=probe_network,
        timeout_seconds=timeout_seconds,
    )
    resolved_out = _resolve(repo_root, out)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = _resolve(repo_root, out_md)
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_public_benchmark_source_access_preflight_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-plan", type=Path, default=DEFAULT_SOURCE_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--probe-network", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_public_benchmark_source_access_preflight_receipt(
        repo_root=args.repo_root,
        source_plan=args.source_plan,
        out=args.out,
        out_md=args.out_md,
        probe_network=args.probe_network,
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "public-benchmark-source-access-preflight-receipt: "
            f"{payload['status']} | rows={payload['source_access_preflight_count']} | "
            f"network_probe={payload['network_probe_performed']} | "
            f"blockers={payload['summary']['blocked_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
