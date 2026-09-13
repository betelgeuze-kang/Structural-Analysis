# Finer numerical reference around sampled plastic onset

One fresh research-only 128-layer model commits the first fourteen displacement
targets (2 through 28 mm in 2 mm increments). All fourteen accepted targets are
compared against the corresponding prefix of the retained 64-layer path. All 140
group comparisons pass the unchanged exploratory 1% screen. The largest internal
steel-variable difference is 0.733736% at 24 mm, versus the earlier 1.512258%
32-to-64 comparison at that target.

This is a bounded prefix comparison, not an exact solution or a convergence
certificate for the original forty-target 80 mm history. The preceding loading
history is rerun from the initial state; the 24 mm state is not reconstructed
without its parents. The endpoint was fixed before execution to include sampled
plastic onset and its next two targets. No targets, tolerances or solver budgets
were changed after observing the result.

Source revision remains `3e2cc1dba5c6dac1b12eb1badc9b6df09337b847`. The runner
verifies source and canonical input hashes, exactly reconstructs the source
32-layer sections, then changes only concrete quadrature to 128 layers through
the low-level builder. Steel fibers, materials, geometry, loads, integration
order, control DOF 15 and direct-control defaults remain unchanged. The public
API is not extended. The entire force vector remains proportional, including
vertical forces; this is not constant-axial loading.

| Group | Maximum 64-to-128 difference | Target |
| --- | ---: | ---: |
| Translations | 0.006225% | 24 mm |
| Rotations | 0.015330% | 20 mm |
| Support forces | 0.013918% | 2 mm |
| Support moments | 0.016020% | 14 mm |
| Load factor | 0.013993% | 2 mm |
| Steel stress | 0.059701% | 24 mm |
| Plastic strain, accumulated plastic strain, backstress, energy density | 0.733736% each | 24 mm |

At 24 mm, the absolute plastic-strain difference is 6.253945266e-7 and the
128-layer group infinity norm is 8.523431538e-5; the denominator floor is 1e-12.
The finer comparison reduces the difference but does not turn the 32-layer result
into a qualified full-history reference. A separate source-hash-checked
32-to-128 extraction at the same target finds a 2.249742% group difference, with
the same E1 first-integration-point/top-steel witness. Its plastic strains are
3.376913971e-6 and 5.294466187e-6, an absolute difference of 1.917552216e-6.

The accepted-state auditor verifies all available checkpoint chains and
member/section/steel trial-to-accepted bindings, matching steel labels and
integration coordinates/weights. Concrete fibers at different locations are not
matched. All outcomes remain numerical observations without physical validation,
training admission, learned benefit or original factor-1 load-path recovery.

Single core path time is 109.469644 s, compilation/reconstruction 0.494250 s,
and the experiment interval including output serialization/hashing is
117.117949 s. Source verification and the separate auditor are outside that
interval. No runtime ratio is interpreted as a speedup because this experiment
uses different quadrature and a shorter target path.

The retained packet contains pre-run protocol, runner, full path, summary,
auditor and all fourteen group comparisons:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-plastic-onset-reference-zukafnjo`

Six payload files, 248,649,051 bytes; inventory SHA-256:
`44c3ecd50b138eb40a7b0eeafc3e3645cedf3c9532cc50320a066d2313555411`.
128-layer path SHA-256:
`bf45ac18cc8cba25df3d79df3753b8f72f27bbb6fe556629b2605942e533dcc2`.
The runner creates a new directory and records its location in
`/tmp/structural-plastic-onset-reference-root.txt`; the auditor uses that location
and the preserved 64-layer path. The original 28-to-80 mm material history still
requires its own finer-reference comparison.

## Development CI integration

The six fixed-source witness-audit integrity tests are now explicitly listed in
the independent development-contract lane of `python-test-collection.yml`.
They pass locally (6 passed). This supplies diagnostic coverage even when
external-evidence preparation blocks full shards. It does not change the full
suite's requirements or claim that hosted execution at this local revision has
already occurred.
