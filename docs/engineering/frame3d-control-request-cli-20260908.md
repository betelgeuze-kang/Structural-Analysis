# Portable requests for bounded experimental Frame3D control

The existing 3D candidate API can now execute a strict JSON control request through
`structural-analysis-bounded-frame3d-control` or the equivalent Python module.
This replaces the need to write a custom Python worker for each persisted restart
experiment. It uses the existing ModelIR adapter, solver, result validator and
checkpoint codec. Registry-public, Workbench, independent V&V, design and release
authority remain at their existing values; this is an experimental execution
interface rather than a capability promotion.

## Request contract

`bounded-frame3d-direct-control-request.v1` requires `control_node_id`,
`control_dof` and `control_targets`, with optional `solver_config`. A minimal
monotonic request for the existing axial example is:

```json
{
  "schema_version": "bounded-frame3d-direct-control-request.v1",
  "control_node_id": "N2",
  "control_dof": "UX",
  "control_targets": [0.003, 0.006]
}
```

Translations use metres and rotations use radians. The selected coordinate must
be a supported free DOF in the source model; a request does not override ModelIR
semantics. The request adapter calls the existing typed constructors for every
solver/control/frame setting and both named sparse factorization policies. JSON
line-search arrays restore the required tuples. Unknown fields, duplicate keys,
nonfinite numbers, integer/boolean confusion, malformed UTF-8 and excessive
size/depth are rejected before analysis. Lossy integer-to-binary64 conversion in
numeric settings or target/line-search arrays is also rejected. The request limit
is 128 KiB, ModelIR
limit 16 MiB and checkpoint limit the existing 8 MiB.

`bounded_frame3d_direct_control_request_payload(config)` exports all constructor
settings, including nested frame and factorization settings, and confirms a
decode round trip preserves the exact request and resume-contract hashes.
`decode_bounded_frame3d_direct_control_request(raw_bytes)` reconstructs the typed
config without running a solver. Both functions live in
`structural_analysis.api.frame3d_direct_control_request`.

A provided factorization-policy object must carry a supported `policy_id`.
The two existing named exact/scalable profiles retain their own constructors and
defaults. Omitted frame policy retains the 3D default condition/pivot thresholds
`1e14`/`1e-16`; it is not replaced by the public planar policy. Unsupported policy
IDs and derived backend/hash/authority fields cannot select or rewrite a policy.
CLI transport does not widen model, material, equation or reversal limits.

## Running and resuming

Prepare a model copy and full-setting requests without running an analysis:

```bash
PYTHONPATH=src python3 examples/prepare_bounded_frame3d_control_requests.py \
  --output-directory /tmp/frame3d-control-inputs
```

The new directory contains `model.json` and monotonic, full cyclic, cyclic prefix
and suffix requests. The cyclic example controls N2/UX through
`0.003, 0.006, 0.001, -0.004, 0.002 m`, with explicit reversal permission and budget.
Run the prefix, let that process exit, then resume from its persisted artifact:

```bash
PYTHONPATH=src python3 -m structural_analysis.api.frame3d_direct_control_cli \
  /tmp/frame3d-control-inputs/model.json \
  --request /tmp/frame3d-control-inputs/cyclic-prefix.request.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --out /tmp/frame3d-control-prefix/result.json \
  --report-out /tmp/frame3d-control-prefix/execution.json \
  --checkpoint-out /tmp/frame3d-control-prefix/checkpoint.json

PYTHONPATH=src python3 -m structural_analysis.api.frame3d_direct_control_cli \
  /tmp/frame3d-control-inputs/model.json \
  --request /tmp/frame3d-control-inputs/cyclic-suffix.request.json \
  --restart-checkpoint /tmp/frame3d-control-prefix/checkpoint.json \
  --source-revision FULL_GIT_COMMIT_SHA \
  --out /tmp/frame3d-control-resumed/result.json \
  --report-out /tmp/frame3d-control-resumed/execution.json \
  --checkpoint-out /tmp/frame3d-control-resumed/checkpoint.json
```

The source identity must be a full lowercase commit or `sha256:` identity. It is
a caller declaration; the CLI neither switches source trees nor attests source
execution. Model provenance/content/semantic hashes remain bound by the existing
API. Run `cyclic-full.request.json` in another output directory to compare an
uninterrupted execution with the resumed terminal state.

## Outputs and failure handling

`--out` is the unchanged API result v2. `--report-out` is a separate execution
report binding the exact input bytes, full control/request/resume identities,
result and model hashes, supplied source identity and existing authority flags.
The existing API validator must pass and the result must match the actual
ModelIR/control input before publication. A structurally valid blocked result
has `result_contract_validation_passed=true` and `execution_contract_pass=false`;
passing serialization validation cannot turn it into successful analysis.

Exit 0 means a ready, contract-passing candidate result. Exit 2 indicates invalid
input/output or blocked execution. Invalid requests and detached results do not
replace existing outputs. A blocked execution preserves the actual partial
result and exact checkpoint if the API supplies one. If no checkpoint is
available, an explicitly requested stale checkpoint target is removed while the
new blocked result/report is published, following the shared CLI output helper.

All outputs must be distinct, non-nested paths that cannot alias model, request
or restart inputs. Existing symlink/hardlink aliases are checked before reading
models or entering the solver, and path bindings and input bytes are checked
again before publication. Output replacement uses the repository's shared staged
write and best-effort rollback. It is not a cross-file power-loss transaction or
a lock against simultaneous output-content edits by another writer.

The durable job service remains bound to its 2D job schema and load-step progress
contract. This CLI does not add a 3D job or Workbench capability, independently
verified numerical authority, design acceptance or release approval.

## Focused verification

- Request transport, full constructor/6DOF/two-policy round trips, hash identities
  and invalid inputs: **116 passed in 1.69 seconds**, with zero solver executions.
- New CLI integration/negative group: **51 passed in 52.86 seconds**, with three
  test-only failures caused by using `completed_target_count` instead of the
  producer's `completed_requested_target_count`. After correcting those
  assertions, all **3 focused tests passed in 11.98 seconds**. These are separate
  runs; the actual fixture made seven solver calls in the first run and four in
  the focused rerun, eleven total. They cover monotonic and rotational controls,
  cyclic fresh-process prefix/resume/full equality, valid partial and zero-target
  blocked results, invalid/detached inputs, source/control binding, unchanged
  authority, aliases, input/path changes during execution and output rollback.
- Existing fresh-process 3D restart regressions: **5 passed in 40.33 seconds**.
- CI ownership/quality-gate contracts: **34 passed in 0.44 seconds**.
- Changed-file Ruff, compilation and whitespace checks passed.

The CLI test initially could not collect under Python 3.10 because it imported
`tomllib` without the existing `tomli` compatibility fallback; the test import
was corrected before the reported execution groups. The numerical producer was
not changed for either test correction. These checks are local integration
evidence and do not establish performance, independent reproduction or a
repository-wide full-suite result.
