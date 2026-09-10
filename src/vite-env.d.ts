/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DESIGN_COMPARISON_URL?: string
  readonly VITE_CANDIDATE_SEARCH_PROCESS_URL?: string
  readonly VITE_JOB_STATUS_URL?: string
  readonly VITE_NATIVE_FRAME_RESULT_URL?: string
  readonly VITE_NATIVE_FRAME_REPORT_URL?: string
  readonly VITE_NATIVE_FRAME_BUNDLE_URL?: string
  readonly VITE_NATIVE_FRAME_JOB_URL?: string
  readonly VITE_NATIVE_FRAME_SUBMISSION_URL?: string
  readonly VITE_NATIVE_FRAME_REFERENCE_URL?: string
  readonly VITE_NATIVE_FRAME_COMPARISON_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface StructuralWorkbenchRuntimeConfig {
  readonly designComparisonUrl?: string
  readonly rcControlSearchUrl?: string
  readonly rcControlDesignUrl?: string
  readonly candidateSearchProcessUrl?: string
  readonly jobStatusUrl?: string
  /** Host-provided credentials for one same-origin job load; not a build-time setting. */
  readonly jobAuthorization?: import('./workbench-v2/model/jobTransport').JobAuthorizationProvider
  readonly nativeFrameResultUrl?: string
  readonly nativeFrameReportUrl?: string
  readonly nativeFrameBundleUrl?: string
  readonly nativeFrameJobUrl?: string
  readonly nativeFrameSubmissionUrl?: string
  readonly nativeFrameReferenceUrl?: string
  readonly nativeFrameComparisonUrl?: string
}

interface Window {
  readonly __STRUCTURAL_WORKBENCH_CONFIG__?: StructuralWorkbenchRuntimeConfig
}
