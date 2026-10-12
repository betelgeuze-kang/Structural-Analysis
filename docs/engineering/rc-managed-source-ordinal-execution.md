# Managed complete source-ordinal RC execution

The v8 operation `rc_corotational_ordinal_history` retains one immutable complete
source plan, including repeated control readings and changes in independent
axial load. Source ordinals measure progress; material epochs measure mechanical
commits. A held source row advances progress only after accepted equilibrium and
the control observation are verified without committing material state.

Admission checks the full source and row hashes, ordered source indices, explicit
linear observation, supported model, authored solver configuration, numerical
genesis, isolated phase deadlines, and separate production and verification
budgets. Observed force values are a separate complete reference vector. They
never become model loads, fitted parameters, or evidence of physical accuracy.

`independent_axial_load_role = source_total_dead_global` is required. An explicit
signed translational pattern maps each source `axial_load_kn` to global loads.
Any nonzero fixed or proportional baseline load on a patterned degree of freedom
is rejected. This prevents applying a published total axial load twice or making
it depend on the lateral load factor. Loads on other degrees of freedom retain
their existing semantics; no baseline value is silently subtracted.

## Ownership and cost

The external shared execution authority owns both API reservations and immutable
solver credit grants. A grant binds the original request, full source context,
API ordinal, worker lease and authority generation, attached checkpoint hash,
native input hash, source cursor, phase, ceiling, and record window. The service
compares the attached prefix before committing a grant. A worker holds the
managed guard and per-job permit through child termination and reaping.

Each isolated phase reserves its full solver ceiling before launch. A failure or
missing outcome leaves that ceiling spent. Unused credits are not refunded.
Production and fresh verification reserve separately. Verification repeats only
the exact suffix from the same attached prefix, using identical limits; it does
not reconstruct the numerical source prefix on every call. Zero solver credits
are authorized only for a bounded suffix consisting entirely of already accepted
authored holds. Uncertified first rows and pending intermediate targets require
positive credits.

The immutable native whole-path attempt cap is separate from external reserved
credits. Assembly attempts, hold checks, resume checks, linear solves, phase
timing, and unknown reserved work remain visible. Per-entry record and solver
limits are at most 255. The public model and request/continuation/result bounds
are checked before compilation or transport; they are admission and transport
bounds, not hard operating-system memory guarantees.

## Saved artifacts and reports

Accepted durable receipts bind the original recorded production and verification
outcomes and external grants. Self-hashes detect corruption; they cannot grant
authority to a substituted prefix. Checkpoint writes and completion preserve the
attached receipt prefix and compare its exact identity. Restoring an older store
cannot lower external spend, replay a consumed grant, or make unknown work free.

Pure historical decoding uses the source identity retained in authenticated
original native artifacts. It does not fingerprint current code or run a solver.
This permits saved-artifact inspection after a source update without qualifying
that update. New numerical entries always check current source identity.

The complete report preserves every authored source row and observed force.
Accepted endpoint samples retain achieved observation, load factor, hold/commit
kind, and mechanical identity. All intermediate, failed, and nodal output events
remain in immutable original window outcomes referenced by content hash. A
generic report does not guess the scalar force convention of a physical test.

`authored_virgin_zero_reference` describes numerical initialization. It is not an
experimental tare or measured preload. Software fixture passes, owner custody,
successful restoration, and a report do not establish specimen equivalence,
independent physical validation, design approval, or release qualification.

The existing v6/v7 operation retains its independent input limits and semantics.
