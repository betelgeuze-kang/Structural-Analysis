"""Consume one supplemental artifact by verified ID, without granting authority.

The caller owns bounded run/list lookup retries. This boundary parses those saved
API responses strictly, rechecks the selected ID, verifies the ZIP bytes, and
extracts into a fresh private directory. The existing Sigstore and receipt checks
must still run afterwards. Missing/expired evidence is unavailable, not verified;
ambiguous, malformed, changed or corrupt evidence is a hard failure.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
from typing import Any, BinaryIO
import unicodedata
import zipfile

from strict_json import StrictJSONError, strict_json_loads
from verify_supplemental_artifact_identity import (
    ArtifactIdentityError,
    FAMILIES,
    MAX_ARCHIVE_BYTES,
    MAX_JSON_BYTES,
    REPOSITORY,
    SHA,
    Stream,
    gh_stream,
    positive_integer,
    read_api,
    select_artifact,
    verify_artifact,
    verify_run,
    write_diagnostic,
)

MAX_MEMBERS = 20_000
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
CHUNK_BYTES = 64 * 1024
IDENTITY_KEYS = (
    "id", "name", "digest", "size_in_bytes", "archive_download_url",
    "expired", "workflow_run",
)


def read_saved_api(path: Path) -> dict[str, Any]:
    """Reject symlinks, non-files, oversized responses and ambiguous JSON."""
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ArtifactIdentityError("saved_api_not_regular")
    with path.open("rb") as handle:
        raw = handle.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ArtifactIdentityError("api_response_too_large")
    try:
        payload = strict_json_loads(raw)
    except (StrictJSONError, RecursionError) as exc:
        raise ArtifactIdentityError("api_json_invalid") from exc
    if type(payload) is not dict:
        raise ArtifactIdentityError("api_object_required")
    return payload


def portable_member(info: zipfile.ZipInfo) -> tuple[str, bool]:
    """Return a canonical relative member name, never a filesystem escape."""
    raw = info.orig_filename
    is_dir = info.is_dir()
    name = raw[:-1] if is_dir else raw
    path = PurePosixPath(name)
    mode = (info.external_attr >> 16) & 0xFFFF
    allowed_modes = {0, stat.S_IFDIR if is_dir else stat.S_IFREG}
    if (
        raw != info.filename or not name or len(name) > 2048
        or "\\" in name or any(char in name for char in '<>:"|?*')
        or unicodedata.normalize("NFC", name) != name
        or unicodedata.normalize("NFKC", name) != name
        or any(unicodedata.category(char) in {"Cc", "Cf"} for char in name)
        or path.is_absolute() or path.as_posix() != name
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or stat.S_IFMT(mode) not in allowed_modes or info.flag_bits & 1
        or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
        or not 0 <= info.file_size <= MAX_EXPANDED_BYTES
        or not 0 <= info.compress_size <= MAX_ARCHIVE_BYTES
        or (is_dir and info.file_size != 0)
    ):
        raise ArtifactIdentityError("archive_member_invalid")
    for part in path.parts:
        stem = part.split(".", 1)[0].casefold()
        if (
            part.endswith((".", " "))
            or stem in {"con", "prn", "aux", "nul", "clock$", "conin$", "conout$"}
            or (len(stem) == 4 and stem[:3] in {"com", "lpt"} and stem[3] in "123456789")
        ):
            raise ArtifactIdentityError("archive_member_invalid")
    return name, is_dir


def extract_archive(archive_file: BinaryIO, target: Path) -> None:
    """Preflight the entire directory; clean only the directory we created."""
    for parent in (target.parent, *target.parent.parents):
        if parent.is_symlink():
            raise ArtifactIdentityError("extraction_parent_symlink")
    if target.exists() or target.is_symlink():
        raise ArtifactIdentityError("extraction_target_exists")
    created = False
    try:
        with zipfile.ZipFile(archive_file) as archive:
            members = archive.infolist()
            if not 1 <= len(members) <= MAX_MEMBERS:
                raise ArtifactIdentityError("archive_member_count_invalid")
            planned = []
            explicit: set[str] = set()
            # Reserve casefolded parent names too, preventing file/dir conflicts.
            kinds: dict[str, str] = {}
            spellings: dict[str, str] = {}
            expanded = 0
            for info in members:
                name, is_dir = portable_member(info)
                parts = name.split("/")
                for index in range(1, len(parts) + 1):
                    spelling = "/".join(parts[:index])
                    key = spelling.casefold()
                    kind = "dir" if index < len(parts) or is_dir else "file"
                    if (key in kinds and kinds[key] != kind) or (
                        key in spellings and spellings[key] != spelling
                    ):
                        raise ArtifactIdentityError("archive_path_collision")
                    kinds[key], spellings[key] = kind, spelling
                folded = name.casefold()
                if folded in explicit:
                    raise ArtifactIdentityError("archive_path_collision")
                explicit.add(folded)
                expanded += info.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise ArtifactIdentityError("archive_expansion_too_large")
                planned.append((info, name, is_dir))
            target.mkdir(mode=0o700)  # Exclusive; never merge with stale evidence.
            created = True
            for info, name, is_dir in planned:
                destination = target.joinpath(*name.split("/"))
                if is_dir:
                    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                written = 0
                with archive.open(info) as source, destination.open("xb") as output:
                    while chunk := source.read(CHUNK_BYTES):
                        written += len(chunk)
                        if written > info.file_size:
                            raise ArtifactIdentityError("archive_member_size_mismatch")
                        output.write(chunk)
                if written != info.file_size:
                    raise ArtifactIdentityError("archive_member_size_mismatch")
    except Exception:
        if created:
            shutil.rmtree(target)
        raise


def consume(
    *, repository: str, source_sha: str, run_id: int, run_attempt: int,
    family: str, run_json: Path, inventory_json: Path, target: Path,
    stream: Stream = gh_stream,
) -> dict[str, Any]:
    diagnostic: dict[str, Any] = {
        "schema_version": "supplemental-artifact-consumer-diagnostic.v1",
        "status": "rejected", "stage": "context", "error_code": None,
        "release_authority": False, "independent_verification": False,
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
            repository=repository, source_sha=source_sha, run_id=run_id,
            run_attempt=run_attempt, family=family, expected_name=expected_name,
        )
        diagnostic["stage"] = "workflow_run"
        run = read_saved_api(run_json)
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise ArtifactIdentityError("workflow_run_not_successful")
        repository_id = verify_run(run, repository, source_sha, run_id, run_attempt, family)
        diagnostic["stage"] = "artifact_inventory"
        selected = select_artifact(read_saved_api(inventory_json), expected_name, diagnostic)
        expected = dict(repository=repository, source_sha=source_sha, run_id=run_id,
                        repository_id=repository_id, expected_name=expected_name)
        verify_artifact(selected, **expected)
        artifact_id = selected["id"]
        prefix = f"repos/{repository}/actions/artifacts/{artifact_id}"
        diagnostic["stage"] = "direct_metadata"
        direct = read_api(prefix, stream)
        verify_artifact(direct, **expected)
        if any(selected.get(key) != direct.get(key) for key in IDENTITY_KEYS):
            raise ArtifactIdentityError("artifact_list_direct_mismatch")
        diagnostic["stage"] = "archive_bytes"
        with tempfile.TemporaryFile() as archive_file:
            hasher = hashlib.sha256()
            size = 0

            def observe(chunk: bytes) -> None:
                nonlocal size
                size += len(chunk)
                if size > direct["size_in_bytes"]:
                    raise ArtifactIdentityError("archive_size_mismatch")
                hasher.update(chunk)
                archive_file.write(chunk)

            stream(prefix + "/zip", direct["size_in_bytes"], observe)
            if size != direct["size_in_bytes"]:
                raise ArtifactIdentityError("archive_size_mismatch")
            if "sha256:" + hasher.hexdigest() != direct["digest"]:
                raise ArtifactIdentityError("archive_digest_mismatch")
            diagnostic["stage"] = "archive_extraction"
            archive_file.seek(0)
            extract_archive(archive_file, target)
        diagnostic.update(status="materialized", stage="complete", artifact_id=artifact_id)
    except ArtifactIdentityError as exc:
        diagnostic["error_code"] = str(exc)
        # Expiry may happen between list and direct lookup; still no credit.
        if str(exc) in {"artifact_missing", "artifact_expired"}:
            diagnostic.update(status="unavailable", availability=str(exc).removeprefix("artifact_"))
    except zipfile.BadZipFile:
        diagnostic["error_code"] = "archive_zip_invalid"
    except Exception:
        diagnostic["error_code"] = "artifact_consumer_error"
    return diagnostic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--family", required=True)
    parser.add_argument("--run-json", required=True, type=Path)
    parser.add_argument("--inventory-json", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--diagnostic", required=True, type=Path)
    args = vars(parser.parse_args())
    diagnostic_path = args.pop("diagnostic")
    result = consume(**args)
    try:
        write_diagnostic(diagnostic_path, result)
    except (OSError, ArtifactIdentityError):
        print("supplemental_consumer_diagnostic_write_failed", file=sys.stderr)
        return 1
    if result["status"] == "unavailable":
        print(result["availability"])
        return 0
    if result["status"] != "materialized":
        print(result["error_code"], file=sys.stderr)
        return 1
    print("available")  # Bytes only; NOT a signature/physics/approval assertion.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
