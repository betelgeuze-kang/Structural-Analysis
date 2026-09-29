# Pin/roller RC beam: consistent scoped quantities and request rejection

The experimental v4 direct-control beam profile was accepted by the solver, but
`compare_rc_control_designs()` dropped its explicit profile when calculating
member quantities. Both the baseline and its alternatives therefore stopped in
preparation, before any numerical execution. The quantity function now accepts
`experimental_pin_roller_beam=True`, checks the same compiler boundary, and the
design comparison passes the request's flag through unchanged.

Quantities still cover gross concrete and the authored straight longitudinal
bars, once per physical member. The synthetic seven-node regression includes
both overhangs: its total member length is 1.9 m, not just the 1.5 m support span.
Section integration refinement does not multiply those quantities. The existing
exclusions for laps, anchorage, hooks and other detailed takeoff items remain.
Malformed boolean opt-ins, mutually enabled profiles, incompatible supports and
non-horizontal geometry are rejected.

The regression executes baseline and narrower-section models with two prescribed
displacements, both with and without a constant-load preload. Each model keeps
the v4 request, pin/roller reaction identities, original result and checkpoint,
and a separate fresh full-path verification. Its synthetic common rates produce
an estimate difference of 4.56; this checks arithmetic and scope only, not a
construction quote, realized currency saving or independently validated response.

At parent source `3021a69b54d073b6f5dee7e329545bbe4f1237a7`, the durable job
transport supported only the one-fixed-endpoint RC profile. Before that correction
it decoded a v3 or v4 request, then compiled its model using the
default profile. A cantilever paired with either incompatible flag could pass
submission validation even though the worker would use different support
semantics. That parent correction rejected both flags explicitly before the
default compiler or worker dispatch; it did not enable a pin/roller durable
worker or browser submission service. The subsequent integration below extends
that transport boundary only where explicit support is implemented.

Validation: all 11 new cases failed against the previous implementation. After
the correction, the five-file regression selection passed 180 tests, including
the existing cantilever/portal design comparisons and durable contract/service
tests. Ruff and whitespace checks passed. These are local software observations;
the browser review of saved originals, measured-specimen validation, operational
budgets, official support and release qualification remain separate work.

## Integrated proportional-load durable path

PR #469 now incorporates the parent correction and the #471 tensile-onset
regression. An explicit pin/roller request without constant preload passes its
profile through the durable compiler, worker, saved result and Workbench review.
A cantilever mislabeled as a pin/roller beam still fails its model check; the
two-fixed-endpoint profile and a canonical pin/roller request with constant
preload still fail before model compilation. Constant-preload support in the
direct-control API and review of its original files does not imply support in
this durable job path.

On integrated source `cd9e063b7f97d8279a25c8fb9645902d2296c4b6`, 119 Python
tests passed for the public beam, durable request/worker and quantity/design
boundary. The synthetic tensile-onset regression retains the default blocked
path with exact rollback and the explicitly weighted control configuration's
accepted, freshly verified result. Solver defaults and equilibrium criteria are
unchanged; this is not evidence from a measured specimen.

The pinned Node 24.20.0/npm 11.19.0 environment installed the unchanged lockfile
with fast-uri 3.1.8; vulnerability and package-signature audits passed. The build
and 84 existing contract/browser cases passed in desktop and mobile Chromium
configurations (1280x720 and 390x844). They cover saved conventional and constant
jobs, pin/roller original files and saved pin/roller jobs, including byte-exact
downloads and altered-profile/reaction rejection. These saved-artifact tests do
not exercise a live HTTP job submission service or establish a mobile response
time guarantee. That broader service integration remains separate work.
