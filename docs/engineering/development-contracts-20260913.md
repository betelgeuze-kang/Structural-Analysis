# Current-source development contracts

Source `f8f2f30fab7e6a56b2ff632c7461691c20d89c37` passes all **1,065** tests
in the committed repository workflow's development-contract roster locally:
zero failures, errors or skips, 672.81 seconds. The JUnit totals and terminal
exit zero agree. The checkout is clean before and after execution.

This roster covers RC learning/splits, runtime selection, work accounting,
candidate costs and HTTP consumers, public-data source boundaries, workflow
contracts and durable failure/job diagnostics. It includes the previously
corrected failed-work expectations and both CI diagnostic-context producers.
It is not the complete repository suite or a hosted-CI pass.

The first attempt omitted an explicit local source path and the existing editable
installation resolved `/home/betelgeuze/건축구조분석/src` instead. That attempt
terminated with 40 collection errors in 6.60 seconds. Its log and XML are retained.
After confirming termination, the second attempt selected this worktree's `src`
with PYTHONPATH and fixed Haswell/single-thread BLAS settings, preserving the
repository environment. Python is 3.10.12, NumPy 1.26.4 and SciPy 1.12.0.
This matches the workflow's numerical-library pins but is still a local runtime.

The [receipt](development-contracts-20260913.json) records source/tree identity,
command, both execution logs and XML byte hashes, and immutable packet location.
No tests were deselected after the first failure and no source edits occurred
during the corrected run. Timings are test execution costs, not product speedups.

External comparison preparation, learned net benefit, independent physical
verification and the full roadmap remain open. No protected receipts changed.
