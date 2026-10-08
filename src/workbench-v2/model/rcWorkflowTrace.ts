/** Opt-in bounded metadata; no context exists without the explicit diagnostic hook. */
const PHASES = [
  'effect.setup', 'effect.cleanup', 'transport.ready', 'poll.begin', 'poll.error',
  'poll.job.begin', 'poll.job.end', 'poll.failed-load.begin', 'poll.failed-load.end',
  'auth.begin', 'auth.end', 'auth.error', 'scope.begin', 'scope.end', 'scope.changed',
  'http.fetch.begin', 'http.fetch.end', 'http.fetch.error', 'http.cancel.begin', 'http.cancel.settled',
  'body.read.begin', 'body.read.end', 'body.read.error',
  'request.hash.begin', 'request.hash.end', 'request.parse.begin', 'request.parse.end',
  'job.load.begin', 'job.parse.begin', 'job.parse.end', 'job.load.error',
  'diagnostic.begin', 'diagnostic.absent', 'ui.ready.queue', 'ui.other.queue', 'ui.ready.commit', 'trace.cap',
] as const
export type RcPhaseName = typeof PHASES[number]
export interface RcPhaseMarker {
  readonly schema: 1
  readonly session: number
  readonly generation: number
  readonly sequence: number
  readonly phase: RcPhaseName
  readonly monotonic_ms: number
}
type Hook = (this: void, marker: Readonly<RcPhaseMarker>) => void
interface Context { session: number; generation: number; sequence: number; stopped: boolean; hook: Hook }
const contexts = new WeakMap<object, Context>()
const allowed = new Set<string>(PHASES)
const SESSION_MAX_MARKERS = 256
let sessions = 0
let delivering = false

export function beginRcPhaseSession(signal: AbortSignal, generation: number): void {
  try {
    const hook = (globalThis as { __RC_INITIAL_READY_MARKER_HOOK__?: unknown }).__RC_INITIAL_READY_MARKER_HOOK__
    if (typeof hook !== 'function' || !Number.isSafeInteger(generation) || generation < 0
      || !Number.isSafeInteger(sessions + 1)) { contexts.delete(signal); return }
    contexts.set(signal, { session: ++sessions, generation, sequence: 0, stopped: false, hook: hook as Hook })
  } catch { contexts.delete(signal) /* Diagnostics never replace the operation outcome. */ }
}

/** Preserve the existing object identity, keeping attribution private. */
export function bindRcPhase<T extends object>(target: T, source?: object, fallback?: object): T {
  const context = source && contexts.get(source) || fallback && contexts.get(fallback)
  if (context) contexts.set(target, context)
  else contexts.delete(target)
  return target
}

/** Finite monotonic metadata and fixed phases only; no URL, credential or payload fields. */
export function traceRcPhase(source: object | undefined, phase: RcPhaseName): void {
  if (delivering) return
  const context = source && contexts.get(source)
  if (!context || context.stopped || !allowed.has(phase) || phase === 'trace.cap') return
  try {
    delivering = true
    const stamp = globalThis.performance?.now()
    if (!Number.isFinite(stamp) || stamp < 0) { context.stopped = true; return }
    if (context.sequence === SESSION_MAX_MARKERS - 1) { phase = 'trace.cap'; context.stopped = true }
    const hook = context.hook
    hook(Object.freeze({ schema: 1, session: context.session, generation: context.generation,
      sequence: ++context.sequence, phase, monotonic_ms: stamp }))
  } catch { context.stopped = true }
  finally { delivering = false }
}
