# Layered RC, isolated phases and restart integration

This integration joins the explicit pin/roller and layer-specific steel model
(PR585 ancestry) with isolated durable phases and the persisted payload cap
(PR597 ancestry). It resolves the backup-test conflict by retaining all axes:
legacy/layered pin-roller, inline/isolated, and uncapped/10 MiB cap. The v4
request schema accepts the same exact phase-policy contract as v3. Browser
preflight accepts a complete valid policy and still rejects unknown execution
extensions or malformed policy fields; retained artifact review additionally
checks the original numeric token spelling.

The nonlinear comparison uses the existing fourteen-target reversed path and
explicit 100-iteration/16-line-search policy with unchanged equilibrium,
increment and control tolerances. Synthetic 4/8 MPa steel strengths are solely
for exercising both constitutive laws; they are not physical specimen inputs.
The final native checkpoint has tensile damage above 0.03 and accumulated
plastic strain above 2e-4. Inline full, isolated full, and isolated restart
following target 11 produce exactly identical native checkpoint bytes. Each
chunk is freshly verified and all invocation ordinals are accounted. The
comparison runs current numerical code, without retained-output substitution.

This supports the interaction of nonlinear state, reversal, subprocess
reconstruction, checkpoint replay and durable admission. Existing default-policy
failure and finer-increment cases remain in the core matrix; successful extended
search does not replace their failure evidence or change solver defaults.

The eight backup combinations perform real calculation, checkpoint backup,
original process stop/reap, restored calculation, report generation and second
backup/reopen. They retain five reservations, unknown ordinal 3, original request
bytes, layer-aware quantities and the inherited cap. Operator stopping the
original remains necessary; no automatic cross-store fencing is claimed.

This remains synthetic software integration. Public-source geometry/material
admission, physical curve comparison, OS-wide resource enforcement and exact
final-main regression/Nightly/Product State are separate unfinished gates.

Browser evidence keeps parent API counters and isolated phase receipts separate.
Inline cases report one parent analysis and one verification per chunk. Isolated
cases report zero parent API calls and retain distinct phase records with child
PID, successful return and observed reaping. The fresh-worker barrier precedes
both kinds of execution. The fixture only accepts enumerated authored requests;
adding phase support does not make arbitrary test input an approved fixture.

A real browser-origin defect was found during integration: the phase transport
hashed the raw chunk config, while the child compared the typed API request
hash. Accepted browser normalization of `1.0` to `1` therefore caused child
transport rejection before calculation. Transport now derives the chunk hash
through the strict typed decoder, while preserving the distinct original durable
request hash and bytes. A real subprocess regression compares both spellings,
requires distinct durable identities, equal typed chunk identity and identical
result/native bytes, followed by fresh verification. No approximate numeric
comparison, rounding or mutation of the original request is introduced.
