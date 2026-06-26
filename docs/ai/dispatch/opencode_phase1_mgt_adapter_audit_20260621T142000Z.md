Goal: Audit the next Phase 1 thin-adapter slice for the installable structural_analysis package.

Scope:
- Do not change files.
- Inspect existing MIDAS/MGT parsing code, especially implementation/phase1/parse_midas_mgt_to_json_npz.py and tests around MIDAS section/load metadata.
- Inspect the new src/structural_analysis core API enough to identify the safest minimal adapter boundary.
- Focus on a thin MGT adapter that maps parser-visible entities into CanonicalModel without claiming solver readiness.

Return only:
- best candidate parser functions/files
- minimal fields the adapter can map safely
- unsupported/warning claim-boundary risks
- focused tests that should be added
- blockers
