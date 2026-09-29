# Alternate numerical seed at the compression-peak witness

The frozen original source `a94d82d1ed60317d36bce7f5af67730576f9ff61` was used for two repeated orderings of four bounded trust-region experiments: original parent versus failed terminal coordinates, at the failed internal target and at the original -80 mm target. The material parent and all native acceptance tolerances remain unchanged. Each optimizer is limited to 100 function evaluations; all residual and Jacobian callback assemblies are counted. Optimizer success never confers acceptance.

At the internal -0.0619436264038086 m target, the parent-start proposal is accepted by the original Newton solver in both repetitions with relative residual 1.4703497678662339e-13 and identical checkpoints. The failed-terminal start remains rejected. Both starts at -80 mm remain rejected, even though the optimizer reports success. All eight optimizer runs use 424 callback assemblies; their eight native confirmations use 10 Newton iterations/linear solves. This demonstrates one alternative accepted internal solution, not a complete history or selection of the physically correct branch.

## Continuing from the recovered coordinates

A separate predeclared experiment takes only the accepted internal solution's coordinates, retaining the original -40 mm material parent for every trial. It uses the existing bounded adaptive fraction schedule: maximum increment 1/16, minimum 2^-20 and 64-call budget. Both repetitions follow identical outcomes and checkpoint hashes.

Each stops after 42 native trials at `minimum_fraction_increment`. The last accepted internal target is -0.076197662353515633 m; the final attempted target is -0.076197700500488283 m, relative residual 7.758085563464683e-07. The -80 mm original target remains unaccepted. The successful recovered seed moves the internal stopping point, but does not complete the original history. No intermediate material checkpoint is adopted in this continuation and no policy/default changes.

Completed continuation measurements retain 84 native calls and 474 Newton iterations/linear solves. Seed-generation work is excluded from that packet's timings and is reported separately above; no combined speed ratio is claimed. A failed driver attempt is also retained: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-80mm-recovered-continuation-n5iccuym` contains 42 additional native calls and 237 Newton iterations/linear solves before variable shadowing stopped the driver before repeat 1. The driver was corrected and both repetitions rerun in a new packet. Failed work is not erased or credited as a completed repeat.

## Evidence

TRF packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-80mm-trf-q2j6am_e`, inventory SHA-256 `da2efd54b660aa292aa5b8db7eece9af71a3101e4c196abc53f122efd67bfec6`.

Completed continuation packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-80mm-recovered-continuation-v6krseoc`, inventory SHA-256 `8fb2de11fbd8c5ea36706345fac9dd86cad8b43abdb298d54c905b0cb9b4cc85`.

Interrupted driver packet inventory SHA-256: `e5c9e2e4ffaf6b08c8a6c78d82e3f6dcd672d0a8e66fc8c68883731c0061cbba`. Each inventory entry was reread. Original input and source hashes were checked before execution; full trial records remain available. [Machine-readable observations](rc-80mm-alternate-seed-20260921.summary.json) retain all unsuccessful cases and costs.

These experiments distinguish a locally trapped iteration from absence of any accepted internal solution. They do not prove global uniqueness, physical branch validity, full-path completion, independent validation or acceleration. Further bounded recovery must be tested through the original complete history before product integration.
