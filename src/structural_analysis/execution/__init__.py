"""Durable execution contracts that never define solver truth."""

from structural_analysis.execution.job_service import (
    JOB_COMPLETION_EVIDENCE_SCHEMA_VERSION,
    JOB_REQUEST_SCHEMA_VERSION,
    JOB_VIEW_SCHEMA_VERSION,
    ArtifactReference,
    DurableJobService,
    JobClaim,
    JobServiceError,
    JobView,
    build_job_completion_evidence,
    validate_job_view,
)
from structural_analysis.execution.job_http_api import (
    JOB_HTTP_API_PROFILE,
    DurableJobHttpAPI,
    DurableJobHttpApi,
    DurableJobWSGIApplication,
    JobHttpResponse,
)
from structural_analysis.execution.nonlinear_frame_worker import (
    NonlinearFrameWorkerError,
    execute_nonlinear_frame_claim,
)
__all__ = [
    "JOB_COMPLETION_EVIDENCE_SCHEMA_VERSION",
    "JOB_REQUEST_SCHEMA_VERSION",
    "JOB_HTTP_API_PROFILE",
    "JOB_VIEW_SCHEMA_VERSION",
    "ArtifactReference",
    "DurableJobService",
    "DurableJobHttpApi",
    "DurableJobHttpAPI",
    "DurableJobWSGIApplication",
    "JobClaim",
    "JobServiceError",
    "JobHttpResponse",
    "JobView",
    "NonlinearFrameWorkerError",
    "build_job_completion_evidence",
    "execute_nonlinear_frame_claim",
    "validate_job_view",
]
