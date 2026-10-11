# Explicit pin/roller RC beam workflow

This integration adapts the pin/roller boundary introduced in draft PR #439
(commit `0861a2e62fd47e860f22f611d27ab1360e4f6a51`) to current main's bounded
control API and durable workflow. It does not import the draft's AI, preload,
two-fixed-endpoint, or protected-evidence changes.

The experimental opt-in admits a straight horizontal X-monotone serial beam,
including end overhangs, with one UX/UY pin and a distinct UY roller. Rotation
is free at both bearings. Duplicate/malformed supports, two pins/rollers,
nonhorizontal or folded geometry, and nodal loads applied to bearings are
rejected. Canonical XY coordinates, section/material restrictions and existing
bounded target/reversal budgets remain applicable. This is not general frame
or general RC failure support.

`BoundedRCFiberDirectControlRequest(experimental_pin_roller_beam=True, ...)`
serializes as `bounded-rc-fiber-direct-control-request.v4`. A saved request uses
`structural-analysis-job-request.v4` and must carry that explicit true flag.
Preload and other draft extensions remain rejected. Existing v1 control/v3 job
requests retain their prior serialized form. The original public monotonic
cantilever API remains limited to its original profile.

Compilation, direct result source bindings, restart replay, durable chunk
validation and quantity rederivation use the selected profile. Reaction output
contains only restrained DOFs. Report inputs retain the original model/config
bindings and declared prices carry no quote or savings authority.

The built Workbench accepts explicit v4 requests, reviews genuine source-bound
worker artifacts and reopens/downloads price-only report revisions. New fixtures
are synthetic: they do not represent an admitted public experiment. The browser
owns submission; actual child workers solve and verify; the original worker is
killed and reaped; fresh HTTP and browser contexts reopen the saved job. No
completed solver response or browser reviewer is injected.

Evidence is software workflow evidence. Public specimen input correspondence,
material laws, observed numerical histories and applicable physical intervals
remain independent admission/comparison gates. Initial failure while extending
the fixture came from its cantilever-only request allowlist; the final harness
allows exactly its two fixed requests, not arbitrary models or solver injection.
