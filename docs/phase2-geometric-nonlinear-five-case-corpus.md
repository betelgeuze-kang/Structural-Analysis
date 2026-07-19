# Phase 2 geometric-nonlinear five-case corpus

This compact corpus composes the five bounded geometric-nonlinear case types in
the technical roadmap while preserving every source receipt's narrower claim
boundary. It is additive: the original three-seed `v1` artifact remains intact
and continues to describe only its historical Euler, modal-column, and
displacement-controlled shallow-arch scope.

## Covered roadmap cases

| Roadmap case | Bounded implementation | Truth level | High-signal gate |
| --- | --- | --- | --- |
| Euler column | Pinned-pinned beam-column FE convergence | Level 1 analytic | `2.06e-6` finest critical-load error, minimum order `3.877`, mode MAC `1.0` |
| P-Delta frame | Gravity-prestressed three-member portal sway tangent | Level 1 analytic | `1.17e-13` critical-load error, amplification `19.993` at `0.95 Pcr` |
| Shallow arch | Exact two-bar scalar spherical arc length | Level 1 analytic | limit-load error `0.563%`, descending/negative/rehardening path, exact rollback and restart |
| Cantilever large rotation | Continuum elastica plus independent energy discretization | Level 1 analytic | tip rotation `1.121 rad`, minimum mesh order `2.000` |
| Lee frame snap-through | Elastic two-member frame against published Table 11 | Level 3 published | 23 reference points, maximum path distance `1.852 mm`, maximum load-factor error `0.131` |

The Lee source is Leahu-Aluas and Abed-Meraim,
[“A proposed set of popular limit-point buckling benchmark problems”](https://doi.org/10.12989/sem.2011.38.6.767).
The portal case uses the official
[OpenSees P-Delta documentation](https://opensees.github.io/OpenSeesDocumentation/user/manual/model/geomTransf/PDelta.html)
only for terminology; its numerical reference is the independent closed-form
three-coordinate reduction documented in the source portal receipt.

## Composition contract

`build_geometric_nonlinear_five_case_corpus()` executes each complete source
builder and reduces it to a compact capsule containing:

- the roadmap case and exact bounded scope;
- source module and source schema version;
- verification-hierarchy truth level and truth basis;
- source contract result;
- a canonical SHA-256 hash of the full strict-JSON source receipt; and
- the metrics needed to audit the corpus-level decision.

The hash uses sorted UTF-8 JSON with compact separators and `allow_nan=False`.
The corpus test performs two independent complete runs and requires byte-level
equivalent dictionaries and identical source receipt hashes.

The fixed truth-level distribution is:

```text
Level 1 analytic             4
Level 2 code-to-code         0
Level 3 published benchmark  1
Level 4 experimental         0
Level 5 customer shadow      0
```

Therefore `status=partial` remains mandatory even when all five source
contracts pass. The corpus may assert only
`bounded_five_case_geometric_nonlinear_corpus=true` and
`roadmap_five_case_coverage=true`.

Run the focused verification with:

```bash
PYTHONPATH=src python3 -W error -m pytest -q \
  tests/test_geometric_nonlinear_five_case_corpus.py \
  tests/test_portal_frame_pdelta_benchmark.py \
  tests/test_lee_frame_snapthrough_benchmark.py \
  tests/test_cantilever_elastica_benchmark.py \
  tests/test_shallow_arch_arc_length_benchmark.py \
  tests/test_geometric_nonlinear_benchmarks.py
python3 -m ruff check \
  src/structural_analysis/benchmark/geometric_nonlinear_corpus.py \
  tests/test_geometric_nonlinear_five_case_corpus.py
```

## Claim boundary

Passing this composition contract means that one bounded case exists and
passes for each of the five roadmap labels. It does **not** mean those cases
share a production model pipeline or collectively validate arbitrary
structures.

General 2D/3D production frames and shells, a finite-displacement portal load
path, member `P-small-delta` stability functions, material--geometric coupling,
Level 2 code-to-code breadth, Level 4 experiments, Level 5 customer shadow
cases, sparse or ROCm/HIP execution, full-building equilibrium, and G1 closure
all remain explicitly false and listed as blockers.
