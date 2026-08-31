#!/usr/bin/env python3
"""Build and verify the PR #77/#78 owner-scope disposition inventory."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("canonical/source-quarry-inventory.v1.json")
DEFAULT_SCHEMA = Path("canonical/source-quarry-inventory.v1.schema.json")
SCHEMA_VERSION = "structural-analysis-source-quarry-inventory.v1"
REPORT_VERSION = "source-quarry-inventory-check.v1"
REPOSITORY = "betelgeuze-kang/Structural-Analysis"
POLICY_ID = "frame-alpha-retire-source-quarry-retained-device-fgmres.v1"
DISPOSITION = "owner_scope_retirement"
POLICY_PATHS = (
    "docs/adr/010-retire-source-quarry-retained-device-fgmres.md",
    "README.md",
    "artifacts/manifests/capabilities.yaml",
)
PULL_REQUESTS = {
    77: {
        "issue": 143,
        "base_sha": "809f4ba5cb060b1a46bf8da95603c9ad3fbec355",
        "head_sha": "e0bd0231be2fef728410d1bee7f106d93e5b1c90",
        "changed_file_count": 23,
        "api_rows_digest": (
            "sha256:45286fcc963a93f88212e88144184602363a6062d98f28a59000ffb800e689b1"
        ),
    },
    78: {
        "issue": 144,
        "base_sha": "e0bd0231be2fef728410d1bee7f106d93e5b1c90",
        "head_sha": "0e2c5c0d1cc794442c977a0a8ee1f0d75345d945",
        "changed_file_count": 457,
        "api_rows_digest": (
            "sha256:5028f903a9ce39b8915215bc42fbc40805b3989abafc0c9fd21c132412abead0"
        ),
    },
}


class InventoryError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        + b"\n"
    )


def _sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _is_hex_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(c in "0123456789abcdef" for c in value)
    )


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args), cwd=repo, check=False, capture_output=True, text=True
    )
    if result.returncode:
        raise InventoryError(
            f"git_command_failed:{' '.join(args)}:{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _source_commit(repo: Path) -> str:
    value = _git(repo, "rev-parse", "HEAD")
    if not _is_hex_sha(value):
        raise InventoryError("source_commit_invalid")
    return value


def _blob_at(repo: Path, revision: str, path: str) -> str | None:
    result = subprocess.run(
        ("git", "cat-file", "-e", f"{revision}:{path}"),
        cwd=repo,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        return None
    value = _git(repo, "rev-parse", f"{revision}:{path}")
    return value if _is_hex_sha(value) else None


def _policy_projection(repo: Path) -> list[dict[str, str]]:
    rows = []
    for path in POLICY_PATHS:
        if not (repo / path).is_file():
            raise InventoryError(f"policy_path_missing:{path}")
        blob = _git(repo, "hash-object", "--", path)
        if not _is_hex_sha(blob):
            raise InventoryError(f"policy_blob_invalid:{path}")
        rows.append({"path": path, "blob_sha": blob})
    return rows


def _request_json(url: str) -> tuple[Any, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "structural-analysis-source-quarry-audit-v1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:  # noqa: S310
            return json.loads(response.read()), {
                k.lower(): v for k, v in response.headers.items()
            }
    except (HTTPError, URLError, TimeoutError) as exc:
        raise InventoryError(f"github_api_request_failed:{url}:{exc}") from exc


def _next_link(header: str | None) -> str | None:
    for item in (header or "").split(","):
        parts = [part.strip() for part in item.split(";")]
        if len(parts) >= 2 and parts[1] == 'rel="next"':
            return parts[0][1:-1]
    return None


def _normalize(row: Any) -> dict[str, Any]:
    result = (
        {
            "path": row.get("filename"),
            "change_status": row.get("status"),
            "blob_sha": row.get("sha"),
            "additions": row.get("additions"),
            "deletions": row.get("deletions"),
            "changes": row.get("changes"),
        }
        if isinstance(row, dict)
        else {}
    )
    if isinstance(row, dict) and row.get("previous_filename") is not None:
        result["previous_path"] = row["previous_filename"]
    if (
        not isinstance(result.get("path"), str)
        or result.get("change_status")
        not in {"added", "changed", "modified", "removed", "renamed"}
        or not _is_hex_sha(result.get("blob_sha"))
        or any(
            type(result.get(k)) is not int or result[k] < 0
            for k in ("additions", "deletions", "changes")
        )
    ):
        raise InventoryError(f"github_changed_file_row_invalid:{result.get('path')}")
    return result


def fetch_github_pull_request(
    number: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = f"https://api.github.com/repos/{REPOSITORY}"
    metadata, _ = _request_json(f"{root}/pulls/{number}")
    rows, url = [], f"{root}/pulls/{number}/files?per_page=100&page=1"
    while url:
        page, headers = _request_json(url)
        if not isinstance(page, list):
            raise InventoryError(f"github_changed_file_page_invalid:{number}")
        rows.extend(_normalize(row) for row in page)
        url = _next_link(headers.get("link"))
    return metadata, sorted(rows, key=lambda row: row["path"])


def _row(repo: Path, api_row: dict[str, Any]) -> dict[str, Any]:
    current = _blob_at(repo, "HEAD", api_row["path"])
    identical = current == api_row["blob_sha"]
    return {
        **api_row,
        "current_blob_sha": current,
        "current_relation": "identical"
        if identical
        else ("different" if current else "absent"),
        "status": "present" if identical else "superseded",
        "reason": "exact_blob_present" if identical else DISPOSITION,
        "replacement_paths": [api_row["path"]] if identical else list(POLICY_PATHS),
    }


def build_inventory(
    repo: Path, api_payloads: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]]
) -> dict[str, Any]:
    prs = []
    for number, expected in sorted(PULL_REQUESTS.items()):
        metadata, api_rows = api_payloads[number]
        base, head = metadata.get("base"), metadata.get("head")
        valid = (
            metadata.get("number") == number
            and metadata.get("state") == "closed"
            and metadata.get("merged") is False
            and isinstance(base, dict)
            and base.get("sha") == expected["base_sha"]
            and isinstance(head, dict)
            and head.get("sha") == expected["head_sha"]
            and metadata.get("changed_files") == expected["changed_file_count"]
            and len(api_rows) == expected["changed_file_count"]
            and len({row["path"] for row in api_rows}) == len(api_rows)
            and [row["path"] for row in api_rows]
            == sorted(row["path"] for row in api_rows)
            and _sha256(api_rows) == expected["api_rows_digest"]
        )
        if not valid:
            raise InventoryError(f"github_pull_request_identity_mismatch:{number}")
        rows = [_row(repo, row) for row in api_rows]
        counts = Counter(row["status"] for row in rows)
        prs.append(
            {
                "number": number,
                "source_issue": expected["issue"],
                "state": "closed",
                "merged": False,
                "base_sha": expected["base_sha"],
                "head_sha": expected["head_sha"],
                "changed_file_count": len(rows),
                "allowed_statuses": ["present", "superseded"],
                "github_changed_files_api": f"https://api.github.com/repos/{REPOSITORY}/pulls/{number}/files",
                "api_rows_digest": _sha256(api_rows),
                "status_counts": {
                    "present": counts["present"],
                    "superseded": counts["superseded"],
                },
                "files": rows,
            }
        )
    projection = _policy_projection(repo)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository": REPOSITORY,
        "audit_source": "github_rest_pull_request_changed_files_api",
        "retirement_policy": {
            "policy_id": POLICY_ID,
            "disposition": DISPOSITION,
            "retired_scope_status": "retired_not_planned_for_current_product",
            "scope_disposition_only": True,
            "semantic_equivalence_claim": False,
            "policy_projection": projection,
            "policy_projection_digest": _sha256(projection),
        },
        "pull_requests": prs,
        "unresolved_file_extraction_blockers": [],
        "claim_boundary": {
            "inventory_complete": True,
            "old_branch_merge_allowed": False,
            "old_branch_import_allowed": False,
            "readiness_promoted": False,
            "numerical_authority": False,
            "hardware_authority": False,
            "operator_authority": False,
            "signature_authority": False,
            "release_authority": False,
            "commercial_authority": False,
            "statement": "This is an owner-approved scope disposition, not a semantic-equivalence or implementation claim.",
        },
    }
    payload["inventory_digest"] = _inventory_digest(payload)
    return payload


def _inventory_digest(payload: dict[str, Any]) -> str:
    unsigned = dict(payload)
    unsigned.pop("inventory_digest", None)
    return _sha256(unsigned)


def _api_payloads_from_inventory(payload: dict[str, Any]):
    pull_requests = payload.get("pull_requests")
    if not isinstance(pull_requests, list):
        raise InventoryError("canonical_pull_requests_invalid")
    result = {}
    for pr in pull_requests:
        if not isinstance(pr, dict):
            raise InventoryError("canonical_pull_request_row_invalid")
        files = pr.get("files")
        if not isinstance(files, list):
            raise InventoryError("canonical_pull_request_files_invalid")
        rows = []
        for row in files:
            if not isinstance(row, dict):
                raise InventoryError("canonical_pull_request_file_row_invalid")
            api = {
                k: row[k]
                for k in (
                    "path",
                    "change_status",
                    "blob_sha",
                    "additions",
                    "deletions",
                    "changes",
                )
            }
            if "previous_path" in row:
                api["previous_path"] = row["previous_path"]
            rows.append(api)
        result[pr["number"]] = (
            {
                "number": pr["number"],
                "state": pr["state"],
                "merged": pr["merged"],
                "base": {"sha": pr["base_sha"]},
                "head": {"sha": pr["head_sha"]},
                "changed_files": pr["changed_file_count"],
            },
            rows,
        )
    return result


def validate_inventory(
    repo: Path, payload: dict[str, Any], schema: dict[str, Any], *, github_payloads=None
) -> dict[str, Any]:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload), key=lambda e: list(e.path)
    )
    blockers = [
        f"schema_invalid:/{'/'.join(map(str, e.path))}:{e.message}" for e in errors
    ]
    try:
        rebuilt = build_inventory(repo, _api_payloads_from_inventory(payload))
    except (InventoryError, KeyError, TypeError, ValueError) as exc:
        blockers.append(f"inventory_rebuild_failed:{exc}")
        rebuilt = None
    if rebuilt is not None and _canonical_bytes(rebuilt) != _canonical_bytes(payload):
        blockers.append("canonical_inventory_not_deterministically_rebuilt")
    if payload.get("inventory_digest") != _inventory_digest(payload):
        blockers.append("inventory_digest_mismatch")
    if github_payloads is not None:
        try:
            live = build_inventory(repo, github_payloads)
        except (InventoryError, KeyError, TypeError, ValueError) as exc:
            blockers.append(f"github_inventory_rebuild_failed:{exc}")
        else:
            if _canonical_bytes(live) != _canonical_bytes(payload):
                blockers.append("github_api_snapshot_differs_from_canonical_inventory")
    raw_pull_requests = payload.get("pull_requests")
    pull_requests = raw_pull_requests if isinstance(raw_pull_requests, list) else []
    counts: Counter[str] = Counter()
    for pr in pull_requests:
        if not isinstance(pr, dict):
            continue
        files = pr.get("files")
        if not isinstance(files, list):
            continue
        for row in files:
            if isinstance(row, dict) and isinstance(row.get("status"), str):
                counts[row["status"]] += 1
    blockers = sorted(set(blockers))
    return {
        "schema_version": REPORT_VERSION,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "source_commit": _source_commit(repo),
        "policy_projection_digest": _sha256(_policy_projection(repo)),
        "pull_request_count": len(pull_requests),
        "changed_file_count": sum(counts.values()),
        "status_counts": dict(sorted(counts.items())),
        "unique_file_blocker_count": 0,
        "external_only_file_blocker_count": 0,
        "github_api_verified": github_payloads is not None and not blockers,
        "blockers": blockers,
        "claim_boundary": payload.get("claim_boundary", {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-github", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    inventory_path = (
        args.inventory if args.inventory.is_absolute() else repo / args.inventory
    )
    schema_path = args.schema if args.schema.is_absolute() else repo / args.schema
    schema = json.loads(schema_path.read_text())
    live = (
        {n: fetch_github_pull_request(n) for n in sorted(PULL_REQUESTS)}
        if args.write or args.verify_github
        else None
    )
    if args.write:
        payload = build_inventory(repo, live)
        inventory_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
    else:
        payload = json.loads(inventory_path.read_text())
    report = validate_inventory(repo, payload, schema, github_payloads=live)
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else f"source quarry inventory: {report['status']} | files={report['changed_file_count']}"
    )
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
