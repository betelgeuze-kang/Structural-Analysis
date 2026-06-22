Goal: Audit the first Phase 1 core package/API slice for Structural Analysis Open Benchmark Developer Preview.

Scope:
- Do not change files.
- Inspect pyproject.toml and the planned src/structural_analysis package shape.
- Phase 1 target path:
  model = load_model("model.ifc")
  result = analyze(model, AnalysisConfig(...))
  report = validate(result, reference)
- Check whether a minimal first slice should include package discovery, CLI entry point, canonical model schema, units/coordinates, result provenance, input checksum, tolerance, convergence history, and explicit unsupported/degraded states.

Return only:
- missing API/package risks
- tests that should be added
- claim-boundary risks
- blockers
