"""Bounded reuse of internally verified originals with optional local persistence.

No file/receipt import, pickle or new engineering authority is provided. An
optional tenant-authorized repository retains trusted session originals across
processes. Reuse reports zero new numerical work, not new verification. Scientific
strategy comparisons continue to use the existing fresh-comparison entry point.
"""

from __future__ import annotations

from collections import OrderedDict
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import json
import platform
import sysconfig
import os
from pathlib import Path
import re
import sys
import threading
from time import perf_counter_ns, process_time_ns
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from structural_analysis.execution.rc_result_repository import RCResultRepository

import numpy as np
import scipy

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_search import _work
from structural_analysis.model.schema import CanonicalModel


class NewAnalysisRequired(ValueError):
    """No eligible local result exists and new numerical work is not permitted."""


def _native_numeric_identity() -> list[tuple[str, str]]:
    paths = set()
    for package in (np, scipy):
        root = Path(package.__file__).resolve().parent
        for library_root in (root, root.parent / (root.name + ".libs")):
            if library_root.is_dir():
                paths.update(
                    path
                    for path in library_root.rglob("*")
                    if path.is_file()
                    and (
                        ".so" in path.name or path.suffix in (".pyd", ".dll", ".dylib")
                    )
                )
    return [(str(path), study._sha(path.read_bytes())) for path in sorted(paths)]


def _runtime_fingerprint() -> str:
    """Bind package bytes and this interpreter's version/configuration, not a signature."""
    package = Path(__file__).resolve().parents[1]
    files = []
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix in (".py", ".json"):
            raw = path.read_bytes()
            files.append(
                (path.relative_to(package).as_posix(), len(raw), study._sha(raw))
            )
    return study._sha(
        study._bytes(
            {
                "package_files": files,
                "python": sys.version,
                "platform": sys.platform,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "machine": platform.machine(),
                "processor": platform.processor(),
                "byteorder": sys.byteorder,
                "python_executable": sys.executable,
                "platform_tag": sysconfig.get_platform(),
                "native_numeric_libraries": _native_numeric_identity(),
                "thread_environment": {
                    k: os.environ.get(k)
                    for k in (
                        "OPENBLAS_NUM_THREADS",
                        "OPENBLAS_CORETYPE",
                        "OMP_NUM_THREADS",
                        "MKL_NUM_THREADS",
                        "VECLIB_MAXIMUM_THREADS",
                    )
                },
            }
        )
    )


def _inputs(model, request, history_limits, material_limits, terminal_limits, prices):
    """Validate/detach before any output or computation; prices do not identify physics."""
    if type(model) is not CanonicalModel:
        raise ValueError("exact canonical model required")
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact control request required")
    if type(history_limits) is not design.FiberFrameHistoryLimits:
        raise ValueError("explicit history limits required")
    if type(material_limits) is not design.FiberFrameMaterialHistoryLimits:
        raise ValueError("explicit material limits required")
    if (
        terminal_limits is not None
        and type(terminal_limits) is not design.FiberFrameTerminalLimits
    ):
        raise ValueError("typed terminal limits required")
    if prices is not None and type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("typed prices required")
    model = model.detached_analysis_snapshot()
    design._finite_tree(model.to_dict())
    request = decode_bounded_rc_fiber_direct_control_request(
        study._bytes(request.to_dict())
    )
    if not request.targets_m:
        raise ValueError("nonempty targets required")
    return (
        model,
        request,
        design.FiberFrameHistoryLimits(**asdict(history_limits)),
        design.FiberFrameMaterialHistoryLimits(**asdict(material_limits)),
        None
        if terminal_limits is None
        else design.FiberFrameTerminalLimits(**asdict(terminal_limits)),
        None if prices is None else design.FiberFrameMaterialPrices(**asdict(prices)),
    )


