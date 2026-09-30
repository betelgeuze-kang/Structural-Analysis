# Fixed full-path v6 runtime comparison

The fixed ten-fit correction-error comparison worsened SSE in every excluded aggregate. Because correction error and nonlinear solve cost are different objectives, the next experiment directly evaluates full paths rather than treating that error change as a runtime verdict.

Use the original pooled campaign with `--fit-solver svd-ridge-exact-constant-centering.v1`. All 165 original training rows, five connected geometry/history groups, 15 development cases, two fixed ridges (10,000 and 1,000,000), three counterbalanced repetitions, secant fallback and static model abstention remain unchanged. Every withheld fit uses exactly the complementary 132 rows. The two reserved cases remain unexecuted. No new label generation, ridge search, altered tolerance or threshold change is permitted.

The campaign plans 90 comparisons and 360 complete paths, with at most 31 selection fits and 6,840 core calls. It accounts for fitting, historical label generation, proposal/guard costs, verification and whole-path execution. The existing 1% minimum improvement criterion applies. A selected candidate would still not constitute independent project validation or automatic promotion.

The driver now records the requested method; the retained-output auditor binds the method across the source declaration, selection plan, pooled metadata policy, every fold and any selected refit. Historical plans without a method field mean the old SVD method and remain auditable. Unknown, missing or mixed policy methods fail verification. Relevant diagnostic/audit tests: 142 passed in 7.08 seconds; Ruff passed.

Freeze this implementation before execution, preserve failed and partial outputs, and inspect process handles before restarting. Run no concurrent numerical timing campaign. Cross-revision historical times are descriptive; the decisive comparison is v6 versus secant within this new source and workload. Original full-history and work-accounting audits must pass before interpreting any score. All five roadmap requirements remain open.
