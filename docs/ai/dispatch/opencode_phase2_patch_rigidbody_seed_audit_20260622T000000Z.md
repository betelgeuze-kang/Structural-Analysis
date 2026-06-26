Goal: Add a narrow Phase 2 deterministic patch/rigid-body automation seed without claiming G1 closure.

Scope:
- Inspect existing Phase 2 artifact patterns.
- Add or review a small axial constant-strain patch test and rigid-body nullspace/free-translation test artifact.
- Keep the artifact honest: it may prove only a narrow axial/component patch and rigid-body automation seed, not general frame/shell/full-mesh G1.

Candidate files:
- src/structural_analysis/assembly/
- scripts/build_phase2_*patch*_artifacts.py or similarly named new builder
- tests/test_build_phase2_*patch*_artifacts.py
- scripts/verify_quality_gate.py if a new builder should be wired into full/release checks
- implementation/phase1/release_evidence/productization/phase2_*patch*_*.json

Verification criteria:
- Run the new builder and its --check mode.
- Run focused pytest for the new builder and verify_quality_gate if touched.
- Run ruff on changed Python files.
- The summary must keep g1_closure_claim=false and broad blockers visible.
- Output only Changed files, Test results, Failed tests, Core diff summary, Blockers.
