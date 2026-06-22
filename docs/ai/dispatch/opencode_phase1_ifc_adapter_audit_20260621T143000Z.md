Goal: Audit the next Phase 1 IFC thin-adapter slice for the installable structural_analysis package.

Scope:
- Do not change files.
- Inspect existing IFC-related code and tests, especially implementation/phase1/interoperability_gateway.py, implementation/phase1/convert_ifc_private_corpus_to_structural_graph.py, and IFC tests.
- Inspect src/structural_analysis core API enough to identify the safest minimal adapter boundary.
- Focus on load_model("model.ifc") returning a CanonicalModel without claiming solver-ready IFC reconstruction.

Return only:
- best candidate parser functions/files
- minimal IFC fields the adapter can map safely
- unsupported/warning claim-boundary risks
- focused tests that should be added
- blockers
