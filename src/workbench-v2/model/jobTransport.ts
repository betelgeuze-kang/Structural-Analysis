import { parseRcDeclaredPrices, type RcDeclaredPrices } from './rcQuantityReportSchema'
import { bindRcPhase, traceRcPhase } from './rcWorkflowTrace'

/** Credentials remain private to one explicit host-authorized load/session. */
export interface JobAuthorization {
  tenantId: string
  bearerToken: string
}

export type JobAuthorizationProvider = (context: {
  statusUrl: string
  signal?: AbortSignal
}) => JobAuthorization | Promise<JobAuthorization>

export class JobArtifactError extends Error {}

export interface JobReadTransport {
  readonly tenantId?: string
  get(role?: string, accept?: string): Promise<Response>
  withSignal?(signal: AbortSignal): JobReadTransport
}

const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)\b/i

export const SUBMIT_MAX_BYTES = 16 * 1024 * 1024
export const REPORT_POST_MAX_BYTES = 16 * 1024
const JOB_ID = /^job_[0-9a-f]{32}$/
const REPORT_ID = /^rcq_[0-9a-f]{64}$/
const HASH = /^sha256:[0-9a-f]{64}$/
const ROLE = /^(request|checkpoint|result|evidence|rc-invocations(?:\/[1-9][0-9]{0,3})?|failure-diagnostics\/[1-9][0-9]{0,3})$/

export interface RcReportCreateBody {
  expected_request_hash: string
  expected_result_artifact_hash: string
  declared_prices: RcDeclaredPrices | null
}

export interface RcReportPage { afterRevision?: number; limit?: number }

export interface RcJobTransport {
  readonly tenantId?: string
  readonly collectionUrl: string
  verifyAuthorizationScope(): Promise<void>
  readTransport(jobId: string, signal?: AbortSignal): JobReadTransport
  getJob(jobId: string): Promise<Response>
  getRequest(jobId: string): Promise<Response>
  submit(requestBytes: Uint8Array, idempotencyKey: string): Promise<Response>
  resume(jobId: string, expectedRequestHash: string, expectedCheckpointHash: string | null): Promise<Response>
  createQuantityReport(jobId: string, body: RcReportCreateBody): Promise<Response>
  listQuantityReports(jobId: string, page?: RcReportPage): Promise<Response>
  getQuantityReport(jobId: string, reportId: string): Promise<Response>
}

function endpoint(value: string, authorize?: JobAuthorizationProvider): URL {
  const origin = typeof location === 'undefined' ? undefined : location.origin
  let url: URL
  try { url = new URL(value, origin) } catch { throw new JobArtifactError('job_endpoint_invalid') }
  if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.search || url.hash
    || (origin !== undefined && url.origin !== origin) || (authorize && origin === undefined)) {
    throw new JobArtifactError('job_endpoint_invalid')
  }
  url.pathname = url.pathname.replace(/\/+$/, '')
  return url
}

async function authorization(url: URL, signal?: AbortSignal, authorize?: JobAuthorizationProvider): Promise<JobAuthorization | undefined> {
  signal?.throwIfAborted()
  if (!authorize) return undefined
  traceRcPhase(signal, 'auth.begin')
  let value: JobAuthorization
  try { value = await authorize({ statusUrl: url.href, signal }) } catch {
    traceRcPhase(signal, 'auth.error')
    signal?.throwIfAborted()
    throw new JobArtifactError('job_authorization_unavailable')
  }
  signal?.throwIfAborted()
  // Snapshot values: the host may later mutate the returned object in place.
  let tenantId: string, bearerToken: string
  try { tenantId = value?.tenantId; bearerToken = value?.bearerToken } catch { throw new JobArtifactError('job_authorization_invalid') }
  if (typeof tenantId !== 'string' || typeof bearerToken !== 'string'
    || !/^[\x21-\x7e]{1,256}$/.test(tenantId) || !/^[\x21-\x7e]{1,4096}$/.test(bearerToken)) {
    throw new JobArtifactError('job_authorization_invalid')
  }
  traceRcPhase(signal, 'auth.end')
  return { tenantId, bearerToken }
}

