# Beam Exact-Decode Action Plan

## Plan Summary
- Scope: `beam .mcb exact-decode next-step planning only`
- Promotion target: `hint-guided preview-derived 3d candidate -> verified preview`
- Recommended order:
  1. `beam_node_xyz_slot_recovery`
  2. `beam_elem_connectivity_recovery`
  3. `beam_promotion_gate_recheck`

## Step 1. NODE xyz recovery
**Goal**
- Recover stable record-local `NODE` xyz semantics for the `951..1111` range.

**Why first**
- Without trustworthy xyz, connectivity evidence stays underdetermined.

**Expected evidence**
- Many more resolved xyz tuples than the current sparse hint path.
- A repeatable slot/record mapping rule.
- A node cloud that is materially denser than the current `5-point / 4-segment` preview.

**Promotion relevance**
- This step establishes whether beam can move beyond `hint-guided` at all.

## Step 2. ELEM connectivity recovery
**Goal**
- Recover trustworthy `ELEM` member references for `224..379` and bind them to recovered `NODE` ids.

**Why second**
- The current viewer blocker is explicit: `ELEM` still looks constant-filled and connectivity is not trustworthy.

**Expected evidence**
- Stable ELEM reference slots.
- Resolved member paths for a meaningful subset of the range.
- A topology-grounded preview that is driven by ELEM references rather than record-order polyline heuristics.

**Promotion relevance**
- Verified preview is not credible until connectivity is evidence-backed.

## Step 3. Promotion gate re-check
**Goal**
- Re-run decode + preview bridge and decide promotion only from regenerated evidence.

**Expected evidence**
- `geometry_preview_ready=true`
- blocker text about `constant-filled ELEM` disappears
- cross-check improves beyond `weak silhouette match`
- probe/adapter readiness rises above `table layout still uncertain`

## Promotion gate criteria
- Parser-side `geometry_preview_ready` must be true.
- `NODE` xyz must be justified by a repeatable decode rule.
- `ELEM` connectivity must be resolved from trustworthy node-reference semantics.
- The viewer must no longer describe connectivity as untrustworthy.
- Cross-check quality must improve beyond weak silhouette match.
- Adapter/probe readiness must move above the current uncertain state.

## Bottom line
We should not spend effort on changing beam promotion wording yet. The next useful work is still:
1. `NODE xyz recovery`
2. `ELEM connectivity recovery`
3. `promotion gate re-check`
