# Price-order layout preflight preserves control and preload correspondence

Legacy v1/v2/v3 layout descriptors preserve their original context format. That
format does not bind an authored global control DOF or a constant-load node name
to a canonical physical slot. Declaration permutations or name remapping can
therefore change control/preload meaning within an otherwise equal context.
Combining that change with an admitted geometry or section alternative also
avoids the existing duplicate-physical-model rejection.

A no-solve observation loaded `rc_control_layout_search.py` directly from Git
source `253da5ee9cc09e45089457975b27c21641375032`. Four new authored counterexamples
completed its standalone price-order preparation: v1 control permutation with
section change, v1 control permutation with geometry change, v2 preload-name
remapping with section change and v3 control permutation with section change.
Each observation stopped at the first output-directory creation call, before
creating it. Numerical execution and artifact-writing entry points were
forbidden and observed zero calls. This establishes a preflight acceptance gap,
not an executed structural response or experimental measurement.

The shared `_run_layout_search()` pool preparation now checks standalone
`price_order` inputs immediately after their existing actual compiler/descriptor
and fixed-context checks. It resolves each authored node ID/index to the same
lexicographic XY canonical node rank used by the physical payload. The binding
contains the canonical control rank, component offset and constant-load tuples
sorted by canonical rank, with exact FX/FY/MZ values. It compares that binding
with the baseline before preparing the next quantity row, ranking candidates,
creating the output directory or invoking numerical execution. Missing control
or preload nodes and unequal bindings raise `ValueError` at that boundary.

Canonical rank is compared under the already equal fixed context. Absolute
coordinates are allowed to change in a layout study, including translation.
Node names and declaration order may change while preserving the controlled
slot and preload slots. Frozen descriptor/context bytes, policy formats, output
schemas, native tolerances and existing solver/quantity/price/restart authority
retain their contracts. The guard covers the full, cost-pruned and prefix-staged
standalone price-order wrappers through their existing common entry point.

The new `tests/test_rc_layout_price_order_preflight.py` passed **30 checks in
2.34 seconds** on the final modified local source. Its actual authored small
models pass existing descriptor compilation and retain equal context hashes;
the rejection alternatives have distinct physical identities. All three
wrappers reject the control/preload counterexamples and missing bindings before
output creation or any forbidden numerical/artifact call. Positive loaded cases
reach the first output boundary, where the test stops without creating files.
They cover valid geometry changes, translation, section changes, declaration
permutations and node renaming while preserving control/preload correspondence.
Original model, request and descriptor bytes remain unchanged. Component and
exact-load distinctions are checked separately. Ruff lint/format and
`git diff --check` passed.

The initial new-test setup referenced the wrong validator symbol, and its
outside-model control example initially exceeded the request's global bound.
Those harness errors were corrected to the actual artifact validator and a
decoder-valid DOF outside the four-node model. No production solver failure,
load, tolerance, descriptor or existing fixture was altered to pass the checks.
Command/result observations and final changed-file hashes are retained under
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/pr-backlog-20260929/rc-readiness-goal-20261002/legacy-layout/`.

The compatibility scope remains limited. Dataset preparation, label generation,
training, direct learned-policy prediction, standalone `learned_order` and the
combined two-arm comparison still use their legacy context contracts. The
combined comparison's price arm is outside this standalone guard. Existing
policy bytes do not attest their historical canonical control/preload binding.
Those paths need a separate compatibility and validation scope; this correction
does not qualify old policies, functional equivalence, independent physical
accuracy, commercial savings or release readiness. Exact-final-commit hosted CI
and the complete integrated RC workflow remain separate evidence.