function authHeaders(value?: JobAuthorization): Headers {
  const headers = new Headers()
  if (value) {
    headers.set('X-Structural-Tenant', value.tenantId)
    headers.set('Authorization', `Bearer ${value.bearerToken}`)
  }
  return headers
}

function linkedSignal(first?: AbortSignal, second?: AbortSignal): AbortSignal | undefined {
  if (!first) return second
  if (!second || first === second) return first
  if (first.aborted) return first
  if (second.aborted) return second
  const controller = new AbortController()
  const cleanup = () => {
    first.removeEventListener('abort', abortFirst)
    second.removeEventListener('abort', abortSecond)
  }
  const abortFirst = () => { cleanup(); controller.abort(first.reason) }
  const abortSecond = () => { cleanup(); controller.abort(second.reason) }
  first.addEventListener('abort', abortFirst, { once: true })
  second.addEventListener('abort', abortSecond, { once: true })
  return bindRcPhase(controller.signal, first, second)
}

async function request(url: string, headers: Headers, signal?: AbortSignal, body?: ArrayBuffer | string): Promise<Response> {
  signal?.throwIfAborted()
  let response: Response
  traceRcPhase(signal, 'http.fetch.begin')
  try {
    response = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'include', cache: 'no-store',
      redirect: 'error', headers, signal, ...(body === undefined ? {} : { body }),
    })
  } catch {
    traceRcPhase(signal, 'http.fetch.error')
    signal?.throwIfAborted()
    throw new Error('job_api_request_failed')
  }
  bindRcPhase(response, signal)
  traceRcPhase(signal, 'http.fetch.end')
  if (!response.ok) {
    traceRcPhase(response, 'http.cancel.begin')
    try { await response.body?.cancel() } catch { /* Never expose an error body. */ }
    traceRcPhase(response, 'http.cancel.settled')
  }
  return response
}

/** Resolve the destination before asking the host for credentials; never follow redirects. */
export async function createJobReadTransport(
  statusUrl: string,
  signal?: AbortSignal,
  authorize?: JobAuthorizationProvider,
): Promise<JobReadTransport> {
  const url = endpoint(statusUrl, authorize)
  const credentials = await authorization(url, signal, authorize)
  const headers = authHeaders(credentials)
  signal?.throwIfAborted()
  const read = (readSignal?: AbortSignal): JobReadTransport => ({
    tenantId: credentials?.tenantId,
    withSignal: (next) => read(linkedSignal(readSignal, next)),
    async get(role, accept = 'application/json') {
      if (role !== undefined && !ROLE.test(role)) {
        throw new JobArtifactError('job_artifact_role_invalid')
      }
      const requestHeaders = new Headers(headers)
      requestHeaders.set('Accept', accept)
      return request(`${url.href}${role === undefined ? '' : `/${role}`}`, requestHeaders, readSignal)
    },
  })
  return read(signal)
}

