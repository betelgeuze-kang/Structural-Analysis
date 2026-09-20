# RC search review capture budget after hosted timeout

At exact source `4f232fdfaaef47e59559fc92c14dbdcc5297b942`, frontend job
106075934685 in run 35509925226 ended with **813 passed / 1 failed (18.7 min)**.
The failed case was the 390px RC search strategy review, original-design review,
full-cost display and exact-download test. The original result remains failed.

The retained artifact 10605865868 contains its Playwright trace. Archive SHA-256:
`20a926cecd4b8893c63441ccb7eab4fa1add446debb7675f3137a72faa74dbf0`.
The trace records 191 completed expectations (including request header checks),
none with assertion errors. All twelve original-byte downloads and the final
width bound check finish before the test enters the panel screenshot call at
916355.428 ms. The test-wide 30-second timeout is then reported at about
918667 ms, while capture remains pending. This identifies where the time budget
expired, not a general proof that browser performance is adequate.

The desktop/mobile instances of this one multi-download scenario now have a
60-second test budget. All assertions, twelve byte comparisons, viewport checks
and final captures remain intact. No global timeout, retry or product code
changes. Other tests retain their previous budgets.

The local default Node 20.19.0 attempt was rejected by the trusted-runtime check
before any browser test. The official Node 24.20.0 archive and executable were
then checked against the repository's pinned hashes. The production runner
completed TypeScript/Vite build, viewer delivery and both scoped desktop/mobile
browser tests: **2 passed in 31.0 seconds**. This targeted success does not
replace a new complete hosted run or establish user-facing speedup.
