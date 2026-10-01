/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `1` in a build for the static showcase: data comes from exported JSON, not the API */
  readonly VITE_SSEBENCH_STATIC?: string
}
