# Cooperative RC job control

This contract extends the authenticated durable service for the existing RC
fiber and corotational direct-control workers. It does not change numerical
requests, start workers, interrupt Newton iterations, or control generic
`nonlinear_frame` jobs. See [Workbench controls](rc-workbench-authoring-scenarios.md).

`GET /v1/jobs/{job_id}/rc-control` returns `rc-job-control.v1` from the job row and
its validated event history. It does not load cumulative result/checkpoint
artifacts or execute a solver. The existing JobView schemas, database status
values and `can_resume` meaning remain unchanged. A separate `paused` control
state holds an existing queued/checkpointed job.

`POST` to the same endpoint requires this exact object, bounded to 16 KiB:

```json
{
  "schema_version": "rc-job-control-request.v1",
  "control_id": "rc-control-67b472a5-38d8-4cd7-81ab-ad34886bd971",
  "action": "pause",
  "expected_request_hash": "sha256:<64 lowercase hex characters>",
  "expected_checkpoint_hash": null,
  "expected_control_revision": 0,
  "expected_attempt": 0
}
```

Actions are `pause`, `cancel`, and `resume`. The expected values come from a
fresh control read. Boolean values are not integers. Both successful GET and
POST return HTTP 200 with no-store headers. POST returns
`rc-job-control-command-result.v1`: the accepted `control_id`, canonical
`command_hash`, `accepted_control_revision`, and the current `view`.

The receipt identifies the submitted command while the view describes current
state. Retrying an older accepted command may return a newer current view. The
same ID and canonical command is idempotent even after its original CAS values
become stale. Reusing an ID with different content is a conflict. A new command
with stale expected request/checkpoint/attempt/control revision is also a
conflict. Heartbeats alone do not invalidate the control CAS. Clients must not
automatically replace a rejected or uncertain command with a new identity.

Requested and resolved events use the existing hash-linked job event store.
A pure reducer checks semantic order in addition to byte/hash integrity. The
same checks participate in service admission and explicit integrity validation
after restore. Raw byte backup/restore receipts continue to state
`application_integrity_checked: false`; byte preservation is not application
validation.

Analysis reservation and control acceptance serialize in the database writer
transaction. If a control request wins, no new analysis is reserved. If analysis
wins, its mandatory verification may finish with its original chunk/attempt
binding. A verified checkpoint and the resulting hold/cancel are committed
together. Workers treat an applied boundary as normal control flow, not a
numerical failure. Existing generation, lease and execution-permit protection
remains active.

For a final chunk, a prior cancel keeps the previous verified checkpoint and
suppresses final-result publication. A prior pause resolves as completed and
allows normal completion. Completion committed first rejects later new control
commands. Actual worker/verification failures retain their error, and lease
expiry applies pending control to the last verified prefix. Recorded and unknown
reservations are never refunded. Resume releases only the pause hold and cannot
change the request, checkpoint or execution budget.

Use an upgraded service together with the upgraded RC workers. An older service
writing the same SQLite database cannot enforce the new overlay and is not a
supported mixed deployment. Legacy cancel/resume routes cannot bypass an active
control hold or pending command. No database migration, deployment or permission
change is performed by this source change.
