/** Credentials are supplied by the embedding application for one load only. */
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
  get(role?: string, accept?: string): Promise<Response>
}

const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)\b/i

/** Resolve the destination before asking the host for credentials; never follow redirects. */
export async function createJobReadTransport(
  statusUrl: string,
  signal?: AbortSignal,
  authorize?: JobAuthorizationProvider,
): Promise<JobReadTransport> {
  const origin = typeof location === 'undefined' ? undefined : location.origin
  const url = new URL(statusUrl, origin)
  if (!/^https?:$/.test(url.protocol) || url.username || url.password || url.search || url.hash
    || (origin !== undefined && url.origin !== origin)
    || (authorize && origin === undefined)) {
    throw new JobArtifactError('job_endpoint_invalid')
  }
  url.pathname = url.pathname.replace(/\/+$/, '')
  const headers = new Headers()
  if (authorize) {
    let credentials: JobAuthorization
    try {
      credentials = await authorize({ statusUrl: url.href, signal })
    } catch {
      // A host exception may include credentials. It is never a UI diagnostic.
      throw new JobArtifactError('job_authorization_unavailable')
    }
    if (!credentials || typeof credentials.tenantId !== 'string'
      || typeof credentials.bearerToken !== 'string'
      || !/^[\x21-\x7e]{1,256}$/.test(credentials.tenantId)
      || !/^[\x21-\x7e]{1,4096}$/.test(credentials.bearerToken)) {
      throw new JobArtifactError('job_authorization_invalid')
    }
    headers.set('X-Structural-Tenant', credentials.tenantId)
    headers.set('Authorization', `Bearer ${credentials.bearerToken}`)
  }
  signal?.throwIfAborted()
  return {
    async get(role, accept = 'application/json') {
      if (role !== undefined && !/^(request|checkpoint|result|evidence|rc-invocations(?:\/[1-9][0-9]{0,3})?)$/.test(role)) {
        throw new JobArtifactError('job_artifact_role_invalid')
      }
      signal?.throwIfAborted()
      const requestHeaders = new Headers(headers)
      requestHeaders.set('Accept', accept)
      const response = await fetch(`${url.href}${role === undefined ? '' : `/${role}`}`, {
        method: 'GET', credentials: 'include', cache: 'no-store', redirect: 'error',
        headers: requestHeaders, signal,
      })
      if (!response.ok) await response.body?.cancel()
      return response
    },
  }
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
    if (target) return target
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) {
      bytes.set(chunk, offset)
      offset += chunk.byteLength
    }
    return bytes
  } catch (error) {
    try {
      if (reader) await reader.cancel()
      else await response.body?.cancel()
    } catch { /* Preserve the validation/read failure, including abort. */ }
    throw error
  } finally {
    reader?.releaseLock()
  }
}
