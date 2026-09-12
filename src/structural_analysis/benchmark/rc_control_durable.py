"""Local RC reuse through the existing durable worker, not imported receipts.

One immutable physics key owns one existing DurableJobService database. This
bounds claiming to that request without changing the shared service's queue or
borrowing another job's lease. The store is trusted, single-host storage, not an
untrusted artifact import or network authentication service. Its administrator
must protect the root and supply credentials out of band on every invocation.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_search import _work
from structural_analysis.benchmark.rc_control_reuse import (
    NewAnalysisRequired,
    RCControlResultSession,
    _inputs,
)
from structural_analysis.execution.job_service import (
    DurableJobService,
    build_job_completion_evidence,
)
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)
from structural_analysis.execution.rc_fiber_job_contract import (
    CONSTANT_RC_FIBER_JOB_RESULT_SCHEMA_VERSION,
    RC_FIBER_JOB_RESULT_SCHEMA_VERSION,
    RC_FIBER_JOB_VALIDATOR_ID,
    validate_rc_fiber_job_request,
    validate_rc_fiber_job_result,
)


def _safe_directory(path: Path) -> Path:
    # Reject every existing symlink, including ancestors, rather than resolving
    # an attacker-selected destination into the trusted cache root.
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("durable store symlinks are unsupported")
    return path


class DurableRCControlResultSession(RCControlResultSession):
    """Price/screen-independent local disk reuse with chunk-boundary pause.

    Every cache miss uses the existing worker's real solve and full replay.
    Every disk hit checks immutable request, event chain, invocation records,
    original response, checkpoint and completion evidence without new Newton work.
    No directory/JSON supplied by a caller can be promoted into a valid entry.
    File hashes are integrity checks, not protection against a malicious local
    administrator. There is no cross-host database sharing or garbage collection.
    """

    def __init__(
        self,
        *,
        store_root: Path,
        source_revision: str,
        scope_id: str,
        authorization_token: str,
        worker_token: str,
        chunk_target_count: int = 255,
        max_chunks_per_call: int = 255,
    ) -> None:
        super().__init__(source_revision=source_revision, scope_id=scope_id)
        for name, number in (
            ("chunk_target_count", chunk_target_count),
            ("max_chunks_per_call", max_chunks_per_call),
        ):
            if type(number) is not int or not 1 <= number <= 255:
                raise ValueError(f"{name} must be an integer in [1, 255]")
        for token in (authorization_token, worker_token):
            if type(token) is not str or len(token) < 16:
                raise ValueError(
                    "out-of-band credentials of at least 16 characters required"
                )
        self._root = _safe_directory(Path(store_root))
        self._tenant_token = authorization_token
        self._worker_token = worker_token
        self._chunk_size = chunk_target_count
        self._max_chunks = max_chunks_per_call

    def _request(self, model, request, key):
        chunk = min(self._chunk_size, len(request.targets_m))
        value = {
            "schema_version": "structural-analysis-job-request.v3",
            "operation": "bounded_rc_fiber_direct_control",
            "case_id": "local-" + key.split(":")[1],
            "source_revision": self.source_revision,
            "model": model.canonical_payload(),
            "config": request.to_dict(),
            "execution_config": {
                "chunk_target_count": chunk,
                "maximum_api_invocations": 2
                * math.ceil(len(request.targets_m) / chunk),
            },
            "result_contract": CONSTANT_RC_FIBER_JOB_RESULT_SCHEMA_VERSION
            if request.constant_nodal_loads
            else RC_FIBER_JOB_RESULT_SCHEMA_VERSION,
        }
        validate_rc_fiber_job_request(value)
        return value

    def _store(self, key):
        path = _safe_directory(self._root / key.split(":")[1])
        for child in (
            "jobs.sqlite3",
            "jobs.sqlite3-wal",
            "jobs.sqlite3-shm",
            "blobs",
            "blobs/sha256",
        ):
            _safe_directory(path / child)
        return DurableJobService(
            path,
            tenant_tokens={self.scope_id: self._tenant_token},
            worker_tokens={"local-rc": self._worker_token},
            worker_tenants={"local-rc": [self.scope_id]},
        )

    def _evidence(self, service, job):
        auth = {"tenant_id": self.scope_id, "authorization_token": self._tenant_token}
        evidence = service.read_rc_invocation_evidence(job.job_id, **auth)
        rows = []
        for record in evidence["invocations"]:
            raw = service.read_rc_invocation_artifact(
                job.job_id, ordinal=record["ordinal"], **auth
            )
            outcome = strict_json_object_bytes(raw, maximum_bytes=576 * 1024 * 1024)
            payload = (
                outcome["api_result"]
                if outcome["phase"] == "analysis"
                else outcome["verification_report"]
            )
            metrics = (
                (payload or {}).get("metrics", {})
                if outcome["phase"] == "analysis"
                else (payload or {})
            )
            work = metrics.get(
                "control_work"
                if outcome["phase"] == "analysis"
                else "replay_control_work"
            )
            rows.append(
                {
                    "phase": outcome["phase"],
                    "work": work,
                    "unknown_execution_work": outcome["unavailable_execution_work"],
                    "ordinal": record["ordinal"],
                }
            )
        for ordinal in evidence["pending_ordinals"]:
            rows.append(
                {
                    "phase": "unrecorded",
                    "work": None,
                    "unknown_execution_work": True,
                    "ordinal": ordinal,
                }
            )
        return evidence, rows

    def evaluate(
        self,
        model,
        request,
        *,
        scope_id,
        output_directory,
        history_limits,
        material_limits,
        prices,
        terminal_limits=None,
        fresh=False,
        allow_new_analysis=True,
    ) -> dict[str, Any]:
        if type(fresh) is not bool or type(allow_new_analysis) is not bool:
            raise ValueError("explicit boolean execution options required")
        if fresh:
            # A requested fresh experiment always uses the old evaluator and
            # never overwrites, updates, or silently bypasses a durable entry.
            return super().evaluate(
                model,
                request,
                scope_id=scope_id,
                output_directory=output_directory,
                history_limits=history_limits,
                material_limits=material_limits,
                prices=prices,
                terminal_limits=terminal_limits,
                fresh=True,
                allow_new_analysis=allow_new_analysis,
            )
        started, started_cpu = perf_counter_ns(), process_time_ns()
        phase_times = {}
        mark = started
        model, request, history_limits, material_limits, terminal_limits, prices = (
            _inputs(
                model, request, history_limits, material_limits, terminal_limits, prices
            )
        )
        self._check_context(scope_id)
        # Chunking changes replay/work accounting, so it cannot silently alter
        # the execution configuration of an already stored job.
        key = study._sha(
            study._bytes(
                {
                    "physics": self._key(model, request),
                    "chunk_target_count": self._chunk_size,
                    "profile": "local-durable-rc.v1",
                }
            )
        )
        job_request = self._request(model, request, key)
        quantities = design.calculate_fiber_frame_member_quantities(model)
        estimate = design._estimate(quantities, prices)
        phase_times["input_and_runtime_checks_ns"] = perf_counter_ns() - mark
        path = _safe_directory(self._root / key.split(":")[1])
        if not allow_new_analysis and not (path / "jobs.sqlite3").is_file():
            raise NewAnalysisRequired("no persisted result exists")
        output = _safe_directory(Path(output_directory))
        if output.exists():
            raise FileExistsError("new output directory required")
        mark = perf_counter_ns()
        service = self._store(key)
        auth = {"tenant_id": scope_id, "authorization_token": self._tenant_token}
        job = service.submit_job(idempotency_key="physics", request=job_request, **auth)
        if not allow_new_analysis and job.status != "succeeded":
            raise NewAnalysisRequired("persisted job is not completed")
        before, prior_rows = self._evidence(service, job)
        owned_ordinals: set[int] = set()
        reused = job.status == "succeeded"
        phase_times["store_lookup_ns"] = perf_counter_ns() - mark
        mark = perf_counter_ns()
        completed_chunks = 0
        while (
            allow_new_analysis
            and job.status in ("queued", "checkpointed", "running")
            and completed_chunks < self._max_chunks
        ):
            if before["pending_ordinals"]:
                break  # Never silently retry abandoned, unknown numerical work.
            claim = service.claim_next(
                worker_id="local-rc",
                authorization_token=self._worker_token,
                tenant_id=scope_id,
                lease_seconds=300,
            )
            if claim is None:
                job = service.get_job(job.job_id, **auth)
                break
            if claim.job.job_id != job.job_id:
                raise ValueError("isolated physics store contains an unexpected job")
            reservation_start = service.read_execution_budget(
                job.job_id,
                worker_id="local-rc",
                authorization_token=self._worker_token,
                lease_token=claim.lease_token,
            )["reserved_attempts"]
            # The unchanged chunk worker reserves at most analysis + verification.
            # Restrict this call's accounting to its own lease, not work another
            # process may finish while we read the durable result.
            owned_ordinals.update((reservation_start + 1, reservation_start + 2))
            job = execute_rc_fiber_direct_control_claim(
                service,
                claim,
                worker_id="local-rc",
                authorization_token=self._worker_token,
            )
            completed_chunks += 1
        phase_times["worker_and_durable_publication_ns"] = perf_counter_ns() - mark
        mark = perf_counter_ns()
        self._check_context(scope_id)
        integrity = service.validate_integrity(job.job_id, **auth)
        evidence, invocation_rows = self._evidence(service, job)
        new_rows = [row for row in invocation_rows if row["ordinal"] in owned_ordinals]
        new_work = _work({"rows": [{"invocations": new_rows}]})
        if not new_rows:
            new_work["known_counters"] = {
                name: 0
                for name in (
                    "attempted_step_count",
                    "known_linear_solve_count",
                    "known_newton_iteration_count",
                    "unknown_solver_work_attempt_count",
                )
            }
        unknown_origin = _work({"rows": [{"invocations": invocation_rows}]})[
            "unknown_work"
        ]
        raw_artifacts = {"request": service.read_request(job.job_id, **auth)}
        row = {
            "candidate_id": "baseline",
            "status": job.status,
            "quantities": quantities,
            "material_estimate": estimate,
            "performance": None,
            "screens": None,
            "full_reference_verification_pass": False,
            "selection_eligible": False,
            "invocations": new_rows,
            "artifacts": {},
        }
        if job.status == "succeeded":
            raw = service.read_result(job.job_id, **auth)
            original_evidence = service.read_evidence(job.job_id, **auth)
            value = strict_json_object_bytes(raw, maximum_bytes=576 * 1024 * 1024)
            checkpoint = (
                service.read_checkpoint(job.job_id, **auth) if job.checkpoint else None
            )
            report = validate_rc_fiber_job_result(
                value,
                request=job_request,
                execution_budget=evidence["execution_budget"],
                checkpoint=checkpoint,
            )
            expected = build_job_completion_evidence(
                job_id=job.job_id,
                request_hash=job.request.content_hash,
                checkpoint_hash=None
                if job.checkpoint is None
                else job.checkpoint.content_hash,
                result_bytes=raw,
                validation_report=report,
                validator_id=RC_FIBER_JOB_VALIDATOR_ID,
            )
            if study._bytes(expected) != original_evidence:
                raise ValueError(
                    "persisted completion evidence differs from the validated result"
                )
            raw_artifacts.update(result=raw, evidence=original_evidence)
            if checkpoint is not None:
                raw_artifacts["checkpoint"] = checkpoint
            payload = value["api_result"]
            history = payload["response_history"]
            if request.constant_nodal_loads:
                history = [payload["preload_response"], *history]
            row["performance"] = study._performance(history)
            row["screens"] = study._screens(
                row["performance"], history_limits, material_limits, terminal_limits
            )
            row["full_reference_verification_pass"] = not unknown_origin
            row["status"] = "verified" if not unknown_origin else "unknown_work"
            row["selection_eligible"] = not unknown_origin and all(
                r["status"] == "pass" for r in row["screens"].values()
            )
        phase_times["integrity_and_rescreen_ns"] = perf_counter_ns() - mark
        mark = perf_counter_ns()
        output.mkdir(parents=True, exist_ok=False)
        row["artifacts"] = {
            name: study._save(output, name + ".json", raw)
            for name, raw in raw_artifacts.items()
        }
        phase_times["original_export_ns"] = perf_counter_ns() - mark
        result = {
            "schema_version": "local-durable-rc-evaluation.v1",
            "physics_key": key,
            "model_checksum": model.canonical_model_checksum,
            "request": request.to_dict(),
            "mode": "verified_durable_original_reused"
            if reused
            else "durable_execution",
            "source_revision": self.source_revision,
            "source_revision_is_attestation": False,
            "job": job.to_dict(),
            "row": row,
            "integrity": integrity,
            "new_model_evaluation": completed_chunks > 0,
            "completed_chunks_this_call": completed_chunks,
            "fresh_reference_verification_this_call": bool(new_rows)
            and row["full_reference_verification_pass"],
            "new_work": new_work,
            "original_work_not_recharged": _work(
                {"rows": [{"invocations": prior_rows}]}
            ),
            "historical_unknown_work": unknown_origin,
            "timings_ns": phase_times,
            "total_wall_ns": perf_counter_ns() - started,
            "total_process_cpu_ns": process_time_ns() - started_cpu,
            "timing_scope": "current_call_including_validation_and_original_export_excluding_final_report_write",
            "prices": None if prices is None else asdict(prices),
            "claims": {
                "persistent_local_storage": True,
                "independent_physical_validation": False,
                "design_authority": False,
                "performance_improvement": False,
                "gpu_execution": False,
                "cross_host_storage": False,
                "automatic_failed_retry": False,
            },
        }
        result["report_hash"] = study._sha(study._bytes(result))
        study._save(output, "evaluation.json", study._bytes(result))
        return result
