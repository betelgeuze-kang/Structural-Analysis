# Recovery does not generalize to the second internal stop

The earlier parent-start TRF seed passed native acceptance at -61.943626 mm, and coordinate-only continuation reached -76.197662 mm. This follow-up retains the same original -40 mm material parent and tests the next failed internal target (-0.07619770050048828 m) and original -80 mm target, using either the last internally accepted coordinates or the failed terminal coordinates. The original material law and all native acceptance tolerances remain unchanged.

The four combinations are repeated in reverse order using the two separately recorded input sequences. All eight optimizers report success, but all eight native confirmations reject their proposed seeds. Thus optimizer convergence cannot be treated as structural acceptance, and success at the earlier internal target cannot be generalized to this target.

| Target | Start | Final native relative residual, both repeats |
| --- | --- | ---: |
| Internal -76.1977005 mm | Last accepted coordinates | 4.207861883973974e-7 |
| Internal -76.1977005 mm | Failed terminal coordinates | 4.1382225601440476e-7 |
| Original -80 mm | Last accepted coordinates | 0.09351428256722744 |
| Original -80 mm | Failed terminal coordinates | 0.007868294543828602 |

Every native run returns `line_search_failed_to_reduce_residual`. All numerical outcomes and returned checkpoint hashes agree across repetitions, and the original parent remains unchanged. The experiment retains 386 optimizer callback assemblies plus eight native calls and 22 Newton iterations/linear solves. Raw clocks and seeds are in the summary; no qualified speed ratio, complete path, physical branch selection or independent validation is claimed.

This negative result prevents promotion of a generic TRF restart based on the earlier isolated success. Further work needs a bounded method justified against the full original history, rather than treating additional start guesses as accepted design evidence. The original 80 mm case remains open; no production recovery or material parameter is changed.

## Evidence

Frozen source: `a94d82d1ed60317d36bce7f5af67730576f9ff61`. Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-76mm-trf-q8d367dk`. Inventory SHA-256: `e270f70122af8ec9150027a154a3e280c8b7b1e77a3a9830028db8de15f7f92f`. Source/input/seed-packet hashes were checked before execution, and all output inventory entries reread. The packet retains its fixed plan, driver, eight full native results, proposals, callback counts and timing records. [Machine-readable observations](rc-76mm-recovery-check-20260921.summary.json).
