"""Public Developer Preview API for the verified planar-frame alpha profile.

This module deliberately promotes only the existing source-bound nonlinear
load-control path. Experimental displacement-control and arc-length solvers are
not reachable through this profile.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final, Literal

from structural_analysis.adapters.bounded_planar_model_ir import (
    PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE,
)
from structural_analysis.api.nonlinear_frame import (
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_result,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.model_ir.types import ModelIRDocument


PLANAR_FRAME_RESULT_SCHEMA_VERSION: Final = "planar-frame-result.v1"
PLANAR_FRAME_VALIDATION_REPORT_SCHEMA_VERSION: Final = (
    "planar-frame-validation-report.v1"
)
PLANAR_FRAME_UNSUPPORTED_REASON_CODES: Final[tuple[str, ...]] = (
    "planar_frame_arc_length_experimental",
    "planar_frame_direct_displacement_control_experimental",
)
PLANAR_FRAME_CLAIM_BOUNDARY: Final = (
    "Public Developer Preview of the source-bound connected planar ModelIR v2 "
    "nonlinear load-control path. Public does not mean release-eligible. The "
    "profile grants no design-code, final-design, independent external-V&V, "
    "commercial, or release-readiness authority. Direct displacement-control "
    "and arc-length remain separate experimental profiles."
)

PlanarFrameControl = Literal[
    "load_control", "direct_displacement_control", "arc_length"
]
PlanarFrameStatus = Literal["converged", "not_converged", "not_run"]


class PlanarFrameUnsupportedError(ValueError):
    """Fail-closed public routing error with a stable reason code."""

    def __init__(self, reason_code: str, path: str, detail: str) -> None:
        if reason_code not in PLANAR_FRAME_UNSUPPORTED_REASON_CODES:
            raise ValueError("reason_code is not a stable planar-frame reason code")
        self.reason_code = reason_code
        self.path = path
        self.detail = detail
        super().__init__(f"{reason_code}@{path}: {detail}")

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": "unsupported",
            "reason_code": self.reason_code,
            "path": self.path,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PlanarFrameConfig:
    """Configuration for the promoted nonlinear load-control slice."""

    control: PlanarFrameControl = "load_control"
    load_steps: int = 4
    residual_tolerance: float = 1.0e-10
    increment_tolerance_m: float = 1.0e-12
    maximum_iterations: int = 40
    matrix_backend: str = "numpy_linalg_solve_dense"

    def nonlinear_config(self) -> NonlinearFrameConfig:
        if self.control == "direct_displacement_control":
            raise PlanarFrameUnsupportedError(
                "planar_frame_direct_displacement_control_experimental",
                "/config/control",
                "Direct displacement-control is available only through its experimental profile.",
            )
        if self.control == "arc_length":
            raise PlanarFrameUnsupportedError(
                "planar_frame_arc_length_experimental",
                "/config/control",
                "Arc-length is available only through its experimental profile.",
            )
        if self.control != "load_control":
            raise ValueError("control is not a recognized planar-frame control mode")
        return NonlinearFrameConfig(
            profile=COROTATIONAL_GENERAL_PROFILE,
            load_steps=self.load_steps,
            residual_tolerance=self.residual_tolerance,
            increment_tolerance_m=self.increment_tolerance_m,
            maximum_iterations=self.maximum_iterations,
            matrix_backend=self.matrix_backend,
        )


@dataclass(frozen=True)
class PlanarFrameResult:
    status: PlanarFrameStatus
    converged: bool | None
    result_hash: str
    authority: Mapping[str, str]
    result_ir: Mapping[str, Any] | None
    unsupported_features: tuple[Mapping[str, str], ...] = ()
    profile: str = PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE
    public: bool = True
    release_eligible: bool = False
    claim_boundary: str = PLANAR_FRAME_CLAIM_BOUNDARY
    _checkpoint_bytes: bytes | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return _result_payload(self, include_hash=True)

    def checkpoint_artifact(self) -> bytes:
        if self._checkpoint_bytes is None:
            raise ValueError("no checkpoint-chain artifact is available")
        return self._checkpoint_bytes


@dataclass(frozen=True)
class PlanarFrameValidationReport:
    status: PlanarFrameStatus
    converged: bool | None
    contract_pass: bool
    result_hash: str
    unsupported_reason_codes: tuple[str, ...] = ()
    profile: str = PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE
    public: bool = True
    release_eligible: bool = False
    claim_boundary: str = PLANAR_FRAME_CLAIM_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PLANAR_FRAME_VALIDATION_REPORT_SCHEMA_VERSION,
            "status": self.status,
            "converged": self.converged,
            "contract_pass": self.contract_pass,
            "result_hash": self.result_hash,
            "profile": self.profile,
            "public": self.public,
            "release_eligible": self.release_eligible,
            "unsupported_reason_codes": list(self.unsupported_reason_codes),
            "claim_boundary": self.claim_boundary,
        }


def analyze_planar_frame(
    document: ModelIRDocument,
    config: PlanarFrameConfig | None = None,
    *,
    restart_checkpoint_chain: bytes | bytearray | memoryview | None = None,
) -> PlanarFrameResult:
    """Analyze a verified-alpha ModelIR document using nonlinear load control."""

    if type(document) is not ModelIRDocument:
        raise ValueError("document must be a ModelIRDocument")
    if document.capability_profile != PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE:
        raise ValueError(
            "document capability_profile must be planar_frame_verified_alpha.v1"
        )
    cfg = PlanarFrameConfig() if config is None else config
    if type(cfg) is not PlanarFrameConfig:
        raise ValueError("config must be a PlanarFrameConfig")
    try:
        nonlinear_config = cfg.nonlinear_config()
    except PlanarFrameUnsupportedError as error:
        return _not_run_result(error)
    source = analyze_nonlinear_frame_model_ir(
        document,
        nonlinear_config,
        restart_checkpoint_chain=restart_checkpoint_chain,
    )
    source_report = validate_nonlinear_frame_result(source)
    converged = bool(source_report.contract_pass and source.status == "ready")
    authority = MappingProxyType(
        {
            "profile": "public_developer_preview",
            "numerical_result": (
                "exact_bounded_candidate" if converged else "not_authoritative"
            ),
            "engineering_result": (
                "exact_bounded_candidate" if converged else "not_authoritative"
            ),
            "external_vv": "not_attached",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        }
    )
    provisional = PlanarFrameResult(
        status="converged" if converged else "not_converged",
        converged=converged,
        result_hash="sha256:" + "0" * 64,
        authority=authority,
        result_ir=MappingProxyType(source.to_dict()),
        _checkpoint_bytes=(
            source.checkpoint_artifact()
            if source.checkpoint.get("available") is True
            else None
        ),
    )
    result = PlanarFrameResult(
        **{
            **provisional.__dict__,
            "result_hash": canonical_hash(
                _result_payload(provisional, include_hash=False)
            ),
        }
    )
    validate_planar_frame_result(result)
    return result


def validate_planar_frame_result(
    result: PlanarFrameResult,
) -> PlanarFrameValidationReport:
    if type(result) is not PlanarFrameResult:
        raise ValueError("result must be a PlanarFrameResult")
    if result.profile != PLANAR_FRAME_VERIFIED_ALPHA_V1_PROFILE:
        raise ValueError("result profile is not planar_frame_verified_alpha.v1")
    if result.public is not True or result.release_eligible is not False:
        raise ValueError("public/release eligibility differs from profile contract")
    expected_converged = (
        None if result.status == "not_run" else result.status == "converged"
    )
    if result.converged is not expected_converged:
        raise ValueError("status and converged are inconsistent")
    if result.result_hash != canonical_hash(
        _result_payload(result, include_hash=False)
    ):
        raise ValueError("result_hash does not match the planar-frame result payload")
    if result.status == "not_run":
        if result.result_ir is not None:
            raise ValueError("not_run result must not expose a result_ir")
        reason_codes = tuple(
            row.get("reason_code", "") for row in result.unsupported_features
        )
        if not reason_codes or any(
            code not in PLANAR_FRAME_UNSUPPORTED_REASON_CODES for code in reason_codes
        ):
            raise ValueError("not_run result requires stable unsupported reasons")
        if any(
            result.authority.get(axis) != "not_authoritative"
            for axis in ("numerical_result", "engineering_result")
        ):
            raise ValueError("not_run result must not expose result authority")
        return PlanarFrameValidationReport(
            status=result.status,
            converged=None,
            contract_pass=False,
            result_hash=result.result_hash,
            unsupported_reason_codes=reason_codes,
        )
    if result.result_ir is None:
        raise ValueError("executed result requires a result_ir")
    if result.unsupported_features:
        raise ValueError("executed result must not retain unsupported routing")
    source = dict(result.result_ir)
    if source.get("profile") != COROTATIONAL_GENERAL_PROFILE:
        raise ValueError("result_ir is not the connected planar nonlinear result")
    if bool(source.get("contract_pass")) != result.converged:
        raise ValueError("result_ir contract_pass differs from converged")
    expected_authority = (
        "exact_bounded_candidate" if result.converged else "not_authoritative"
    )
    if (
        result.authority.get("profile") != "public_developer_preview"
        or result.authority.get("numerical_result") != expected_authority
        or result.authority.get("engineering_result") != expected_authority
        or result.authority.get("release_readiness") != "not_authoritative"
    ):
        raise ValueError("result authority differs from profile contract")
    return PlanarFrameValidationReport(
        status=result.status,
        converged=result.converged,
        contract_pass=result.converged,
        result_hash=result.result_hash,
    )


def _not_run_result(error: PlanarFrameUnsupportedError) -> PlanarFrameResult:
    provisional = PlanarFrameResult(
        status="not_run",
        converged=None,
        result_hash="sha256:" + "0" * 64,
        authority=MappingProxyType(
            {
                "profile": "public_developer_preview",
                "numerical_result": "not_authoritative",
                "engineering_result": "not_authoritative",
                "external_vv": "not_attached",
                "engineering_design": "not_authoritative",
                "release_readiness": "not_authoritative",
            }
        ),
        result_ir=None,
        unsupported_features=(MappingProxyType(error.to_dict()),),
    )
    result = PlanarFrameResult(
        **{
            **provisional.__dict__,
            "result_hash": canonical_hash(
                _result_payload(provisional, include_hash=False)
            ),
        }
    )
    validate_planar_frame_result(result)
    return result


def _result_payload(result: PlanarFrameResult, *, include_hash: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": PLANAR_FRAME_RESULT_SCHEMA_VERSION,
        "status": result.status,
        "converged": result.converged,
        "profile": result.profile,
        "public": result.public,
        "release_eligible": result.release_eligible,
        "authority": dict(result.authority),
        "result_ir": dict(result.result_ir) if result.result_ir is not None else None,
        "unsupported_features": [dict(row) for row in result.unsupported_features],
        "claim_boundary": result.claim_boundary,
    }
    if include_hash:
        payload["result_hash"] = result.result_hash
    return payload