@dataclass(frozen=True)
class _Snapshot:
    """Immutable original bytes, admitted only after this session's fresh replay."""

    key: str
    row_bytes: bytes
    artifacts: tuple[tuple[str, bytes], ...]
    seal: str

    @property
    def byte_length(self) -> int:
        return len(self.row_bytes) + sum(len(raw) for _, raw in self.artifacts)

    def check(self) -> None:
        value = {
            "key": self.key,
            "row_hash": study._sha(self.row_bytes),
            "artifacts": [
                (name, study._sha(raw), len(raw)) for name, raw in self.artifacts
            ],
        }
        if study._sha(study._bytes(value)) != self.seal:
            raise ValueError("local snapshot integrity mismatch")
        row = json.loads(self.row_bytes)
        if _work({"rows": [row]})["unknown_work"]:
            raise ValueError("local snapshot contains unknown numerical work")
        if (
            row["status"] != "verified"
            or row["full_reference_verification_pass"] is not True
        ):
            raise ValueError("local snapshot lacks original verification")
        if set(row["artifacts"]) != {name for name, _ in self.artifacts}:
            raise ValueError("local snapshot artifact set mismatch")
        for name, raw in self.artifacts:
            meta = row["artifacts"][name]
            if meta["sha256"] != study._sha(raw) or meta["byte_length"] != len(raw):
                raise ValueError("local snapshot original bytes mismatch")


