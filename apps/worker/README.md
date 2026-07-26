# Durable worker application boundary

`job_service_app.create_application(...)` composes the single-host SQLite/WAL
job service and its WSGI transport. Credentials and worker-to-tenant scopes are
mandatory constructor inputs; this directory contains no default token and does
not read an environment file.

The mount must be placed behind operator-managed TLS, authentication secret
delivery, request limits, backups, observability, and process supervision. The
library itself provides transactional state changes, time-bounded worker leases,
idempotency, tenant isolation, content-addressed artifacts, hash-chained events,
and exact checkpoint binding. It does not provide distributed consensus or
multi-host failover; those remain P3 work.

Workbench may read `GET /v1/jobs/{job_id}` and, after success, the referenced
`result` and `evidence` endpoints through a same-origin authenticated gateway.
The UI treats those as integrity-bound core artifacts and never turns job status
into solver convergence or an engineering verdict.
