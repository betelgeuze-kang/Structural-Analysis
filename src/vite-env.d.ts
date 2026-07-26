/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_JOB_STATUS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
