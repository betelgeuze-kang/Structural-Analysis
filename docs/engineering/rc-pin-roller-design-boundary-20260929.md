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

The durable job transport still supports only the one-fixed-endpoint RC profile.
Previously it decoded a v3 or v4 request, then compiled its model using the
default profile. A cantilever paired with either incompatible flag could pass
submission validation even though the worker would use different support
semantics. It now rejects both flags explicitly before the default compiler or
worker dispatch. The direct-control API/CLI remain the available experimental
route for the two-fixed-endpoint and pin/roller profiles. This change does not
enable a pin/roller durable worker or browser submission service.

Validation: all 11 new cases failed against the previous implementation. After
the correction, the five-file regression selection passed 180 tests, including
the existing cantilever/portal design comparisons and durable contract/service
tests. Ruff and whitespace checks passed. These are local software observations;
the browser review of saved originals, measured-specimen validation, operational
budgets, official support and release qualification remain separate work.
