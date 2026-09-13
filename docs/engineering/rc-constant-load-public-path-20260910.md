# Constant RC loading through public requests, preload and restart

Source `4fe2ee248ff152ff330139a6308d532049d31449` connects the previously
implemented internal constant-load law to the bounded experimental direct-control
API and CLI. This is development evidence on authored models, not reconstruction
or independent validation of a public experiment.

## Input and executable path

`bounded-rc-fiber-direct-control-request.v2` requires a nonempty
`constant_nodal_loads` array. Each row names a canonical `node_id` and explicitly
supplies `FX_kN`, `FY_kN` and `MZ_kNm`. Duplicate or undeclared nodes, nonfinite or
boolean values, missing/extra component names and zero rows reject. There are at
most 16 rows. These constants supplement the canonical model's proportional
reference loads: `F = F_constant + lambda * F_reference`. Request/resume identity
binds the normalized constant pattern; changing 600 to 601 kN rejects an existing
restart before solving. No geometry, material or load value is inferred from a
paper or drawing.

The [example request](../../examples/public_rc_fiber_frame_constant_axial_control_request.json)
works with the existing authored 3 m cantilever:

```sh
PYTHONPATH=src python3 -m structural_analysis.api.rc_fiber_frame_direct_control_cli run \
  --model examples/public_rc_fiber_frame_cantilever.json \
  --request examples/public_rc_fiber_frame_constant_axial_control_request.json \
  --output /tmp/rc-constant-result.json \
  --checkpoint-output /tmp/rc-constant-checkpoint.json \
  --report /tmp/rc-constant-run.json
```

A real force-controlled solve applies the constant pattern at lambda zero from
the virgin state. Only its accepted checkpoint can parent the lateral path.
Preload is epoch 1; the first lateral target is epoch 2. Directions and reversal
budgets start at the actual preloaded control displacement, not an assumed zero.
Targets remain absolute physical displacements. A failed preload stops before
any lateral call and exports no restart. Its original failed solver result and
known/unknown work remain in the execution error.

The constant-load path and restart use explicit v2 schemas. Restart stores the
preload checkpoint and original preload-result hash. Verification reruns the
preload and every accepted lateral prefix step from virgin material state, then
compares the original bindings and terminal checkpoint exactly. A self-consistent
hash is not treated as evidence of reachability. Preload, replay and suffix work
are reported separately and included in the total.

The public result also uses v2. It recovers a separate `preload_response` and each
lateral response by reassembling the original constitutive transition from its
previous parent and original solver coordinates. Nodal displacements, SI support
reactions, member forces and material points remain source-bound. Direct loads on
the fixed support are included; a 7 kN support load plus 600 kN free-end axial load
yields the expected 607,000 N support reaction in the authored test.

## Verification and retained observation

Seven focused test files pass **353 tests in 42.79 s**. These include unchanged
request/API/CLI behavior, actual v2 run and explicit verification, full/prefix/
resume parity, changed-source rejection, forged preload binding rejection,
preload failure/rollback, actual-origin direction counting, and binary64 plus
native twofold damage/reversal/restart paths. The durable-contract selection
separately passes **54 tests in 5.70 s**. Five changed path/API/control modules
pass mypy; Ruff and diff checks pass.

The initial broader selection had three failed assertions: two tests looked up
an incorrect support-reaction field, and one assumed the failed Newton return
contained counters that it does not supply. Reaction checks now use the existing
`value_si` field. Failed-preload work remains explicitly unknown where absent;
no counters are synthesized. Initial static narrowing/list annotations were
corrected before the successful five-module check. No acceptance tolerance or
physical fixture was adjusted to obtain these passes.

A separate observation launches three fresh processes: archived original
`b2ec2a4f3`, current proportional behavior, and current constant-load behavior.
All six original/current public result and checkpoint artifacts are exactly
equal, totaling **358,848 bytes**, across full, prefix and resumed requests.
This equality is limited to the declared authored fixture.

The constant process performs full, prefix, resume, explicit fresh verification,
and one deliberately nonconvergent preload. Full and resumed checkpoints and
complete response histories match exactly. The successful full/resume/verification
calls each count four solves, including preload; the prefix counts two. Across
all three processes there are **29 core attempts**, **56 known Newton iterations
and 56 known linear solves**, with **one attempt having unknown counters**. The
unknown attempt is the retained failed preload and must not be added as zero work.
No learning fit or external experiment admission occurs.

Per-call elapsed times, separate parent process times, and peak memory are in the
[machine summary](rc-constant-load-public-path-20260910.summary.json). Worker
intervals exclude interpreter/import startup and final report writing; source
archiving, audits and sealing are outside solver timings. This single shared-host
observation establishes no repeated performance improvement.

All **1,339 tracked Python source/test files** match the committed source before
and after execution. All three workers and the observer finish before sealing:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-public-q3_aqs0p`.
The packet contains **41 files / 52,990,949 bytes**, including the original source
archive, original outputs, scripts, reports and initial/final test logs. Inventory
SHA-256: `9bb9bcb47a30cb11b7e6a7cfb8b25bcc6647a7d1faae07c2372c3cc3d90de175`.

## Remaining integration and scientific scope

Existing proportional v1 requests/results remain unchanged in the observed
comparison. Current durable receipts assume the proportional problem and zero
origin; they explicitly reject constant requests before numerical execution
until their model/scope, epoch, preload recovery and budget accounting are
extended. Execution-topology buffers still reject constants. Workbench v2
consumption, durable integration and state-preserving long histories remain open.
The public compiler retains its original binary64 scope; native twofold constant
path/restart support is exercised at the core level.

The 255-target bound and rejection of consecutive equal targets remain in force.
U3's commanded/measured correspondence, whole history, reinforcement/material
reconstruction and source reuse decisions are still unresolved. No external
training sample, independent physical acceptance, hosted-CI closure or release
approval follows from this work. The full roadmap remains active and incomplete.
