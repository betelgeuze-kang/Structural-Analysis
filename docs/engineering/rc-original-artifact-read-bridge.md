# Authenticated original request/checkpoint reads

This read-only bridge follows the RC durable-service and quantity-report slices.
It supplies the original bytes required by the real browser reviewer without
adding a solver path or changing existing result/evidence reads.

- `GET /v1/jobs/{job_id}/request` reads the immutable submitted request in any
  lifecycle state
- `GET /v1/jobs/{job_id}/checkpoint` reads the last attached checkpoint, including
  while running or after failure/cancellation; it does not create a checkpoint
- Both require existing `X-Structural-Tenant` and bearer credentials and enforce
  tenant custody in the service itself, even without the HTTP adapter
- Returned bytes are exact stored bytes, not decoded/re-encoded JSON. Reads
  verify stored SHA-256 and length, preserve the reference media type, and use
  `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and the optional
  `X-Structural-Artifact-Sha256` header
- Request and checkpoint limits remain 16 MiB and 128 MiB respectively. Invalid
  size metadata fails before opening an artifact file
- A checkpoint that advances between the job-view and byte read produces HTTP
  409 `artifact_reference_changed`; clients must refresh the job view
- A pending/missing checkpoint reference returns the existing HTTP 400 JSON
  error `artifact_not_published`. Wrong credentials return 401; another tenant's
  job returns 404. Error bodies retain `structural-analysis-job-http-error.v1`
- Nonempty GET bodies are rejected; POST on either read route returns 405

`tests/test_rc_original_artifact_reads.py` creates genuine RC artifacts once,
then forbids numerical dispatch for read tests. It checks exact bytes/media/
hashes, unchanged numerical database rows, direct-service and HTTP authorization,
pending and interrupted states, corrupt/missing bytes and length metadata,
reference races, bounded reads and method/body rejection.

These routes do not attest independent physics or source authentication. They
enable a separately reviewed browser integration; their local tests alone do
not establish a Workbench or hosted-browser pass.
