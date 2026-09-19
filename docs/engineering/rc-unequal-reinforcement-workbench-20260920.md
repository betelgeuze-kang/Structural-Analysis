# Unequal reinforcement in Workbench review

Both physical-design and direct-control design report validators now compute
longitudinal steel from separate top/bottom areas plus intermediate common-area
bars. Optional area values must be positive finite numbers: explicit null,
Boolean, string and nonfinite values are rejected. Candidate-change validation
recognizes the two optional override fields without requiring them in legacy
reports. Both panels display each outer layer's count and area separately;
intermediate bars, when present, are described at their common area.

The previous UI would recompute quantities using the common area only and reject
valid new reports, while its description implied identical top/bottom areas.
The backend reported values and their original source/byte/hash bindings are
retained; the UI does not replace them with recalculated results.

Validation: TypeScript no-emit check passed. Four selected Playwright suites
passed **131 tests in 26.0 s**, including existing design/history/control integrity
checks, invalid override values, retained intermediate bars, and rejection of stale
common-area quantities. An actual public Python comparison generated at
`6c9c17e694e0fda232a23e10151b65c66232fb7a` passed full reference verification
before becoming `tests/frontend/fixtures/unequal-steel-comparison.json.gz`.
The generator is `scripts/build_unequal_reinforcement_workbench_fixture.py`.
It uses a synthetic price table and is not experimental evidence.

Desktop (1440 px) and mobile (390 px) browser tests route the exact original
report bytes through the configured manifest and show top 4 × 0.0002 m² and
bottom 4 × 0.0004 m². Mobile panel screenshot was inspected. Wide comparison
tables retain horizontal scrolling. This is display/import coverage, not a new
interactive reinforcement editor or a physical qualification claim.

The new regression file is included in the Workbench E2E runner. Cross-area
learned ranking, independent specimen admission and full CI acceptance remain
open. The first test invocation lacked the local web server and tried unsupported
Playwright-transformed JSX in server rendering; the final run uses a live Vite
server and actual browser rendering.
