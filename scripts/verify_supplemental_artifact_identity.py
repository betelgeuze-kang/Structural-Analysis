"""Check supplemental upload transport, never engineering or release authority.

Run after the signed upload in a separate read-only job. Even byte-identical
same-name duplicates fail closed. The selected artifact ID is rechecked through
the direct API and is the only ID downloaded. ZIP bytes are hashed as a bounded
stream; nothing from the archive is extracted, imported, or executed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from strict_json import StrictJSONError, strict_json_loads

SAFE_INTEGER = 9_007_199_254_740_991
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_DIAGNOSTIC_MATCHES = 16
MAX_DIAGNOSTIC_BYTES = 32 * 1024
API_ROOT = "https://api.github.com"
FAMILIES = {
    "linear": (
        "bounded-planar-opensees-technical.yml",
        "bounded-planar-opensees-technical",
    ),
    "negative": (
        "bounded-planar-negative-opensees-technical.yml",
        "bounded-planar-negative-opensees",
    ),
    "scaling": (
        "bounded-planar-scaling-opensees-technical.yml",
        "bounded-planar-scaling-opensees",
    ),
    "modal_buckling": (
        "bounded-planar-modal-buckling-technical.yml",
        "bounded-planar-modal-buckling",
    ),
    "nonlinear_material_recovery": (
        "bounded-planar-nonlinear-material-recovery-technical.yml",
        "bounded-planar-nonlinear-material-recovery",
    ),
}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}\Z")
Stream = Callable[[str, int, Callable[[bytes], Any]], None]


class ArtifactIdentityError(ValueError):
    """Stable, non-secret error code suitable for a transport diagnostic."""


def positive_integer(value: Any) -> bool:
    return type(value) is int and 1 <= value <= SAFE_INTEGER


def stream_command(
    command: list[str],
    limit: int,
    sink: Callable[[bytes], Any],
    *,
    timeout: float = 60.0,
) -> None:
    """Drain a process with hard byte/time bounds and without retaining stderr."""
    if not positive_integer(limit) or not 0 < timeout <= 60:
        raise ArtifactIdentityError("transport_bounds_invalid")
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    errors: list[Exception] = []

    def drain() -> None:
        observed = 0
        try:
            while chunk := process.stdout.read(64 * 1024):
                observed += len(chunk)
                if observed > limit:
                    raise ArtifactIdentityError("api_response_too_large")
                sink(chunk)
        except Exception as exc:
            errors.append(exc)

    reader = threading.Thread(target=drain, daemon=True)
    deadline = time.monotonic() + timeout
    reader.start()
    try:
        reader.join(timeout)
        if reader.is_alive():
            raise ArtifactIdentityError("api_timeout")
        if errors:
            raise errors[0]
        try:
            code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise ArtifactIdentityError("api_timeout") from exc
        if code:
            raise ArtifactIdentityError("api_request_failed")
    finally:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        reader.join(1)
        if not reader.is_alive():
            process.stdout.close()


def gh_stream(endpoint: str, limit: int, sink: Callable[[bytes], Any]) -> None:
    stream_command(
        ["gh", "api", "--hostname", "github.com", "--method", "GET", endpoint],
        limit,
        sink,
    )


def read_api(endpoint: str, stream: Stream) -> dict[str, Any]:
    buffer = io.BytesIO()
    stream(endpoint, MAX_JSON_BYTES, buffer.write)
    try:
        payload = strict_json_loads(buffer.getvalue())
    except (StrictJSONError, RecursionError) as exc:
        raise ArtifactIdentityError("api_json_invalid") from exc
    if type(payload) is not dict:
        raise ArtifactIdentityError("api_object_required")
    return payload


def bounded_match(row: dict[str, Any]) -> dict[str, Any]:
    """Never copy raw names, URLs, log text, or unrecognized metadata."""
    digest = row.get("digest")
    return {
        "id": row.get("id") if positive_integer(row.get("id")) else None,
        "digest": digest if isinstance(digest, str) and DIGEST.fullmatch(digest) else None,
        "size_in_bytes": row.get("size_in_bytes")
        if positive_integer(row.get("size_in_bytes"))
        else None,
        "expired": row.get("expired") if type(row.get("expired")) is bool else None,
    }


def select_artifact(
    payload: dict[str, Any], expected_name: str, diagnostic: dict[str, Any]
) -> dict[str, Any]:
    rows = payload.get("artifacts")
    total = payload.get("total_count")
    if (
        type(rows) is not list
        or len(rows) > 100
        or type(total) is not int
        or not 0 <= total <= SAFE_INTEGER
        or any(type(row) is not dict for row in rows)
    ):
        raise ArtifactIdentityError("artifact_inventory_invalid")
    if total != len(rows):
        raise ArtifactIdentityError("artifact_inventory_incomplete")
    matches = [row for row in rows if row.get("name") == expected_name]
    diagnostic["matching_count"] = len(matches)
    diagnostic["matching_artifacts"] = [
        bounded_match(row) for row in matches[:MAX_DIAGNOSTIC_MATCHES]
    ]
    diagnostic["matching_artifacts_truncated"] = len(matches) > MAX_DIAGNOSTIC_MATCHES
    if not matches:
        raise ArtifactIdentityError("artifact_missing")
    if len(matches) != 1:
        raise ArtifactIdentityError("artifact_inventory_ambiguous")
    return matches[0]


def verify_run(
    run: dict[str, Any], repository: str, source_sha: str,
    run_id: int, run_attempt: int, family: str,
) -> int:
    repo = run.get("repository")
    head_repo = run.get("head_repository")
    if not (
        type(repo) is dict and type(head_repo) is dict
        and repo.get("full_name") == repository
        and head_repo.get("full_name") == repository
        and positive_integer(repo.get("id"))
        and positive_integer(head_repo.get("id"))
        and repo["id"] == head_repo["id"]
        and positive_integer(run.get("id")) and run["id"] == run_id
        and positive_integer(run.get("run_attempt")) and run["run_attempt"] == run_attempt
        and run.get("head_sha") == source_sha
        and run.get("head_branch") == "main"
        and run.get("path") == ".github/workflows/" + FAMILIES[family][0]
        and run.get("event") in {"push", "workflow_dispatch"}
        and (
            (run.get("status") == "in_progress" and run.get("conclusion") is None)
            or (run.get("status") == "completed" and run.get("conclusion") == "success")
        )
    ):
        raise ArtifactIdentityError("workflow_run_identity_invalid")
    return repo["id"]


def verify_artifact(
    row: dict[str, Any], *, repository: str, source_sha: str,
    run_id: int, repository_id: int, expected_name: str,
) -> None:
    artifact_id = row.get("id")
    linked = row.get("workflow_run")
    digest = row.get("digest")
    if not (
        positive_integer(artifact_id)
        and row.get("name") == expected_name
        and isinstance(digest, str) and DIGEST.fullmatch(digest)
        and positive_integer(row.get("size_in_bytes"))
        and row["size_in_bytes"] <= MAX_ARCHIVE_BYTES
        and row.get("archive_download_url")
        == f"{API_ROOT}/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        and type(row.get("expired")) is bool
        and type(linked) is dict
        and positive_integer(linked.get("id")) and linked["id"] == run_id
        and positive_integer(linked.get("repository_id"))
        and linked["repository_id"] == repository_id
        and positive_integer(linked.get("head_repository_id"))
        and linked["head_repository_id"] == repository_id
        and linked.get("head_sha") == source_sha
        and linked.get("head_branch") == "main"
    ):
        raise ArtifactIdentityError("artifact_metadata_invalid")
    if row["expired"]:
        raise ArtifactIdentityError("artifact_expired")


def inspect_upload(
    *, repository: str, source_sha: str, run_id: int,
    run_attempt: int, family: str, stream: Stream = gh_stream,
) -> dict[str, Any]:
    """Return a bounded diagnostic; rejected transport never gains any credit."""
    diagnostic: dict[str, Any] = {
        "schema_version": "supplemental-artifact-transport-diagnostic.v1",
        "status": "rejected",
        "stage": "context",
        "error_code": None,
        "release_authority": False,
        "independent_verification": False,
        "technical_credit_granted": False,
    }
    try:
        if not (
            isinstance(repository, str) and REPOSITORY.fullmatch(repository)
            and isinstance(source_sha, str) and SHA.fullmatch(source_sha)
            and positive_integer(run_id) and positive_integer(run_attempt)
            and isinstance(family, str) and family in FAMILIES
        ):
            raise ArtifactIdentityError("context_invalid")
        expected_name = f"{FAMILIES[family][1]}-{run_id}-{run_attempt}"
        diagnostic.update(
            repository=repository, source_sha=source_sha, family=family,
            run_id=run_id, run_attempt=run_attempt, expected_name=expected_name,
        )
        prefix = f"repos/{repository}/actions"
        diagnostic["stage"] = "workflow_run"
        run = read_api(f"{prefix}/runs/{run_id}", stream)
        repository_id = verify_run(run, repository, source_sha, run_id, run_attempt, family)
        diagnostic["stage"] = "artifact_inventory"
        inventory = read_api(f"{prefix}/runs/{run_id}/artifacts?per_page=100", stream)
        selected = select_artifact(inventory, expected_name, diagnostic)
        expected = {
            "repository": repository, "source_sha": source_sha, "run_id": run_id,
            "repository_id": repository_id, "expected_name": expected_name,
        }
        verify_artifact(selected, **expected)
        artifact_id = selected["id"]
        diagnostic["stage"] = "direct_metadata"
        direct = read_api(f"{prefix}/artifacts/{artifact_id}", stream)
        verify_artifact(direct, **expected)
        identity = (
            "id", "name", "digest", "size_in_bytes", "archive_download_url",
            "expired", "workflow_run",
        )
        if any(selected.get(key) != direct.get(key) for key in identity):
            raise ArtifactIdentityError("artifact_list_direct_mismatch")
        diagnostic["stage"] = "archive_bytes"
        hasher = hashlib.sha256()
        observed_size = 0

        def observe(chunk: bytes) -> None:
            nonlocal observed_size
            observed_size += len(chunk)
            if observed_size > direct["size_in_bytes"]:
                raise ArtifactIdentityError("archive_size_mismatch")
            hasher.update(chunk)

        stream(f"{prefix}/artifacts/{artifact_id}/zip", direct["size_in_bytes"], observe)
        if observed_size != direct["size_in_bytes"]:
            raise ArtifactIdentityError("archive_size_mismatch")
        if "sha256:" + hasher.hexdigest() != direct["digest"]:
            raise ArtifactIdentityError("archive_digest_mismatch")
        diagnostic.update(status="transport_verified", stage="complete", artifact_id=artifact_id)
    except ArtifactIdentityError as exc:
        diagnostic["error_code"] = str(exc)
    except Exception:
        # Exception messages may contain API response bodies or local paths.
        diagnostic["error_code"] = "transport_verifier_error"
    return diagnostic


def write_diagnostic(path: Path, diagnostic: dict[str, Any]) -> None:
    encoded = (json.dumps(diagnostic, allow_nan=False, sort_keys=True, indent=2) + "\n").encode()
    if len(encoded) > MAX_DIAGNOSTIC_BYTES:
        raise ArtifactIdentityError("diagnostic_size_invalid")
    # Refuse stale files and symlinks; callers use a fresh RUNNER_TEMP path.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--family", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = vars(parser.parse_args())
    output = args.pop("output")
    diagnostic = inspect_upload(**args)
    try:
        write_diagnostic(output, diagnostic)
    except (OSError, ArtifactIdentityError):
        print("supplemental_artifact_diagnostic_write_failed", file=sys.stderr)
        return 1
    if diagnostic["status"] != "transport_verified":
        print(diagnostic["error_code"], file=sys.stderr)
        return 1
    print("supplemental_artifact_transport_verified_no_authority_granted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
