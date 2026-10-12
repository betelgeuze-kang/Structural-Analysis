# Explicit steel layers in the narrow RC workflow

The canonical public RC compiler accepts `rectangular_rc_explicit_steel_layers`
alongside its existing rectangular section. This format avoids replacing distinct
bar areas, positions or material laws with a common equivalent reinforcement.
It uses the mixed constituent state/recovery implementation introduced in PR577.

Required section fields are `id`, `type`, `width_m`, `depth_m`,
`concrete_layer_count`, `concrete_material` and `steel_layers`. Each steel layer
contains exactly `id`, `y_m`, `bar_count`, `bar_area_m2` and `steel_material`.
The layer coordinate is measured from the concrete section centroid; positive
`y_m` is the same coordinate used by `epsilon = epsilon_0 - kappa * y_m`.
Rows must be strictly increasing inside the section depth, with unique IDs.
There are 1-32 layers, 1-64 bars per layer, and 2-32 concrete integration layers.
Material references must name declared materials of the correct constituent type.
Unused materials, extra fields, nonpositive areas and total steel area at least
equal to gross section area are rejected. Layer area is count times individual
bar area. No cover or material default is inferred for this format.

`examples/public_rc_fiber_frame_explicit_layers.json` is an **authored software
case**, not an Alberta or other measured specimen. Its three steel layers use
different centroid positions, areas and laws. Gross concrete volume and straight
longitudinal reinforcement quantities use the original geometry, once per member;
transverse steel, laps, anchorage, waste and construction costs remain excluded.
The example's total straight steel mass is 28.26 kg at the declared density of
7,850 kg/m3. This does not establish a measured takeoff or verified quote.

The typed direct-control request and durable job carry the original canonical
model unchanged. A changed layer invalidates a previous restart. Reopened quantity
reports bind to the successful original job and recompute the sum of individual
layer areas in the browser reviewer. Their structural/physical authority flags
remain unchanged. Existing common-bar section arithmetic remains exact.

The actual browser tests submit both legacy and explicit-layer inputs, kill the
first real worker after a committed checkpoint, restore with a fresh worker,
reopen the HTTP service and browser, save two price-only report revisions, and
download the original persisted second revision. These tests neither inject a
completed result nor perform a solve in HTTP/report handling. They verify the
product path on authored inputs; public-source specimen qualification remains open.

Scope is the existing bounded planar canonical RC path. This change does not add
general Model IR frame support, pin/roller support by itself, lateral bar-position
or clear-spacing design checks, shear, confinement, bond slip or a physical
acceptance tolerance. PR575 supplies the separate pin/roller support profile and
PR573 the separate operator backup interface. Their final merged combination
still requires exact-source integration checks. Public specimen force/datum,
nominal layer coordinates, test-day constitutive assumptions and applicable
response interval must be recorded before measured-versus-solved acceptance.

## Optional finite circular bar integration

An explicit layer may include `circular_integration_points` (integer 2 through
64). Omitting it preserves the existing centroid-point layer and its fiber IDs.
Selecting it declares that `bar_area_m2` is the area of a solid circular bar;
the radius is `sqrt(bar_area_m2 / pi)`. The complete circle, rather than only
its center, must lie strictly inside the section depth and fit inside its width.
This does not infer horizontal bar placement or prove detailing compliance.

The compiler uses Gauss-Chebyshev second-kind weights for the circular chord
area, creates one independent material state per integration point, and repeats
the authored steel law at each point. Bars sharing a layer share planar strain
kinematics; their count multiplies each integration weight. Authored quantities
continue to use bar count and area, not integration-point count. The maximum
is 32 layers times 64 steel integration points, plus the existing concrete
layers. Increasing points increases solver state and work.

Area, centroid, and intrinsic second moment are integrated exactly in the
elastic limit up to floating-point error. Two points are not a claim of
nonlinear convergence. Users must check convergence for their cyclic loading.
Changing the integration count changes the original source identity and the
section contract; a prior checkpoint cannot be reused with a changed count.

This option does not replace gross concrete by net concrete, add bond slip,
introduce a new steel law, or establish TC11 physical validation. Those model
correspondences remain separate requirements.
