# Original solver failure inspection in RC design review

The full cyclic reinforcement observation retained a concrete line-search failure
inside the original result, while its comparison row only reported
`full_reference_blocked`. Workbench now provides an explicit original-failure
inspection button for failed rows with a stored result.

Inspection uses the existing verified download, checks the result self-hash and
schema, and extracts the last uncommitted attempt's recorded solver reason,
target, accepted-target count and rollback/parent-immutability flags. A claimed
exact rollback must bind identical accepted and parent checkpoint hashes.
Malformed diagnostics or changed original bytes invalidate the review. A result
without a blocked control step gives an unavailable message directing review to
verification/execution records; it does not invent a solver failure. Diagnostics
remain recorded observations and confer no physical or selection authority.

The existing report format, stored artifacts, solver and tolerances are unchanged.
This also supports historical comparisons through their verified result downloads.
No new solve, training fit or altered failure experiment was performed.

Validation:

- 25 design-contract tests pass (17.8 s), including synthetic diagnostic parsing,
  changed-byte rejection, contradictory rollback and mistyped flags.
- 13 design-browser tests pass (1.1 min), including unavailable failure detail,
  disabled candidate selection and original-byte corruption after initial review.
- TypeScript and `git diff --check` pass. Initial type checking identified an
  unsupported `Object.hasOwn`; the implementation uses the project's supported
  `Object.prototype.hasOwnProperty.call` form.
- The actual three-design output from numerical source `94302f49a` was opened
  at widths 1440 and 390. Each view made 26 reads and displayed the smaller-bars
  result's seven accepted targets, failed -0.0032 m target,
  `line_search_failed_to_reduce_residual`, exact rollback and immutable parent.
  Failed candidate selection stayed disabled. The diagnostic had no horizontal
  overflow, and the mobile screenshot was visually inspected.

The actual-output review used local Vite and Playwright route fulfillment with
original artifact bytes. It is not an actual authenticated service-mount or
production-hosting observation. The earlier two-of-three full-path outcome
remains incomplete; showing its diagnosis does not resolve convergence or
establish physical collapse, feasible reinforcement reduction or design approval.

Logs, desktop/mobile images, browser script and source patch are retained in
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-failure-review-uxr8v9fd`:
9 files, 72,584 bytes. The inventory was reread; SHA-256 is
`b26f7462da2954ca420df7f476997ba46cc4bb4aa0b37ae63cb89b4703e33511`.
The original numerical packet remains unchanged, linked by its separate
inventory in the [full-path observation](rc-reinforcement-full-path-20260913.md).
Full hosted validation and the broader roadmap remain open.
