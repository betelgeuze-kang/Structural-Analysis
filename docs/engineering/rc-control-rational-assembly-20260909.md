# Rational accumulation during original RC trial assembly

The retained-strain development probes still fail 89 fixed physical comparisons
across the two complete histories. The next explicit benchmark-only profile,
`force_accumulation="rational"`, retains finite returned material stresses and
tangents through the original force/tangent assembly without intermediate
binary64 sum or product rounding. It requires the existing retained-coordinate,
retained-strain material profile. Public API, CLI and Workbench defaults retain
the existing binary64 assembly.

Section integration uses exact fractions of the finite returned stress, tangent,
fiber area and ordinate. Element integration uses exact Hermite coefficients from
the finite original length and quadrature points, with exact quadrature products.
Each original element response records canonical numerator/denominator identities
for its local force and tangent under `rational-fiber-to-frame.v1`. Section and
member reporting arrays are rounded binary64 projections of those exact values.
The original finite transformation matrix is applied rationally, followed by exact
global addition, external load-factor products, residual subtraction and physical
coordinate scaling. The solver receives the final rounded residual and Jacobian.

Consequently, the reported residual can differ from subtracting already rounded
internal and external display arrays. Its authority is the original rational
assembly and explicit element identities plus the compiled problem, not a second
postprocessing solve or a replacement recovered force. The original rounded
material history updates, branch decisions, native coordinates and compensation,
Newton/control/equilibrium gates, commit/rollback and recovery checks remain in
force. The section contract binds the selected accumulation profile; mixed frame
profiles and mismatched native checkpoint contracts are rejected. Existing modes
retain their original response wire shapes and arithmetic paths.

A separate read-only verifier reconstructs exact section and member force/tangent,
transformation, global loads, residual, Jacobian and reactions from original saved
fiber responses. It uses a separately expressed Hermite polynomial and dense
matrix equations rather than the production accumulation helpers. Every explicit
rational identity and rounded reporting field must match. It performs no material
integration, Newton solve or commit. The older saved-force diagnostic rejects this
profile so that its binary64 replay cannot misrepresent rational assembly.

Focused tests cover cancellation, independent original-record reconstruction,
tampered exact and reported records, scaled-frame finite differences, material
runtime coverage, fresh-interpreter native continuation, contract rejection,
genuine failure rollback and cyclic original recovery. The related frame and benchmark
regression neighborhood passes 556 tests in 453.75 s, including all 11 new
rational-accumulation tests; Ruff and diff checks pass. All resulting local test and
verification costs remain separate from nonlinear path costs.

Before full observation, six existing profiles are compared with the preceding
frozen retained-strain source in fresh processes. Two serial fresh development
probes retain both original geometries, all 242 targets, three original paths,
shared polishing and fixed absolute `1e-10` / relative `1e-8` comparisons. Both
complete physical passes are required before repeated timing qualification.
Negative results are retained, and single observations cannot establish speedup,
independent physical validation, public capability admission or roadmap closure.
