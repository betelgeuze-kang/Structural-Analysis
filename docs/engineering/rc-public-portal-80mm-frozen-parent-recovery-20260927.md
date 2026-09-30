# Public 80 mm RC portal: bounded frozen-parent recovery observation

The [direct 80 mm public request](rc-public-portal-40-80mm-20260927.md) was blocked at its first −40 mm target. This follow-up ran an **off-product** failure-triggered adaptive frozen-parent continuation. It used the unchanged two-fixed-endpoint model and derived v3 80 mm request; it did not edit the accepted public API, targets, supports, constant roof loads, N4 reference load, or solver configuration.

The runner is [`scripts/run_rc_public_portal_80mm_recovery.py`](../../scripts/run_rc_public_portal_80mm_recovery.py). It pins the original model bytes (SHA-256 `6f8eec155f5fcf2f9ae942c021a8692e79ae1efd0d1b98342f8aea0b642d0ed6`) and derived 80 mm request bytes (SHA-256 `abf8d1d84a6b05af107730494ae5440deb305ceae123b91ceb5c92eb5feea782`), copies both into a new output packet, and invokes the existing research comparison runner. Its four arms are reference, secant, frozen-parent proposal, and fresh reference. A failed native target is retained before any recovery trial. Each intermediate trial uses the same immutable accepted material parent; only numerical coordinates become a seed. The original native solver then confirms a proposed target. Failed stages cannot become the accepted checkpoint.

The run from checkout HEAD `728e67a40e38ff3359dbc57676bec1533dc00936` wrote a local packet at `/tmp/rc-public-portal-80mm-frozen-parent-source-bound-728e67a40e38`. Its source revision field is **not** an attestation of the working tree. `comparison.json` has report hash `sha256:775000563dcd248108a082e77a51bd7f5cfa3ac1b15811335166c6c7198c4988`. The wrapper checked the entire stored comparison report against its self-hash, pinned request, canonical model checksum, two-fixed-endpoint compiler profile, and reported checkout HEAD; the copied source inputs remained byte-identical. It separately checked byte lengths, hashes, parents, and rollback records for **51 continuation trial artifacts**, plus parent and rollback records for **3 direct native step files**. The direct step files do not have separate byte-length/hash bindings in this audit. The packet is local, not hosted evidence.

| Arm | Accepted lateral targets | Result |
| --- | ---: | --- |
| Reference | 0/3 | Direct −40 mm attempt blocked |
| Secant | 0/3 | Direct −40 mm attempt blocked; no seed with only preload history |
| Frozen-parent proposal | 1/3 | −40 mm confirmed by native solve; −80 mm blocked; +40 mm unattempted |
| Fresh reference | 0/3 | Direct −40 mm attempt blocked again |

In the proposal arm, the original unseeded −40 mm attempt failed after **5 known Newton iterations/linear solves** and rolled back exactly to preload checkpoint `sha256:76b0d0ba03423f6e5fd5410454a2452f807035be222d7a12a7c88299e82cd240`. Sixteen frozen-parent trial calls then produced a seed; a separate native call committed −40 mm in one solve. That confirmation's accepted checkpoint became the parent for the next requested target. At −80 mm, the direct native attempt failed after 11 solves and rolled back exactly. Thirty-five further frozen-parent trials stopped at `minimum_fraction_increment`; the last trial target was about −61.0963 mm and was itself rejected. Those trial checkpoints were never adopted. The +40 mm reversal was not run because −80 mm remained blocked. A rejected trial target near −61 mm is a numerical observation, not a measured physical capacity.

The predeclared upper bound was 220 native calls across all four arms, including at most 64 continuation trials per requested target. The completed packet records **61 attempted native calls, 295 known Newton iterations, 295 known linear solves, and zero unknown-work attempts**. Of these, 51 calls and 255 solves were recovery trials; the other 10 calls and 40 solves cover all four preloads, direct attempts, and the native −40 mm confirmation. The enclosing benchmark call, artifact audit, and outcome classification took about 11.98 seconds wall/process CPU in this one local run; nested stage and path timings are not summed or used as a speed ratio. The failed original attempt and both blocked recovery paths remain in the denominator.

The proposal arm's single accepted −40 mm response passed the research runner's original-transition reassembly. It does **not** establish the full 80 mm public path: no arm accepted all three targets, `reference_repeat_exact=false`, and there is no fresh-source validation of a completed 80 mm public result. The observation establishes one bounded software recovery and a further numerical failure. It is not independent physical validation, design approval, or performance evidence.

Reproduce from this checkout with a new output directory:

```sh
PYTHONPATH=src python3 scripts/run_rc_public_portal_80mm_recovery.py \
  --output-directory /tmp/rc-public-portal-80mm-frozen-parent-new
PYTHONPATH=src python3 -m pytest -q tests/test_run_rc_public_portal_80mm_recovery.py
```
