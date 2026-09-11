"""Bounded, process-local reuse of results that this session actually verified.

No file/receipt import, pickle, persistent cache, network authentication, or new
engineering authority is provided. A trusted caller owns each session. Reuse
retains original solver bytes and reports zero *new* numerical work. Scientific
strategy comparisons continue to use the existing fresh-comparison entry point.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import sys
import threading
from time import perf_counter_ns, process_time_ns
from typing import Any

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


def _runtime_fingerprint() -> str:
    """Bind package bytes and this interpreter's version/configuration, not a signature."""
    package = Path(__file__).resolve().parents[1]
    files = []
    for path in sorted(package.rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.json'):
            raw = path.read_bytes()
            files.append((path.relative_to(package).as_posix(), len(raw), study._sha(raw)))
    return study._sha(study._bytes({
        'package_files': files,
        'python': sys.version,
        'platform': sys.platform,
        'numpy': np.__version__,
        'scipy': scipy.__version__,
        'thread_environment': {k: os.environ.get(k) for k in (
            'OPENBLAS_NUM_THREADS', 'OPENBLAS_CORETYPE', 'OMP_NUM_THREADS',
            'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS',
        )},
    }))


def _inputs(model, request, history_limits, material_limits, terminal_limits, prices):
    """Validate/detach before any output or computation; prices do not identify physics."""
    if type(model) is not CanonicalModel:
        raise ValueError('exact canonical model required')
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError('exact control request required')
    if type(history_limits) is not design.FiberFrameHistoryLimits:
        raise ValueError('explicit history limits required')
    if type(material_limits) is not design.FiberFrameMaterialHistoryLimits:
        raise ValueError('explicit material limits required')
    if terminal_limits is not None and type(terminal_limits) is not design.FiberFrameTerminalLimits:
        raise ValueError('typed terminal limits required')
    if prices is not None and type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError('typed prices required')
    model = model.detached_analysis_snapshot()
    design._finite_tree(model.to_dict())
    request = decode_bounded_rc_fiber_direct_control_request(study._bytes(request.to_dict()))
    if not request.targets_m:
        raise ValueError('nonempty targets required')
    return (
        model, request,
        design.FiberFrameHistoryLimits(**asdict(history_limits)),
        design.FiberFrameMaterialHistoryLimits(**asdict(material_limits)),
        None if terminal_limits is None else design.FiberFrameTerminalLimits(**asdict(terminal_limits)),
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
        value = {'key': self.key, 'row_hash': study._sha(self.row_bytes),
                 'artifacts': [(name, study._sha(raw), len(raw)) for name, raw in self.artifacts]}
        if study._sha(study._bytes(value)) != self.seal:
            raise ValueError('local snapshot integrity mismatch')
        row = json.loads(self.row_bytes)
        if row['status'] != 'verified' or row['full_reference_verification_pass'] is not True:
            raise ValueError('local snapshot lacks original verification')
        if set(row['artifacts']) != {name for name, _ in self.artifacts}:
            raise ValueError('local snapshot artifact set mismatch')
        for name, raw in self.artifacts:
            meta = row['artifacts'][name]
            if meta['sha256'] != study._sha(raw) or meta['byte_length'] != len(raw):
                raise ValueError('local snapshot original bytes mismatch')


class RCControlResultSession:
    """Serial, bounded LRU of verified physics in one trusted interpreter.

    ``scope_id`` is an ownership label, NOT authentication. Do not expose this
    object directly to untrusted callers. No existing directory or user-supplied
    receipt can populate it. Closing/restarting the process discards reuse.
    """

    def __init__(self, *, source_revision: str, scope_id: str,
                 max_entries: int = 32, max_bytes: int = 64 * 1024 * 1024) -> None:
        if type(source_revision) is not str or not re.fullmatch(r'[0-9a-f]{40}', source_revision):
            raise ValueError('40-character source revision required')
        design._identifier(scope_id, 'scope_id')
        if type(max_entries) is not int or not 1 <= max_entries <= 128:
            raise ValueError('max_entries must be an integer in [1, 128]')
        if type(max_bytes) is not int or not 1 <= max_bytes <= 1024**3:
            raise ValueError('max_bytes must be an integer in [1, 1073741824]')
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
            raise ValueError('session ownership label mismatch')
        if _runtime_fingerprint() != self._runtime:
            raise ValueError('source/runtime changed; create a new session')

    def _key(self, model: CanonicalModel, request: BoundedRCFiberDirectControlRequest) -> str:
        return study._sha(study._bytes({
            'schema_version': 'local-rc-control-physics-key.v1',
            'model_with_provenance': model.to_dict(),
            'request': request.to_dict(),
            'source_revision': self._source_revision,
            'runtime': self._runtime,
            'scope_id': self._scope_id,
            'execution': 'virgin_reference_then_fresh_full_replay',
        }))

    def _capture(self, key: str, row: dict, root: Path) -> _Snapshot | None:
        if (row['full_reference_verification_pass'] is not True
                or row['status'] != 'verified'
                or _work({'rows': [row]})['unknown_work']):
            return None
        raw_row = study._bytes(row)
        total = len(raw_row) + sum(meta['byte_length'] for meta in row['artifacts'].values())
        if total > self._max_bytes:
            return None  # Admission limit, not truncation or a solver failure.
        artifacts = []
        for name, meta in sorted(row['artifacts'].items()):
            with (root / meta['path']).open('rb') as stream:
                raw = stream.read(meta['byte_length'] + 1)
            if len(raw) != meta['byte_length'] or study._sha(raw) != meta['sha256']:
                raise ValueError('fresh original artifact changed before admission')
            artifacts.append((name, raw))
        seal = study._sha(study._bytes({
            'key': key, 'row_hash': study._sha(raw_row),
            'artifacts': [(name, study._sha(raw), len(raw)) for name, raw in artifacts],
        }))
        entry = _Snapshot(key, raw_row, tuple(artifacts), seal)
        entry.check()
        return entry

    def evaluate(self, model: CanonicalModel, request: BoundedRCFiberDirectControlRequest,
                 *, scope_id: str, output_directory: Path,
                 history_limits: design.FiberFrameHistoryLimits,
                 material_limits: design.FiberFrameMaterialHistoryLimits,
                 prices: design.FiberFrameMaterialPrices | None,
                 terminal_limits: design.FiberFrameTerminalLimits | None = None,
                 fresh: bool = False, allow_new_analysis: bool = True) -> dict[str, Any]:
        """Return a new evaluation; hits rescreen/reprice but never claim new replay.

        Fresh misses execute the existing virgin analysis AND full reference
        verification. Failures are exported but never cached. Cache import and
        cross-process reuse are deliberately unsupported in this first slice.
        """
        if type(fresh) is not bool or type(allow_new_analysis) is not bool:
            raise ValueError('explicit boolean execution options required')
        model, request, history_limits, material_limits, terminal_limits, prices = _inputs(
            model, request, history_limits, material_limits, terminal_limits, prices)
        with self._lock:
            wall, cpu = perf_counter_ns(), process_time_ns()
            self._check_context(scope_id)
            key = self._key(model, request)
            entry = None if fresh else self._entries.get(key)
            if entry is not None:
                entry.check()
                if entry.key != key:
                    raise ValueError('local snapshot physics key mismatch')
            elif not allow_new_analysis:
                raise NewAnalysisRequired('new analysis budget required')
            root = Path(output_directory)
            root.mkdir(parents=True, exist_ok=False)
            origin_work = None
            new_entry = None
            if entry is None:
                row = study._evaluate_design_row(
                    model, None, request, root=root, prices=prices,
                    history_limits=history_limits, material_limits=material_limits,
                    terminal_limits=terminal_limits)
                new_work = _work({'rows': [row]})
                self._check_context(scope_id)
                new_entry = self._capture(key, row, root)
                mode = 'fresh_reference_and_replay'
            else:
                row = json.loads(entry.row_bytes)
                origin_work = _work({'rows': [row]})
                row['artifacts'] = {
                    name: study._save(root, f'original/{name}.json', raw)
                    for name, raw in entry.artifacts
                }
                row['invocations'] = []
                row['material_estimate'] = design._estimate(row['quantities'], prices)
                row['screens'] = study._screens(
                    row['performance'], history_limits, material_limits, terminal_limits)
                row['selection_eligible'] = all(s['status'] == 'pass' for s in row['screens'].values())
                new_work = _work({'rows': []})
                new_work['known_counters'] = {k: 0 for k in (
                    'attempted_step_count', 'known_linear_solve_count',
                    'known_newton_iteration_count', 'unknown_solver_work_attempt_count')}
                mode = 'verified_original_reused'
                self._entries.move_to_end(key)
            report = {
                'schema_version': 'local-rc-control-evaluation.v1',
                'physics_key': key, 'scope_id': self._scope_id,
                'source_revision': self._source_revision,
                'source_revision_is_attestation': False,
                'runtime_fingerprint': self._runtime,
                'model_checksum': model.canonical_model_checksum,
                'request': request.to_dict(),
                'history_limits': asdict(history_limits),
                'material_limits': asdict(material_limits),
                'terminal_limits': None if terminal_limits is None else asdict(terminal_limits),
                'prices': None if prices is None else asdict(prices),
                'mode': mode, 'row': row,
                'new_work': new_work, 'original_work_not_recharged': origin_work,
                'original_snapshot_hash': None if entry is None else entry.seal,
                'retained_for_reuse': entry is not None or new_entry is not None,
                'fresh_reference_verification_this_call': entry is None and row['full_reference_verification_pass'] is True,
                'total_wall_ns': perf_counter_ns() - wall,
                'total_process_cpu_ns': process_time_ns() - cpu,
                'timing_scope': 'local_call_including_context_checks_and_original_export_excluding_final_report_write',
                'claims': {'independent_physical_validation': False, 'design_authority': False,
                           'confirmed_currency_savings': False, 'performance_improvement': False,
                           'release_approved': False, 'persistent_cache': False},
            }
            design._finite_tree(report)
            report['report_hash'] = study._sha(study._bytes(report))
            study._save(root, 'evaluation.json', study._bytes(report))
            # Failed publication never admits a new entry. A forced fresh run
            # does not overwrite the first successful original for this key.
            if new_entry is not None and key not in self._entries:
                while self._entries and (len(self._entries) >= self._max_entries
                        or self.retained_bytes + new_entry.byte_length > self._max_bytes):
                    self._entries.popitem(last=False)
                self._entries[key] = new_entry
            return report