/** One explicit workflow session, with host scope checked before and after network operations. */
export async function createJobWorkflowTransport(
  collectionUrl: string, signal?: AbortSignal, authorize?: JobAuthorizationProvider,
): Promise<RcJobTransport> {
  const url = endpoint(collectionUrl, authorize)
  if (!/^\/(?:[A-Za-z0-9_-]+\/)*v1\/jobs$/.test(url.pathname)) throw new JobArtifactError('job_collection_endpoint_invalid')
  const initial = await authorization(url, signal, authorize)
  let headers = authHeaders(initial)
  let scopeChanged = false
  async function verify(readSignal = signal): Promise<void> {
    traceRcPhase(readSignal, 'scope.begin')
    readSignal?.throwIfAborted()
    if (scopeChanged) throw new JobArtifactError('job_authorization_scope_changed')
    const current = await authorization(url, readSignal, authorize)
    if (current?.tenantId !== initial?.tenantId) { scopeChanged = true; traceRcPhase(readSignal, 'scope.changed') }
    if (scopeChanged) throw new JobArtifactError('job_authorization_scope_changed')
    // Token rotation within the same tenant is private to this session.
    headers = authHeaders(current)
    traceRcPhase(readSignal, 'scope.end')
  }
  function jobPath(jobId: string): string {
    if (!JOB_ID.test(jobId)) throw new JobArtifactError('job_id_invalid')
    return `${url.href}/${jobId}`
  }
  async function send(path: string, body?: ArrayBuffer | string, extra?: Record<string, string>, readSignal = signal, accept = 'application/json'): Promise<Response> {
    await verify(readSignal)
    if (scopeChanged) throw new JobArtifactError('job_authorization_scope_changed')
    const outgoing = new Headers(headers)
    outgoing.set('Accept', accept)
    if (body !== undefined) outgoing.set('Content-Type', 'application/json')
    Object.entries(extra ?? {}).forEach(([name, value]) => outgoing.set(name, value))
    const response = await request(path, outgoing, readSignal, body)
    try { await verify(readSignal) } catch (error) {
      try { await response.body?.cancel() } catch { /* Do not expose stale-scope bytes. */ }
      throw error
    }
    return response
  }
  function readTransport(jobId: string, extraSignal?: AbortSignal): JobReadTransport {
    const path = jobPath(jobId)
    const readSignal = linkedSignal(signal, extraSignal)
    return bindRcPhase<JobReadTransport>({
      tenantId: initial?.tenantId,
      withSignal: (next) => readTransport(jobId, linkedSignal(readSignal, next)),
      get(role, accept = 'application/json') {
        if (role !== undefined && !ROLE.test(role)) throw new JobArtifactError('job_artifact_role_invalid')
        return send(`${path}${role === undefined ? '' : `/${role}`}`, undefined, undefined, readSignal, accept)
      },
    }, readSignal)
  }
  return bindRcPhase<RcJobTransport>({
    tenantId: initial?.tenantId,
    collectionUrl: url.href,
    verifyAuthorizationScope: () => verify(),
    readTransport,
    getJob: (jobId) => send(jobPath(jobId)),
    getRequest: (jobId) => send(`${jobPath(jobId)}/request`),
    submit(bytes, key) {
      if (!(bytes instanceof Uint8Array) || !bytes.byteLength || bytes.byteLength > SUBMIT_MAX_BYTES) throw new JobArtifactError('job_submit_too_large')
      if (typeof key !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(key)) throw new JobArtifactError('job_idempotency_key_invalid')
      // Copy, but never parse/re-serialize, caller-authored numerical tokens.
      return send(url.href, bytes.slice().buffer as ArrayBuffer, { 'Idempotency-Key': key })
    },
    resume(jobId, expectedRequestHash, expectedCheckpointHash) {
      const path = jobPath(jobId)
      if (!HASH.test(expectedRequestHash) || (expectedCheckpointHash !== null && !HASH.test(expectedCheckpointHash))) throw new JobArtifactError('job_resume_binding_invalid')
      return send(`${path}/resume`, JSON.stringify({ expected_request_hash: expectedRequestHash, expected_checkpoint_hash: expectedCheckpointHash }))
    },
    createQuantityReport(jobId, body) {
      const path = jobPath(jobId)
      let raw: string
      try {
        if (!body || Object.keys(body).sort().join(',') !== 'declared_prices,expected_request_hash,expected_result_artifact_hash'
          || !HASH.test(body.expected_request_hash) || !HASH.test(body.expected_result_artifact_hash)
          || body.declared_prices === undefined) throw new Error('invalid')
        const prices = parseRcDeclaredPrices(body.declared_prices)
        raw = JSON.stringify({ expected_request_hash: body.expected_request_hash, expected_result_artifact_hash: body.expected_result_artifact_hash, declared_prices: prices })
      } catch { throw new JobArtifactError('rc_report_declaration_invalid') }
      if (new TextEncoder().encode(raw).byteLength > REPORT_POST_MAX_BYTES) throw new JobArtifactError('rc_report_declaration_too_large')
      return send(`${path}/rc-quantity-reports`, raw)
    },
    listQuantityReports(jobId, page = {}) {
      const path = jobPath(jobId)
      const after = page.afterRevision ?? 0
      const limit = page.limit ?? 20
      if (!Number.isSafeInteger(after) || after < 0 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100) throw new JobArtifactError('rc_report_page_invalid')
      return send(`${path}/rc-quantity-reports`, undefined, { 'X-Structural-Report-After-Revision': String(after), 'X-Structural-Report-Limit': String(limit) })
    },
    getQuantityReport(jobId, reportId) {
      const path = jobPath(jobId)
      if (!REPORT_ID.test(reportId)) throw new JobArtifactError('rc_report_id_invalid')
      return send(`${path}/rc-quantity-reports/${reportId}`)
    },
  }, signal)
}

