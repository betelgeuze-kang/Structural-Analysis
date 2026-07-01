# G1 Load-Dependent Near-Null / Geometric-Softening Comparison

- `summary_line`: `G1 load-dependent near-null/geometric-softening comparison: BLOCKED | load_response_ready=True | near_null_packets_ready=False | geometric_softening_signal=active_secondary`
- `contract_pass`: `False`
- `promotes_g1_closure`: `False`
- `geometric_softening_signal`: `active_secondary`
- `near_null_packet_comparison_ready`: `False`

## Load Response Segments
- `0.1` -> `0.2`: translation_ratio=`2.1798886013760526`, drift_ratio=`2.1739369057854447`, superlinear_translation=`True`, superlinear_drift=`True`
- `0.2` -> `0.4`: translation_ratio=`2.665222496999357`, drift_ratio=`2.6073590072318398`, superlinear_translation=`True`, superlinear_drift=`True`
- `0.1` -> `0.4`: translation_ratio=`5.809888141339919`, drift_ratio=`5.668233972453394`, superlinear_translation=`True`, superlinear_drift=`True`

## Blockers
- `load_dependent_near_null_packet_missing:0.2`
- `load_dependent_near_null_packet_missing:0.4`

## Claim Boundary

This receipt compares non-promoting F2h load-response trends and optional load-dependent near-null packets. It does not close G1, prove full-load 1.0, or replace the consistent residual/Jacobian Newton and production ROCm/HIP gates.
