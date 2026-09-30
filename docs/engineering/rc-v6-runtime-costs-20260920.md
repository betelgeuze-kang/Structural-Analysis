# Attribution of the completed v6 runtime cost

The post-hoc decomposition authenticates the completed v6 packet and all consumed reports/step outputs against inventory `19d600900d8972263446acb7a899c14687eb61e8307d7b4d8f62f1ef3c7f9bcf`. It reuses the unchanged, tested disjoint timing decomposition from the frozen source, explicitly rebinding its input inventory to this new packet. No fit or numerical solve was executed.

The table averages proposal-minus-secant time over the nine cases with actual proposals for each ridge. Each case retains all three repeats. Values are milliseconds per full path. Static model-gate time outside the path is excluded here; the original selection score continues to account for its declared costs.

| Ridge | Solver invocations | Response recovery | Proposal computation | Material capture | Unattributed remainder |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10,000 | +90.522 | +7.363 | +13.934 | +49.350 | -1.492 |
| 1,000,000 | +72.649 | +1.034 | +13.819 | +49.144 | +2.469 |

Every arm has nonnegative components that add back exactly to its recorded path time. A negative difference in the final column is not a negative duration. The residual category is not relabeled as I/O without measurement.

Across the nine active cases' 108 controlled targets, ridge 10,000 adds 24 Newton iterations and 20 recorded line-search trials; ridge 1,000,000 adds nine iterations and 14 trials. These counts are for one repeated target roster, not the sum of all three runs. All three repeats agree on these work counts and parent relationships. Recorded line-search trials do not constitute separately timed assemblies.

Only 19 of 108 corresponding target pairs retain identical parent hashes for each ridge. Later step differences therefore describe complete strategies rather than interventions at the same state. They cannot be spliced into switching labels or an oracle full-path speedup.

The consistent proposal-plus-material-capture overhead is about 63 ms. Even hypothetically removing that entire overhead would leave positive mean invocation-time differences. Such removal has not been implemented or measured. The next warm-start improvement must reduce actual nonlinear solver work as well as feature/capture cost; preprocessing correctness alone has not achieved that. The reference solver and unchanged acceptance criteria remain authoritative.

The diagnostic is descriptive attribution, not a causal proof that extra Newton or line-search counts explain all additional elapsed time. Cases with only fallback remain in the complete 30-case diagnostic and in the original selection score; they were omitted only from this explicitly labeled active-case table.

Exact packet and diagnostic inventory identities, all case/repetition-derived work counts and component times are retained in [the summary](rc-v6-runtime-costs-20260920.summary.json). No model promotion, independent validation or release credit is claimed.
