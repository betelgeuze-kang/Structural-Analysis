# Workbench web application boundary

Workbench is a result/evidence and durable-job consumer. It never defines solver
truth. Configure a same-origin status endpoint through `VITE_JOB_STATUS_URL`;
invalid, missing, or cross-origin configuration remains unavailable in the UI.

See [`docs/workbench-v2.md`](../../docs/workbench-v2.md) and
[`docs/durable-job-service.md`](../../docs/durable-job-service.md).
