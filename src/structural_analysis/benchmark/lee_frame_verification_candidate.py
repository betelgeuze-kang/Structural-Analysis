"""Generate a non-promoting formal V&V candidate for the published Lee frame.

The generator executes the bounded Lee-frame benchmark, writes exact generated
source, execution, and scientific-decision receipts, and creates an operator
manifest compatible with the existing verification hierarchy.

The evidence row identifies the locally generated source receipt with a
``generated://`` URI. The published DOI remains benchmark metadata only until
permitted publisher/table bytes are attached and hashed. Source-use/license,
independent clean-runner, and operator-approval blockers remain explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from structural_analysis.benchmark.acceptance import (
    BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
    decide_benchmark,
)
from structural_analysis.benchmark.lee_frame import (
    LEE_FRAME_PUBLISHED_PATH,
    LEE_FRAME_REFERENCE_DOI,
    LEE_FRAME_REFERENCE_TABLE,
    LEE_FRAME_SCHEMA_VERSION,
    run_lee_frame_snapthrough_benchmark,
)
from structural_analysis.benchmark.verification_hierarchy import (
    EvidenceArtifactReceipt,
    ReferenceSolverReceipt,
    SourceLicenseReceipt,
    VerificationEvidence,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


LEE_FRAME_VERIFICATION_CANDIDATE_SCHEMA_VERSION = (
    "lee-frame-verification-candidate-bundle.v1"
)
LEE_FRAME_SOURCE_RECEIPT_SCHEMA_VERSION = (
    "lee-frame-published-source-receipt.v1"
)
LEE_FRAME_EXECUTION_RECEIPT_SCHEMA_VERSION = (
    "lee-frame-published-execution-receipt.v1"
)
LEE_FRAME_EVIDENCE_ID = "published-lee-frame-snap-through-candidate"
LEE_FRAME_TRUTH_BASIS = "published_benchmark"
LEE_FRAME_CATEGORY = "nonlinear_snap_through"
LEE_FRAME_DECISION_EVALUATED_AT = "1970-01-01T00:00:00+00:00"
LEE_FRAME_GENERATED_SOURCE_URI = (
    "generated://structural_analysis/verification/lee-frame/source-receipt.v1"
)
LEE_FRAME_PUBLISHER_SOURCE_URI = f"https://doi.org/{LEE_FRAME_REFERENCE_DOI}"
LEE_FRAME_CLAIM_BOUNDARY = (
    "This candidate binds a locally generated source-identity receipt, the "
    "bounded Lee-frame execution, and a scientific PASS decision. The generated "
    "receipt hash is not represented as publisher-source bytes. The row is not "
    "hierarchy credit until permitted publisher/table source bytes, source-use/"
    "license approval, independent clean-runner reproduction, and formal operator "
    "approval are attached. It cannot bypass incomplete Level 2 code-to-code "
    "slots or promote general frame/shell, production, release, or commercial claims."
)
LEE_FRAME_DECLARED_BLOCKERS = (
    "publisher_source_bytes_not_attached",
    "source_use_license_approval_missing",
    "independent_clean_runner_receipt_missing",
    "formal_operator_approval_missing",
)


@dataclass(frozen=True)
class LeeFrameVerificationCandidateBundle:
    root: Path
    manifest_path: Path
    source_receipt_path: Path
    execution_receipt_path: Path
    decision_path: Path
    evidence: VerificationEvidence
    source_receipt: dict[str, Any]
    execution_receipt: dict[str, Any]
    decision: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LEE_FRAME_VERIFICATION_CANDIDATE_SCHEMA_VERSION,
            "manifest_path": _relative(self.root, self.manifest_path),
            "source_receipt_path": _relative(
                self.root,
                self.source_receipt_path,
            ),
            "execution_receipt_path": _relative(
                self.root,
                self.execution_receipt_path,
            ),
            "decision_path": _relative(self.root, self.decision_path),
            "evidence": self.evidence.to_dict(),
            "claim_boundary": LEE_FRAME_CLAIM_BOUNDARY,
        }


def _scalar_metric_result(
    *,
    name: str,
    actual: float,
    reference: float,
    absolute_tolerance: float,
    relative_tolerance: float = 0.0,
) -> dict[str, Any]:
    """Build one deterministic scalar metric-family result for acceptance."""

    absolute_error = abs(float(actual) - float(reference))
    relative_error = (
        absolute_error / abs(float(reference)) if float(reference) != 0.0 else None
    )
    allowed_error = max(
        float(absolute_tolerance),
        float(relative_tolerance) * abs(float(reference)),
    )
    return {
        "schema_version": BENCHMARK_ACCEPTANCE_SCHEMA_VERSION,
        "metric_family": name,
        "reference": float(reference),
        "actual": float(actual),
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "absolute_tolerance": float(absolute_tolerance),
        "relative_tolerance": float(relative_tolerance),
        "allowed_error": allowed_error,
        "contract_pass": absolute_error <= allowed_error,
    }


def build_lee_frame_verification_candidate_payloads() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """Execute the benchmark and return strict generated receipt payloads."""

    result = run_lee_frame_snapthrough_benchmark()
    if not result.contract_pass:
        raise ValueError("Lee-frame source benchmark did not pass its bounded contract")

    published_path_payload = [list(row) for row in LEE_FRAME_PUBLISHED_PATH]
    source_receipt = {
        "schema_version": LEE_FRAME_SOURCE_RECEIPT_SCHEMA_VERSION,
        "contract_pass": True,
        "generated_source_receipt_uri": LEE_FRAME_GENERATED_SOURCE_URI,
        "publisher_source_uri": LEE_FRAME_PUBLISHER_SOURCE_URI,
        "publisher_source_bytes_attached": False,
        "publisher_source_sha256": None,
        "doi": LEE_FRAME_REFERENCE_DOI,
        "reference_table": LEE_FRAME_REFERENCE_TABLE,
        "publisher": "Structural Engineering and Mechanics / NAFEMS catalogue",
        "published_path_point_count": len(LEE_FRAME_PUBLISHED_PATH),
        "published_path_content_hash": canonical_hash(published_path_payload),
        "published_path_provenance_status": (
            "transcribed_reference_values_pending_publisher_source_attachment"
        ),
        "source_use_status": "pending_formal_product_use_approval",
        "local_execution_approved": False,
        "commercial_use_approved": False,
        "redistribution_approved": False,
        "claim_boundary": (
            "This generated receipt binds declared publisher identity and the "
            "locally retained path values. Its own SHA-256 is not the SHA-256 of "
            "publisher/table source bytes. It grants no source-use, commercial-use, "
            "or redistribution approval."
        ),
    }

    execution_receipt = {
        "schema_version": LEE_FRAME_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "contract_pass": True,
        "source_schema_version": LEE_FRAME_SCHEMA_VERSION,
        "source_builder": (
            "structural_analysis.benchmark.lee_frame."
            "run_lee_frame_snapthrough_benchmark"
        ),
        "generated_source_receipt_uri": LEE_FRAME_GENERATED_SOURCE_URI,
        "source_receipt_content_hash": canonical_hash(source_receipt),
        "publisher_source_bytes_attached": False,
        "model": {
            "element_count": result.element_count,
            "free_dof_count": result.free_dof_count,
            "published_path_point_count": result.published_path_point_count,
        },
        "path": {
            "accepted_step_count": result.accepted_step_count,
            "rejected_step_count": result.rejected_step_count,
            "restart_exact": result.restart_exact,
            "descending_branch_observed": result.descending_branch_observed,
            "negative_load_observed": result.negative_load_observed,
            "snapback_observed": result.snapback_observed,
            "rehardening_observed": result.rehardening_observed,
        },
        "metrics": {
            "first_limit_load_factor": result.first_limit_load_factor,
            "first_limit_reference_factor": result.first_limit_reference_factor,
            "first_limit_absolute_error": result.first_limit_absolute_error,
            "maximum_path_distance_m": result.maximum_path_distance_m,
            "maximum_load_factor_error": result.maximum_load_factor_error,
            "rms_load_factor_error": result.rms_load_factor_error,
            "maximum_residual_inf_kn": result.maximum_residual_inf_kn,
            "maximum_constraint_residual_m2": (
                result.maximum_constraint_residual_m2
            ),
            "energy_gradient_relative_error": (
                result.energy_gradient_relative_error
            ),
            "tangent_hessian_relative_error": (
                result.tangent_hessian_relative_error
            ),
            "tangent_symmetry_relative_error": (
                result.tangent_symmetry_relative_error
            ),
            "regularization_count": result.regularization_count,
            "fallback_count": result.fallback_count,
        },
        "source_result_hash": canonical_hash(result.to_dict()),
        "claim_boundary": result.claim_boundary,
    }

    metric_results = [
        _scalar_metric_result(
            name="first_limit_load_factor",
            actual=result.first_limit_load_factor,
            reference=result.first_limit_reference_factor,
            absolute_tolerance=0.25,
        ),
        _scalar_metric_result(
            name="maximum_path_distance_m",
            actual=result.maximum_path_distance_m,
            reference=0.0,
            absolute_tolerance=0.004,
        ),
        _scalar_metric_result(
            name="maximum_load_factor_error",
            actual=result.maximum_load_factor_error,
            reference=0.0,
            absolute_tolerance=0.35,
        ),
        _scalar_metric_result(
            name="rms_load_factor_error",
            actual=result.rms_load_factor_error,
            reference=0.0,
            absolute_tolerance=0.20,
        ),
        _scalar_metric_result(
            name="maximum_residual_inf_kn",
            actual=result.maximum_residual_inf_kn,
            reference=0.0,
            absolute_tolerance=1.0e-7,
        ),
        _scalar_metric_result(
            name="maximum_constraint_residual_m2",
            actual=result.maximum_constraint_residual_m2,
            reference=0.0,
            absolute_tolerance=1.0e-10,
        ),
        _scalar_metric_result(
            name="energy_gradient_relative_error",
            actual=result.energy_gradient_relative_error,
            reference=0.0,
            absolute_tolerance=1.0e-7,
        ),
        _scalar_metric_result(
            name="tangent_hessian_relative_error",
            actual=result.tangent_hessian_relative_error,
            reference=0.0,
            absolute_tolerance=2.0e-7,
        ),
        _scalar_metric_result(
            name="tangent_symmetry_relative_error",
            actual=result.tangent_symmetry_relative_error,
            reference=0.0,
            absolute_tolerance=1.0e-12,
        ),
    ]
    decision = decide_benchmark(
        metric_results,
        decision="PASS",
        evaluated_at=LEE_FRAME_DECISION_EVALUATED_AT,
    )
    if not decision["decision_contract_pass"] or decision["decision"] != "PASS":
        raise ValueError("Lee-frame scientific decision did not pass")
    return source_receipt, execution_receipt, decision


def write_lee_frame_verification_candidate_bundle(
    root: Path,
    *,
    candidate_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> LeeFrameVerificationCandidateBundle:
    """Write exact artifacts and one non-promoting operator manifest."""

    repository_root = root.resolve()
    candidate_directory = (
        candidate_dir
        or repository_root
        / "implementation/phase1/release_evidence/productization/"
        "verification_candidates/lee_frame"
    ).resolve()
    operator_manifest = (
        manifest_path
        or repository_root
        / "implementation/phase1/release_evidence/productization/"
        "verification_hierarchy_evidence.candidate.json"
    ).resolve()
    _inside(repository_root, candidate_directory)
    _inside(repository_root, operator_manifest)

    source_receipt, execution_receipt, decision = (
        build_lee_frame_verification_candidate_payloads()
    )
    source_path = candidate_directory / "source_receipt.json"
    execution_path = candidate_directory / "execution_receipt.json"
    decision_path = candidate_directory / "scientific_decision.json"
    source_bytes = _write_json(source_path, source_receipt)
    execution_bytes = _write_json(execution_path, execution_receipt)
    decision_bytes = _write_json(decision_path, decision)

    evidence = VerificationEvidence(
        schema_version="structural-verification-evidence.v1",
        evidence_id=LEE_FRAME_EVIDENCE_ID,
        level=3,
        category=LEE_FRAME_CATEGORY,
        truth_basis=LEE_FRAME_TRUTH_BASIS,
        source_url_or_doi=LEE_FRAME_GENERATED_SOURCE_URI,
        source_sha256=_sha256(source_bytes),
        license=SourceLicenseReceipt(
            approval_status="pending",
            local_execution_approved=False,
            commercial_use_approved=False,
            redistribution_approved=False,
            approved_by="",
            evidence_ref=_relative(repository_root, source_path),
        ),
        reference_solver=ReferenceSolverReceipt(
            name="Structural-Analysis bounded Lee-frame kernel",
            verified_version=LEE_FRAME_SCHEMA_VERSION,
            solver_class="product_bounded_reference_kernel",
            independent_from_product=False,
        ),
        benchmark_name=(
            "Lee frame snap-through and snap-back / NAFEMS NLGB8 / "
            f"DOI {LEE_FRAME_REFERENCE_DOI}"
        ),
        publisher="Structural Engineering and Mechanics / NAFEMS",
        dataset_id=LEE_FRAME_REFERENCE_TABLE,
        measurement_types=(
            "load_displacement_path",
            "limit_load",
            "equilibrium_residual",
            "tangent_consistency",
        ),
        artifacts=(
            EvidenceArtifactReceipt(
                path=_relative(repository_root, source_path),
                sha256=_sha256(source_bytes),
                contract_pass=True,
            ),
            EvidenceArtifactReceipt(
                path=_relative(repository_root, execution_path),
                sha256=_sha256(execution_bytes),
                contract_pass=True,
            ),
            EvidenceArtifactReceipt(
                path=_relative(repository_root, decision_path),
                sha256=_sha256(decision_bytes),
                contract_pass=True,
            ),
        ),
        decision=decision,
        declared_blockers=LEE_FRAME_DECLARED_BLOCKERS,
        claim_boundary=LEE_FRAME_CLAIM_BOUNDARY,
    )
    manifest = {
        "schema_version": "structural-verification-evidence-manifest.v1",
        "evidence": [evidence.to_dict()],
        "claim_boundary": (
            "This candidate manifest exposes one published nonlinear snap-through "
            "row without granting hierarchy credit. The evidence source URI and "
            "hash identify the generated source receipt, not publisher bytes. "
            "Existing analytic evidence is still composed by the hierarchy builder, "
            "and contiguous promotion remains blocked by incomplete Level 2 and the "
            "declared candidate blockers."
        ),
    }
    _write_json(operator_manifest, manifest)
    return LeeFrameVerificationCandidateBundle(
        root=repository_root,
        manifest_path=operator_manifest,
        source_receipt_path=source_path,
        execution_receipt_path=execution_path,
        decision_path=decision_path,
        evidence=evidence,
        source_receipt=source_receipt,
        execution_receipt=execution_receipt,
        decision=decision,
    )


def _write_json(path: Path, payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return encoded


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _inside(root: Path, path: Path) -> None:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"candidate path escapes repository root: {path}") from exc


__all__ = [
    "LEE_FRAME_CATEGORY",
    "LEE_FRAME_CLAIM_BOUNDARY",
    "LEE_FRAME_DECISION_EVALUATED_AT",
    "LEE_FRAME_DECLARED_BLOCKERS",
    "LEE_FRAME_EVIDENCE_ID",
    "LEE_FRAME_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "LEE_FRAME_GENERATED_SOURCE_URI",
    "LEE_FRAME_PUBLISHER_SOURCE_URI",
    "LEE_FRAME_SOURCE_RECEIPT_SCHEMA_VERSION",
    "LEE_FRAME_TRUTH_BASIS",
    "LEE_FRAME_VERIFICATION_CANDIDATE_SCHEMA_VERSION",
    "LeeFrameVerificationCandidateBundle",
    "build_lee_frame_verification_candidate_payloads",
    "write_lee_frame_verification_candidate_bundle",
]
