# Cursor worker slice: Developer Preview scope parity

Goal:
- Verify whether Developer Preview included/excluded scope is displayed consistently across README, GUI, and readiness report surfaces.

Scope:
- Authoritative source:
  - `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`
- Candidate display surfaces:
  - `README.md`
  - `implementation/phase1/release_evidence/productization/developer_preview_readiness.md`
  - `src/App.tsx`
- Candidate tests:
  - Search existing tests around Developer Preview readiness and App resource cards before adding new ones.

Constraints:
- Do not promote readiness or remove true blockers.
- Do not rewrite generated JSON by hand.
- Keep Developer Preview distinct from future Commercial Release blockers.
- Keep customer shadow, license/legal approval, commercial SLA, 30-run CI streak, and external approval receipts visible as future Commercial Release blockers, not Developer Preview blockers.

Verification:
- Report whether the same included/excluded scope terms are visible in README, GUI card text, and readiness markdown/report.
- If a narrow code or doc change is needed, make it and run focused tests/checks.
- Summarize changed files, tests, and any remaining blocker.
