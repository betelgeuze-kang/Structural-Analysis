# OpenCode worker: commercial v1 scope freeze

Goal:
Extend the existing paid-pilot scope guard so commercial v1 supported scope and separate-validation exclusions are machine-readable and tested.

Scope:
- Edit only the paid-pilot scope guard script/tests/docs if needed.
- Do not touch `.env*`.
- Do not claim Limited Commercial, GA, legal approval, or external V&V closure.
- Keep unsupported/proxy/fallback states visible.

Candidate files:
- `scripts/build_paid_pilot_scope_guard_report.py`
- `tests/test_build_paid_pilot_scope_guard_report.py`
- `docs/pm-release-gate-milestones.md`
- `docs/release-limitation-manual.md`
- `README.md`
- `docs/github-documentation-status.md`

Verification criteria:
- Report includes supported commercial v1 families/workflows: frame, wall-frame, outrigger, truss; MIDAS/OpenSees/KDS interop; nonlinear static; bounded NDTHA; residual audit; reference comparison; reviewer package.
- Report includes separate-validation exclusions: rail/tunnel, special SSI, nonstandard contact, legal/authority approval automation, special construction stages.
- Missing supported scope or missing exclusions must block the guard.
- Existing constrained paid-pilot scope checks and prohibited claim checks must keep working.
- Add focused pytest coverage.
- Return only: Changed files, Test results, Failed tests, Core diff summary, Blockers.
