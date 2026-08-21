/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_JOB_STATUS_URL?: string
  readonly VITE_NATIVE_FRAME_RESULT_URL?: string
  readonly VITE_NATIVE_FRAME_REPORT_URL?: string
  readonly VITE_NATIVE_FRAME_BUNDLE_URL?: string
  readonly VITE_NATIVE_FRAME_JOB_URL?: string
  readonly VITE_NATIVE_FRAME_REFERENCE_URL?: string
  readonly VITE_NATIVE_FRAME_COMPARISON_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface StructuralWorkbenchRuntimeConfig {
  readonly jobStatusUrl?: string
  readonly nativeFrameResultUrl?: string
  readonly nativeFrameReportUrl?: string
  readonly nativeFrameBundleUrl?: string
  readonly nativeFrameJobUrl?: string
  readonly nativeFrameReferenceUrl?: string
  readonly nativeFrameComparisonUrl?: string
}

interface Window {
  readonly __STRUCTURAL_WORKBENCH_CONFIG__?: StructuralWorkbenchRuntimeConfig
}
