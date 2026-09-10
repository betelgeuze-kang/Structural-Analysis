"""Authenticated, immutable HTTP snapshots of completed RC search artifacts.

The host explicitly pins a report hash and supplies tenant authorization. This
mount owns byte integrity and access only; Workbench still validates engineering
bindings. It does not execute a solver, fit a policy, or configure a listener.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
from http import HTTPStatus
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any

from structural_analysis.execution.job_http_api import JobHttpResponse

PROFILE = "immutable-rc-search-artifact-http.v1"
_META_MAX = 2 * 1024**2
_TOTAL_MAX = 1024**3
_HASH = re.compile(r"sha256:[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")
_MOUNT = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
_ROLES = frozenset(
    {
        "model",
        "result",
        "checkpoint",
        "verification",
        "analysis_started",
        "analysis_outcome",
        "verification_started",
        "verification_outcome",
    }
)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _document(raw: bytes, key: str) -> dict:
    def pairs(items):
        out = {}
        for name, value in items:
            if name in out:
                raise ValueError("duplicate artifact document key")
            out[name] = value
        return out

    def invalid(value):
        raise ValueError("non-finite artifact value")

    try:
        d = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid
        )
        if type(d) is not dict or not _HASH.fullmatch(d.get(key, "")):
            raise ValueError("artifact document hash missing")
        canonical = json.dumps(
            {k: v for k, v in d.items() if k != key},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        if _sha(canonical) != d[key]:
            raise ValueError("artifact document hash mismatch")
        return d
    except (UnicodeError, TypeError, OverflowError, RecursionError) as exc:
        raise ValueError("invalid artifact document") from exc


def _path(value: str) -> bool:
    if (
        type(value) is not str
        or len(value) > 512
        or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value)
    ):
        return False
    parts = value.split("/")
    if any(not p or p in {".", ".."} for p in parts) or re.match(
        r"[A-Za-z][A-Za-z0-9+.-]*:", value
    ):
        return False
    name = parts[-1]
    return not (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
        or ".env." in name
    )


@dataclass(frozen=True, init=False)
class RcSearchArtifactBundle:
    """A registered snapshot; never consults mutable files on an HTTP request."""

    report_hash: str
    artifacts: Mapping[str, bytes]

    @classmethod
    def from_reader(
        cls, reader: Callable[[str, int], bytes], *, expected_report_hash: str
    ):
        """Read only the named, hash-bound graph via a host's bounded reader.

        The reader is a trusted host adapter, not a caller-controlled HTTP URL.
        Unreferenced source-directory files never enter the snapshot.
        """
        if type(expected_report_hash) is not str or not _HASH.fullmatch(
            expected_report_hash
        ):
            raise ValueError("pinned report hash required")
        files: dict[str, bytes] = {}
        total = 0

        def read(path: str, maximum: int, ref: dict | None = None):
            nonlocal total
            if not _path(path):
                raise ValueError("artifact path invalid")
            if ref is not None and (
                type(ref.get("byte_length")) is not int
                or not 0 < ref["byte_length"] <= maximum
                or not _HASH.fullmatch(ref.get("sha256", ""))
            ):
                raise ValueError("artifact byte reference invalid")
            raw = files.get(path)
            if raw is None:
                raw = reader(path, min(maximum, _TOTAL_MAX - total))
                if (
                    type(raw) is not bytes
                    or len(raw) > maximum
                    or len(raw) > _TOTAL_MAX - total
                ):
                    raise ValueError("artifact byte budget exceeded")
                files[path] = raw
                total += len(raw)
            if ref is not None and (
                len(raw) != ref["byte_length"] or _sha(raw) != ref["sha256"]
            ):
                raise ValueError("artifact byte reference mismatch")
            return raw

        result = _document(read("result.json", _META_MAX), "report_hash")
        if (
            result["report_hash"] != expected_report_hash
            or result.get("schema_version")
            != "experimental-rc-control-candidate-search.v2"
        ):
            raise ValueError("pinned search result mismatch")
        plan = _document(read("plan.json", _META_MAX), "plan_hash")
        training = _document(read("historical-training.json", _META_MAX), "report_hash")
        policy = _document(read("policy.json", _META_MAX), "policy_hash")
        if (
            plan.get("schema_version")
            != "experimental-rc-control-candidate-search-plan.v2"
            or result.get("plan_hash") != plan["plan_hash"]
            or result.get("historical_training_cost") != training
            or plan.get("training_report_hash") != training["report_hash"]
            or plan.get("policy_hash") != policy["policy_hash"]
            or training.get("policy_hash") != policy["policy_hash"]
        ):
            raise ValueError("search metadata binding mismatch")
        pool = plan.get("pool")
        if (
            type(pool) is not list
            or not 2 <= len(pool) <= 17
            or result.get("candidate_denominator") != len(pool)
        ):
            raise ValueError("bounded pool required")
        ids = [p.get("candidate_id") for p in pool]
        if (
            ids[0] != "baseline"
            or any(type(i) is not str or not _ID.fullmatch(i) for i in ids)
            or len(set(ids)) != len(ids)
        ):
            raise ValueError("pool identity invalid")
        for row in pool:
            ref = row["model_artifact"]
            expected = f"pool/{row['candidate_id']}.json"
            if ref.get("path") != expected or ref.get("sha256") != row.get(
                "model_checksum"
            ):
                raise ValueError("pool model reference invalid")
            read(expected, 16 * 1024**2, ref)
        arms = result.get("arms")
        if type(arms) is not dict or set(arms) != {"price_order", "learned_order"}:
            raise ValueError("both online search arms required")
        outcomes = dict(arms)
        if result.get("oracle") is not None:
            outcomes["exhaustive_oracle"] = result["oracle"]
        for name, outcome in outcomes.items():
            path = f"{name}/comparison.json"
            if (
                outcome.get("status") != "completed"
                or outcome.get("comparison_path") != path
                or outcome.get("unknown_work_until_outcome") is not False
            ):
                raise ValueError("completed bounded arm required")
            comparison = _document(read(path, _META_MAX), "report_hash")
            if (
                comparison["report_hash"] != outcome.get("comparison_hash")
                or comparison.get("schema_version")
                != "experimental-rc-control-design-comparison.v1"
            ):
                raise ValueError("comparison identity mismatch")
            rows = comparison.get("rows")
            if (
                type(rows) is not list
                or not 2 <= len(rows) <= 17
                or len(rows) != outcome.get("request_count")
            ):
                raise ValueError("comparison denominator invalid")
            row_ids = [r.get("candidate_id") for r in rows]
            if (
                row_ids[0] != "baseline"
                or len(set(row_ids)) != len(row_ids)
                or not set(row_ids) <= set(ids)
            ):
                raise ValueError("comparison pool mismatch")
            for row in rows:
                refs = row.get("artifacts")
                if type(refs) is not dict or not set(refs) <= _ROLES:
                    raise ValueError("comparison artifact role invalid")
                for role, ref in refs.items():
                    relative = f"{row['candidate_id']}/{role.replace('_', '-')}.json"
                    if type(ref) is not dict or ref.get("path") != relative:
                        raise ValueError("comparison artifact path invalid")
                    maximum = (
                        64 if role == "result" else 128 if role == "checkpoint" else 16
                    ) * 1024**2
                    read(f"{name}/{relative}", maximum, ref)
        bundle = object.__new__(cls)
        object.__setattr__(bundle, "report_hash", expected_report_hash)
        object.__setattr__(bundle, "artifacts", MappingProxyType(dict(files)))
        return bundle

    @classmethod
    def from_directory(cls, directory: Path, *, expected_report_hash: str):
        """Load a host-owned completed directory; reject links and changing files.

        Hosts must exclude concurrent writers while publishing this snapshot.
        No filesystem paths or reads are accepted from HTTP clients.
        """
        requested = Path(directory).absolute()
        if (
            any(p.is_symlink() for p in (requested, *requested.parents))
            or not requested.is_dir()
        ):
            raise ValueError("artifact directory must be a real directory")
        root = requested.resolve(strict=True)

        def reader(relative: str, maximum: int) -> bytes:
            path = root.joinpath(*relative.split("/"))
            if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve(
                strict=True
            ).is_relative_to(root):
                raise ValueError("artifact links are not permitted")
            before = path.stat()
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise ValueError("artifact file exceeds profile")
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                raw = stream.read(maximum + 1)
                after = os.fstat(stream.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
                opened.st_mtime_ns,
            ) or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise ValueError("artifact changed during snapshot")
            return raw

        return cls.from_reader(reader, expected_report_hash=expected_report_hash)


class RcSearchArtifactWSGIApplication:
    """Mount pre-registered bundles under /v1/rc-search/{study}/{artifact}."""

    def __init__(
        self,
        mounts: Mapping[tuple[str, str], RcSearchArtifactBundle],
        *,
        authorize: Callable[[str, str], bool],
    ):
        if not callable(authorize) or not 1 <= len(mounts) <= 32:
            raise ValueError("explicit authorization and bounded mounts required")
        frozen = {}
        for (tenant, study), bundle in mounts.items():
            if (
                type(tenant) is not str
                or not _ID.fullmatch(tenant)
                or type(study) is not str
                or not _MOUNT.fullmatch(study)
                or type(bundle) is not RcSearchArtifactBundle
            ):
                raise ValueError("registered tenant/study/bundle invalid")
            frozen[(tenant, study)] = bundle
        if (
            sum(sum(map(len, b.artifacts.values())) for b in frozen.values())
            > _TOTAL_MAX
        ):
            raise ValueError("total mounted bytes exceed profile")
        self._mounts = MappingProxyType(frozen)
        self._authorize = authorize

    def handle(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> JobHttpResponse:
        def response(status, payload, *, content_type="application/json"):
            return JobHttpResponse(
                status,
                {
                    "content-type": content_type,
                    "content-length": str(len(payload)),
                    "cache-control": "no-store",
                    "x-content-type-options": "nosniff",
                    "x-structural-rc-search-api": PROFILE,
                },
                payload,
            )

        def error(status, code):
            return response(
                status,
                json.dumps(
                    {"schema_version": PROFILE, "error": code}, separators=(",", ":")
                ).encode(),
            )

        match = re.fullmatch(r"/v1/rc-search/([A-Za-z][A-Za-z0-9_-]{0,63})/(.+)", path)
        if match is None or not _path(match[2]):
            return error(404, "artifact_not_found")
        values = {k.lower(): v for k, v in (headers or {}).items()}
        tenant, bearer = (
            values.get("x-structural-tenant", ""),
            values.get("authorization", ""),
        )
        if not re.fullmatch(r"[\x21-\x7e]{1,128}", tenant) or not re.fullmatch(
            r"Bearer [\x21-\x7e]{1,4096}", bearer
        ):
            return error(401, "unauthorized")
        try:
            authorized = self._authorize(tenant, bearer[7:]) is True
        except Exception:
            authorized = False
        if not authorized:
            return error(401, "unauthorized")
        if method != "GET":
            return error(405, "read_only")
        if body:
            return error(400, "unexpected_body")
        bundle = self._mounts.get((tenant, match[1]))
        raw = None if bundle is None else bundle.artifacts.get(match[2])
        return error(404, "artifact_not_found") if raw is None else response(200, raw)

    def __call__(self, environ: Mapping[str, Any], start_response):
        headers = {
            key[5:].replace("_", "-"): str(value)
            for key, value in environ.items()
            if key.startswith("HTTP_")
        }
        # This read-only mount never consumes request bodies, even with malformed
        # lengths or transfer encodings. A listener's request framing is separate.
        length = str(environ.get("CONTENT_LENGTH") or "0")
        body = (
            b"rejected"
            if length != "0" or environ.get("HTTP_TRANSFER_ENCODING")
            else b""
        )
        path = str(environ.get("PATH_INFO") or "/")
        if environ.get("QUERY_STRING"):
            path += "?"
        response = self.handle(
            str(environ.get("REQUEST_METHOD") or "GET"),
            path,
            headers=headers,
            body=body,
        )
        start_response(
            f"{response.status} {HTTPStatus(response.status).phrase}",
            [(k.title(), v) for k, v in response.headers.items()],
        )
        return (response.body,)
