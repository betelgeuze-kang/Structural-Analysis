# Noncommitting initial residual observer

`observe_rc_control_initial_residuals` evaluates one to sixteen explicit named seeds against a shared accepted checkpoint and control target. It uses the displacement-control adapter's coordinate conversion and actual residual/tangent assembly. The relative residual is computed by the same normalization as Newton. The report records the parent hash, target, coordinate scale, tolerances, input and solver coordinates, residuals, control error, per-attempt time and total time.

All adapters validate candidate inputs before assembly begins. A coordinate-conversion failure records zero assembly attempts; an assembly failure records an attempted assembly. Both retain an error and unknown-work flag and stop subsequent candidates. Successful and failed observations check that the parent remains byte-identical. An unexpected parent mutation raises an error rather than returning a successful report.

The observer performs no Newton solve, commits no checkpoint, selects no candidate and changes no runtime policy. Its residual-gate field describes only the initial normalized residual condition, not solver acceptance. Each observation currently builds a full tangent as well as the residual; its measured cost must be included before proposing any online gate. A lower residual does not establish faster convergence or independent physical accuracy.

Focused validation uses a nonzero accepted parent and two distinct initial guesses in both binary64 and twofold-increment coordinates. Each observed residual vector and normalized residual exactly matches the corresponding first Newton observation. Further tests cover all-input preflight, retained assembly failures and coordinate failures without fictitious assembly counts. The development workflow includes this test module. The observer and complete workflow-contract suite pass 23 tests; Ruff and whitespace checks pass.

During development, the initial retained-coordinate test omitted the required exact-rational strain profile and was rejected by existing validation. The test now uses that required profile; no solver tolerance or validation was relaxed. Earlier implementation testing also caught and corrected an incorrect observation field name before this change was committed.

The next research step is a prespecified development-only comparison that includes the extra observation cost and complete subsequent solve cost. Existing v6 measurements still select secant. This helper is not an online acceleration result or a completion of the broader roadmap.
