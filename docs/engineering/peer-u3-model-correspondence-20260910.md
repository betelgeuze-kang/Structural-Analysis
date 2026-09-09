# PEER U3: source-to-model loading correspondence

Source `4020b8fec` adds an exact reported-load diagnostic in
[rc_experiment_loading.py](../../src/structural_analysis/benchmark/rc_experiment_loading.py).
This investigation advances reconstruction of the already acquired U3 experiment;
it does not add a new experiment or admit it to learning.

The original PEER-SPD-105 XML and 1,010-pair history match the earlier sealed
[source cohort](peer-spd-cohort-intake-20260909.md). The NISTIR 5984 definition
page and U-series drawing/table are visually inspected (PDF pages 11, 46, 47;
printed pages 3, 38, 39). The sources agree on a 350 mm square cantilever with
1,000 mm measurement length, eight stated 25 mm longitudinal bars, concrete
strength 34.8 MPa, longitudinal yield 430 MPa, hoop yield 470 MPa and 600 kN
compression. NIST distinguishes U3 from excluded variable-axial specimen U5.
This supports a **declared constant axial load**, not a measured third channel.
[NIST source](https://nehrpsearch.nist.gov/static/files/NIST/PB97153522.pdf).

## A specific solver gap

The existing small-displacement RC assembler uses
`external = load_factor * reference_external_load_vector()`. Its rational-force
branch implements the same proportional loading law, and displacement control
differentiates that same reference vector with respect to the one unknown load
factor. Thus adding 600 kN to that reference vector would vary the axial load
alongside the reversing lateral load. That does not reproduce constant-axial U3.

The new diagnostic decodes original bytes and uses exact rational determinants
of reported lateral/axial pairs. A nonzero determinant proves that those reported
vectors cannot all equal one scalar times a fixed vector. Missing axial data
stays unavailable; a declared constant requires a source description, and cannot
replace a measured third column. A collinear result grants no model, licensing,
source-authentication, training or physical-validation approval. No uncertainty
model is inferred from exact reported decimal tokens.

In the actual U3 observation, source lines 3 and 4 contain lateral values
`-12.17` and `-12.21 kN`. Combined with the separately declared `600 kN` axial
load, their determinant is exactly `24 kN²`. An independent rational calculation
from those original text lines reproduces the witness. No sign change, zeroing,
P-delta conversion, interpolation or structural solve occurs. Applied actuator
force versus reported shear correspondence remains a separate requirement.

The source also has **51 consecutive equal-displacement transitions**. Its
initial reported point is `(0 mm, -12.17 kN)`, not a zero-force state. Current
public direct-control requests require successive targets to differ and permit
at most 255 targets. Therefore all 1,010 observations cannot simply become the
current request's commanded targets. Preserving measurement order and native
material history requires explicit long-history/loading work; dropping repeated
rows or treating a measured trace as its command history would not resolve it.

## Reinforcement discrepancy remains explicit

Using the stated circular diameter gives `8*pi*25²/4 = 3926.990817 mm²` of steel
and ratio `0.032057068`, which rounds to PEER's `0.0321`. NIST prints `0.0327`.
A hypothetical 500 mm² bar area would round to that value, but that area convention
is **not established by the inspected sources**. Both originals remain unchanged.
The reported axial ratio `0.141` agrees, after rounding, with
`600000/(34.8*350*350) = 0.140745954`.

NIST's printed page 3 explicitly warns that transverse reinforcement ratios use
mixed volumetric/shear definitions and should be recomputed for their intended
purpose. Therefore interpreting its `1.69` as percent is not, by itself, a
resolution against PEER's `0.017`. The sketch's 260 mm internal annotation is
retained without assigning uncertain endpoints to bar centroids. Source zeros
in ultimate-strength fields are not used as positive measured material capacities.

## Verification, evidence and next implementation

The source/diagnostic test selection passes **31 tests in 1.68 s**. Mypy initially
reports six Decimal-exponent type errors; an explicit finite-integer narrowing
fix then passes mypy, Ruff and the **11 diagnostic tests in 1.60 s**. The selections
overlap. Tests include exact differences hidden by binary64 rounding, a low
Decimal precision context, missing versus explicit zero axial load, measured
channel preservation and invalid later rows after an incompatibility witness.

The actual source audit takes 0.008476147 s internally, excluding imports,
parent setup, file copies, rendering, source review and sealing. Parent time
and peak memory are in the machine summary. Five relevant source/test files
match their Git blobs before and after the observation; original inputs remain
unchanged. No fitting, material integration or structural solver call occurs.

The terminated observer/worker packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-peer-u3-loading-utnixp87`:
15 files / 3,805,835 bytes, inventory SHA-256
`85c45bab7e5699b14440a737fe4fd04cd5a1f29c7a7c2b535a65d3d503f5e0e1`.
The [machine summary](peer-u3-model-correspondence-20260910.summary.json) retains
source hashes, original field tokens, exact witness and explicit remaining work.

The next necessary solver slice is an independently bound constant load pattern
with an accepted preload state, while the lateral pattern varies. It must cover
residuals, load derivatives, reactions, checkpoint/restart, material commit/rollback
and retained arithmetic before connecting to public requests and learned features.
Long-history execution and repeated measured observations require their own
state-preserving handling. Neither numerical mechanism supplies missing material
or sensor definitions. The original article's
[institutional metadata](https://open.metu.edu.tr/handle/11511/64672) shows a
CC BY-NC-ND statement; no full text is obtained and its terms are not transferred
to the PEER history. Reuse, source lineage, calibration assumptions and campaign
splits remain open. The full roadmap and independent validation stay incomplete.