class RCControlResultSession:
    """Serial, bounded LRU of verified physics in one trusted interpreter.

    ``scope_id`` alone is NOT authentication. Do not expose this object directly
    to untrusted callers. Persistent reads require the repository's host-issued
    tenant credential. No user-supplied receipt can populate either store. Without
    a repository, closing the process still discards reuse.
    """

    def __init__(
        self,
        *,
        source_revision: str,
        scope_id: str,
        max_entries: int = 32,
        max_bytes: int = 64 * 1024 * 1024,
        repository: RCResultRepository | None = None,
    ) -> None:
        if type(source_revision) is not str or not re.fullmatch(
            r"[0-9a-f]{40}", source_revision
        ):
            raise ValueError("40-character source revision required")
        design._identifier(scope_id, "scope_id")
        if type(max_entries) is not int or not 1 <= max_entries <= 128:
            raise ValueError("max_entries must be an integer in [1, 128]")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 1024**3:
            raise ValueError("max_bytes must be an integer in [1, 1073741824]")
        if repository is not None:
            from structural_analysis.execution.rc_result_repository import (
                RCResultRepository,
            )

            if type(repository) is not RCResultRepository:
                raise ValueError("exact persistent RC repository required")
            repository._authorize(scope_id)
        self._repository = repository
        self._source_revision = source_revision
        self._scope_id = scope_id
        self._max_entries, self._max_bytes = max_entries, max_bytes
        self._runtime = _runtime_fingerprint()
        self._entries: OrderedDict[str, _Snapshot] = OrderedDict()
        self._lock = threading.RLock()

    @property
    def source_revision(self) -> str:
        return self._source_revision

    @property
    def scope_id(self) -> str:
        return self._scope_id

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            return sum(entry.byte_length for entry in self._entries.values())

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _check_context(self, scope_id: str) -> None:
        if type(scope_id) is not str or scope_id != self._scope_id:
            raise ValueError("session ownership label mismatch")
        if _runtime_fingerprint() != self._runtime:
            raise ValueError("source/runtime changed; create a new session")

    def _key(
        self, model: CanonicalModel, request: BoundedRCFiberDirectControlRequest
    ) -> str:
        return study._sha(
            study._bytes(
                {
                    "schema_version": "local-rc-control-physics-key.v1",
                    "model_with_provenance": model.to_dict(),
                    "request": request.to_dict(),
                    "source_revision": self._source_revision,
                    "runtime": self._runtime,
                    "scope_id": self._scope_id,
                    "execution": "virgin_reference_then_fresh_full_replay",
                }
            )
        )

    def _capture(self, key: str, row: dict, root: Path) -> _Snapshot | None:
        if (
            row["full_reference_verification_pass"] is not True
            or row["status"] != "verified"
            or _work({"rows": [row]})["unknown_work"]
        ):
            return None
        raw_row = study._bytes(row)
        total = len(raw_row) + sum(
            meta["byte_length"] for meta in row["artifacts"].values()
        )
        if total > self._max_bytes:
            return None  # Admission limit, not truncation or a solver failure.
        artifacts = []
        for name, meta in sorted(row["artifacts"].items()):
            with (root / meta["path"]).open("rb") as stream:
                raw = stream.read(meta["byte_length"] + 1)
            if len(raw) != meta["byte_length"] or study._sha(raw) != meta["sha256"]:
                raise ValueError("fresh original artifact changed before admission")
            artifacts.append((name, raw))
        seal = study._sha(
            study._bytes(
                {
                    "key": key,
                    "row_hash": study._sha(raw_row),
                    "artifacts": [
                        (name, study._sha(raw), len(raw)) for name, raw in artifacts
                    ],
                }
            )
        )
        entry = _Snapshot(key, raw_row, tuple(artifacts), seal)
        entry.check()
        return entry

    def evaluate(
        self,
        model: CanonicalModel,
        request: BoundedRCFiberDirectControlRequest,
        *,
        scope_id: str,
        output_directory: Path,
        history_limits: design.FiberFrameHistoryLimits,
        material_limits: design.FiberFrameMaterialHistoryLimits,
        prices: design.FiberFrameMaterialPrices | None,
        terminal_limits: design.FiberFrameTerminalLimits | None = None,
        fresh: bool = False,
        allow_new_analysis: bool = True,
    ) -> dict[str, Any]:
        """Reuse internally published originals, never call it a fresh replay.

        Persistent admission follows successful evaluation-report publication.
        A failed disk write is an error, never a successful empty cache. Existing
        scientific comparison APIs are unchanged and always execute fresh paths.
        """
        wall, cpu = perf_counter_ns(), process_time_ns()
        stages: dict[str, int] = {}
        mark = perf_counter_ns()
        if type(fresh) is not bool or type(allow_new_analysis) is not bool:
            raise ValueError("explicit boolean execution options required")
        model, request, history_limits, material_limits, terminal_limits, prices = (
            _inputs(
                model, request, history_limits, material_limits, terminal_limits, prices
            )
        )
        stages["input_validation_ns"] = perf_counter_ns() - mark
        with ExitStack() as stack:
            mark = perf_counter_ns()
            stack.enter_context(self._lock)
            stages["thread_lock_wait_ns"] = perf_counter_ns() - mark
            mark = perf_counter_ns()
            self._check_context(scope_id)
            key = self._key(model, request)
            if self._repository is not None:
                self._repository._authorize(scope_id)
            stages["context_and_key_ns"] = perf_counter_ns() - mark
            mark = perf_counter_ns()
            if self._repository is not None:
                stack.enter_context(self._repository.reservation(key, scope_id))
            stages["process_lock_wait_ns"] = perf_counter_ns() - mark
            mark = perf_counter_ns()
            entry = None if fresh else self._entries.get(key)
            origin = "memory" if entry is not None else None
            if entry is None and not fresh and self._repository is not None:
                entry = self._repository._load(key, scope_id)
                if entry is not None:
                    origin = "durable_original"
            if entry is not None:
                entry.check()
                if entry.key != key:
                    raise ValueError("local snapshot physics key mismatch")
            elif not allow_new_analysis:
                raise NewAnalysisRequired("new analysis budget required")
            stages["lookup_and_original_integrity_ns"] = perf_counter_ns() - mark
            root = Path(output_directory)
            root.mkdir(parents=True, exist_ok=False)
            origin_work = None
            new_entry = None
            mark = perf_counter_ns()
            if entry is None:
                row = study._evaluate_design_row(
                    model,
                    None,
                    request,
                    root=root,
                    prices=prices,
                    history_limits=history_limits,
                    material_limits=material_limits,
                    terminal_limits=terminal_limits,
                )
                new_work = _work({"rows": [row]})
                self._check_context(scope_id)
                new_entry = self._capture(key, row, root)
                mode = "fresh_reference_and_replay"
            else:
                row = json.loads(entry.row_bytes)
                origin_work = _work({"rows": [row]})
                row["artifacts"] = {
                    name: study._save(root, f"original/{name}.json", raw)
                    for name, raw in entry.artifacts
                }
                row["invocations"] = []
                row["material_estimate"] = design._estimate(row["quantities"], prices)
                row["screens"] = study._screens(
                    row["performance"], history_limits, material_limits, terminal_limits
                )
                row["selection_eligible"] = all(
                    value["status"] == "pass" for value in row["screens"].values()
                )
                new_work = _work({"rows": []})
                new_work["known_counters"] = {
                    k: 0
                    for k in (
                        "attempted_step_count",
                        "known_linear_solve_count",
                        "known_newton_iteration_count",
                        "unknown_solver_work_attempt_count",
                    )
                }
                mode = "verified_original_reused"
                if key in self._entries:
                    self._entries.move_to_end(key)
            stages["evaluation_or_reuse_with_original_io_ns"] = perf_counter_ns() - mark
            report = {
                "schema_version": "local-rc-control-evaluation.v1",
                "physics_key": key,
                "scope_id": self._scope_id,
                "source_revision": self._source_revision,
                "source_revision_is_attestation": False,
                "runtime_fingerprint": self._runtime,
                "model_checksum": model.canonical_model_checksum,
                "request": request.to_dict(),
                "history_limits": asdict(history_limits),
                "material_limits": asdict(material_limits),
                "terminal_limits": None
                if terminal_limits is None
                else asdict(terminal_limits),
                "prices": None if prices is None else asdict(prices),
                "mode": mode,
                "reuse_origin": origin,
                "row": row,
                "new_work": new_work,
                "original_work_not_recharged": origin_work,
                "original_snapshot_hash": None if entry is None else entry.seal,
                "retained_for_reuse": entry is not None or new_entry is not None,
                "persistent_repository_enabled": self._repository is not None,
                "persistence_receipt": "persistence.json"
                if self._repository is not None
                else None,
                "fresh_reference_verification_this_call": entry is None
                and row["full_reference_verification_pass"] is True,
                "stage_wall_ns": stages,
                "total_wall_ns": perf_counter_ns() - wall,
                "total_process_cpu_ns": process_time_ns() - cpu,
                "timing_scope": "local_call_before_final_report_and_persistent_publication_see_completion_sidecar",
                "claims": {
                    "independent_physical_validation": False,
                    "design_authority": False,
                    "confirmed_currency_savings": False,
                    "performance_improvement": False,
                    "release_approved": False,
                    "persistent_cache": self._repository is not None,
                },
            }
            design._finite_tree(report)
            report["report_hash"] = study._sha(study._bytes(report))
            mark = perf_counter_ns()
            study._save(root, "evaluation.json", study._bytes(report))
            report_write_ns = perf_counter_ns() - mark
            mark = perf_counter_ns()
            if self._repository is not None:
                admitted = entry is not None and origin == "durable_original"
                publish = new_entry if new_entry is not None else entry
                if publish is not None and not admitted:
                    admitted = self._repository._publish(publish, scope_id)
                study._save(
                    root,
                    "persistence.json",
                    study._bytes(
                        {
                            "schema_version": "local-rc-persistence-outcome.v1",
                            "evaluation_hash": report["report_hash"],
                            "physics_key": key,
                            "admitted": admitted,
                            "new_verification_credit": False,
                        }
                    ),
                )
            storage_ns = perf_counter_ns() - mark
            completion = {
                "schema_version": "local-rc-evaluation-completion.v1",
                "evaluation_hash": report["report_hash"],
                "report_write_ns": report_write_ns,
                "persistence_and_receipt_ns": storage_ns,
                "wall_ns_before_completion_write": perf_counter_ns() - wall,
                "process_cpu_ns_before_completion_write": process_time_ns() - cpu,
                "scope": "complete_local_evaluation_except_this_final_sidecar_write",
            }
            study._save(root, "completion.json", study._bytes(completion))
            retain = new_entry if new_entry is not None else entry
            if (
                retain is not None
                and key not in self._entries
                and retain.byte_length <= self._max_bytes
            ):
                while self._entries and (
                    len(self._entries) >= self._max_entries
                    or self.retained_bytes + retain.byte_length > self._max_bytes
                ):
                    self._entries.popitem(last=False)
                self._entries[key] = retain
            return report