/** Bound actual streamed bytes, including absent or dishonest Content-Length headers. */
export async function readBoundedJobBytes(
  response: Response,
  maximumBytes: number,
  label: string,
  expectedBytes?: number,
): Promise<Uint8Array> {
  const tooLarge = () => new JobArtifactError(`${label.replace(' ', '_')}_too_large`)
  const lengthMismatch = () => new JobArtifactError(`${label} byte length mismatch`)
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  traceRcPhase(response, 'body.read.begin')
  try {
    if (!Number.isSafeInteger(maximumBytes) || maximumBytes < 0
      || (expectedBytes !== undefined && (!Number.isSafeInteger(expectedBytes) || expectedBytes < 0))) {
      throw new JobArtifactError('job_byte_limit_invalid')
    }
    if (expectedBytes !== undefined && expectedBytes > maximumBytes) throw tooLarge()
    if (!JSON_CONTENT_TYPE.test(response.headers.get('content-type') ?? '')) {
      throw new JobArtifactError(`${label.replace(' ', '_')}_content_type_invalid`)
    }
    const declaredHeader = response.headers.get('content-length')
    const declared = declaredHeader === null ? undefined : Number(declaredHeader)
    if (declared !== undefined && (!/^\d+$/.test(declaredHeader!) || !Number.isSafeInteger(declared))) {
      throw new JobArtifactError(`${label.replace(' ', '_')}_content_length_invalid`)
    }
    if (declared !== undefined && declared > maximumBytes) throw tooLarge()
    // Fetch transparently decompresses bodies. Content-Length can describe the
    // encoded body; the reference always describes the decoded original bytes.
    const encoded = response.headers.get('content-encoding')
    if ((!encoded || encoded === 'identity') && expectedBytes !== undefined
      && declared !== undefined && declared !== expectedBytes) throw lengthMismatch()
    if (!response.body) throw new JobArtifactError(`${label.replace(' ', '_')}_body_unavailable`)
    reader = response.body.getReader()
    // Artifact references give an exact allocation bound. Small views without a
    // reference use chunks; no unbounded Response.arrayBuffer() is used.
    const target = expectedBytes === undefined ? undefined : new Uint8Array(expectedBytes)
    const chunks: Uint8Array[] = []
    let size = 0
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (value.byteLength > maximumBytes - size) throw tooLarge()
      if (target && value.byteLength > target.byteLength - size) throw lengthMismatch()
      if (target) target.set(value, size)
      else chunks.push(value)
      size += value.byteLength
    }
    if (expectedBytes !== undefined && size !== expectedBytes) throw lengthMismatch()
    if (target) { traceRcPhase(response, 'body.read.end'); return target }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) {
      bytes.set(chunk, offset)
      offset += chunk.byteLength
    }
    traceRcPhase(response, 'body.read.end')
    return bytes
  } catch (error) {
    traceRcPhase(response, 'body.read.error')
    try {
      if (reader) await reader.cancel()
      else await response.body?.cancel()
    } catch { /* Preserve the validation/read failure, including abort. */ }
    throw error
  } finally {
    reader?.releaseLock()
  }
}
