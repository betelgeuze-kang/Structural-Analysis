# Beam .mcb Exact-Decode Feasibility

## Recommendation
- Promote today: `no`
- Decision: `do_not_promote`
- Summary: We do **not** have enough evidence to move beam from `hint-guided preview` to `verified preview` today.

## What is working
- `MCVL` container detection is stable.
- `NODE` and `ELEM` rows are present in the extracted table directory.
- The current pipeline consistently produces a hint-guided preview (`5` points / `4` segments) and surfaces it in the viewer.

## Why promotion is blocked
1. Parser output is still `PASS_TABLE_DIRECTORY_ONLY`, not a verified geometry preview.
2. `NODE` records do not expose enough direct xyz evidence.
   - `146/160` records have `0` plausible values.
   - `13/160` have only `1` plausible value.
   - `1/160` has `2` plausible values.
   - `0/160` have `3+` plausible values.
3. Viewer truth already says the key issue directly:
   - `ELEM range still looks constant-filled, so connectivity decode is not trustworthy yet.`
4. Cross-check quality is still only `weak silhouette match (50.6)`.
5. Archive adapter/probe artifacts still report `probe_ready=false` / `table layout still uncertain`.

## Exact blockers
- Recover record-local `NODE` xyz, not just sparse scalar hints.
- Decode trustworthy `ELEM` member references from the hinted range.
- Produce a parser-level preview with `geometry_preview_ready=true`.
- Improve beam cross-check beyond weak silhouette match.
- Raise adapter/probe readiness above the current uncertain state.

## Bottom line
Beam is still an **honest diagnostic candidate**, not a verified preview. The current evidence supports keeping it at `hint-guided preview-derived 3d candidate` until `NODE` xyz and `ELEM` connectivity are both decoded with stronger proof.
