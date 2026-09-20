# Why the fixed inner gates decline beneficial validation rows

A read-only post-hoc observer of the [audited forty-fit evaluation](rc-inner-gate-evaluation-results-20260920.md) rechecks pinned policies, validation-row hashes and every saved decision. It evaluates the fixed score algebra and existing range/positive-training guards without fitting, changing thresholds or accessing reserved cases.

| Fixed variant | Outside training bounds | Below threshold within bounds | Proposed |
| --- | ---: | ---: | ---: |
| Prefix cost | 346 | 314 | 0 |
| Material cost | 346 | 312 | 2 |

For **both** variants, the 32 measured-positive validation decisions split into **29 within bounds but below threshold** and **3 outside bounds**. No gate lacks positive training rows. The two material proposals are the previously audited false positives. Thus, even a perfect discriminator retaining the existing range guard could consider 29 of these positives; the dominant observed rejection of positives occurs at the learned score, not solely at range admission. This is a count of eligibility, not evidence that a better discriminator exists or would yield net runtime benefit.

These are 660 overlapping decisions per variant from 165 retained development samples. Do not reinterpret them as independent projects, tune a new threshold on them and call it untouched validation, or promote a policy from this diagnosis. The findings do not establish whether the principal remaining issue is feature representation, policy-dependent labels, cost noise, model class or inadequate independent cases.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-inner-gate-decisions-ga1a53qb`.
Inventory SHA-256: `9fca7d6451018ba6cd9ba34292b25790e0c18aeb669562f1baf2e7027aa1793d`.
Input evaluation inventory: `69dd07e07063ba88f8227bddc57ffcd02bc1de100e0adc335a35caea8faf0afb`.
Observer wall time through report assembly: 0.135376912 seconds; zero new fits and zero structural solves. The large material-witness read was concurrently active, so this diagnostic time is not an isolated performance benchmark.
