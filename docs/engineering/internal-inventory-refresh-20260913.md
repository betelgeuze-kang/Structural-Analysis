# Current-source inventory and bounded material artifact refresh

Update: the five protected material summaries were subsequently restored to the
PR base; their fresh local results are retained, and CI now regenerates them in
its ephemeral runner. See [the CI boundary correction](package-preparation-ci-boundary-20260913.md).

This refresh resolves two diagnosed stale-data groups from the failed full Python
baseline at `df60b7d3913f8fe095788f07ace95302d02f6cd3`. It was calculated from
parent source `c60b83ce3e302770a8d3cfa1247bedd1254f2ccd`. The full suite has not
been rerun, and remaining failures retain their original unresolved status.

## Historical source-quarry inventory

The 480-row inventory for closed, unmerged PRs 77 and 78 was rebuilt from its
digest-pinned historical API rows and the current Git tree. Fourteen current
blob identities in PR 78 had changed. Only those identities and the aggregate
inventory digest changed. All 71 present and 409 superseded classifications,
replacement paths, owner retirement policy and authority boundaries remain
unchanged. No historical branch was merged or reintroduced. This was an offline
rebuild; no new live GitHub API verification is claimed.

All nine source-quarry tests passed, including deterministic rebuild, policy
tampering, historical API digest and API drift rejection. These tests cover the
four inventory failures observed in the baseline.

## Five bounded internal material/continuation records

The builders for steel material, bilinear link, composite section, concrete
damage and adaptive Newton continuation were executed from current code. Their
fresh result objects exactly matched the retained result objects. After excluding
the existing volatile generation timestamp and source-commit fields, each summary
differed only in the input checksum of
`src/structural_analysis/solvers/nonlinear/newton.py`.

The freshly generated summaries now bind that current source. No result value,
gate, tolerance, blocker or authority claim was changed. All 17 tests across the
five builder modules passed, including current generated-artifact checks. This
addresses five additional stale-summary failures; it does not turn the old failed
full-suite report into a pass.

The material receipts remain bounded internal computational checks. Published
experimental validation, general material breadth, independent operator evidence,
hardware qualification and release authority remain separate requirements.

Local reproduction records are retained under
`/tmp/structural-quarry-refresh-jp239qcy` and
`/tmp/structural-phase2-refresh-gbssx_y1`; focused JUnit outputs are
`/tmp/structural-quarry-refresh-tests.xml` and
`/tmp/structural-phase2-refresh-tests.xml`.
