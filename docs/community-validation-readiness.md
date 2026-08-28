# Community validation readiness

## Current state

The repository is publicly visible but the default license grants no permission to use, modify, or redistribute the software. Community execution or contribution therefore requires a separate applicable permission until the copyright holder adopts another policy.

This document and the reproduction receipt format prepare a future validation surface. They do not change `LICENSE` and do not approve any dataset, commercial use, external operator, or release.

## Evidence levels

| Level | Meaning | May be self-authored? | Authority created automatically? |
|---|---|---:|---:|
| Analytical verification | Comparison with an analytical or manufactured reference | Yes | No |
| Internal differential | Comparison between independently implemented internal paths | Yes | No |
| Cross-code | Fresh comparison with another solver using semantically equivalent input | Operator may be internal | No |
| Experimental validation | Comparison with a licensed holdout specimen or dataset | Calibration and validation must be separated | No |
| Blind prediction | Parameters frozen before hidden result disclosure | No hidden-result access | No |
| Community reproduction | Another operator reproduces a declared source/model/result contract | Must be independent for credit | No |
| Public support | Capability is explicitly promoted for users | No | Requires separate product gate |

## Receipt workflow

1. Obtain permission to execute the software and use every input dataset.
2. Check out the exact 40-character source commit.
3. Record SHA-256 identities for the built engine artifact, execution plan, model, and result.
4. Record the command, backend, environment, fallback count, regularization count, runtime, and peak memory.
5. For HIP, record the ROCm version, GPU architecture, and stable device UUID.
6. An operator may record a claimed identity, time, and signature reference in the
   v1 receipt. These self-declared fields do not verify identity or signature
   authenticity and cannot receive independent-reproduction credit.
7. Validate the receipt:

```bash
python scripts/validate_community_reproduction_receipt.py \
  path/to/receipt.json \
  --require-independent \
  --out path/to/validation-report.json
```

A schema-valid v1 receipt records one claimed reproduction. Because v1 attaches no
separately verifiable operator-identity or cryptographic-signature receipt,
`--require-independent` fails closed and community-reproduction credit remains
false even when the declaration fields are populated. A future authority-bearing
contract must define and verify those external bytes separately. This validation
does not grant numerical correctness, external V&V level, hardware promotion,
design authority, public support, or release authority.

## Leakage controls for papers and competitions

Calibration, development regression, locked validation, blind competition, and community reproduction datasets must be separate. Split by specimen, study, institution, structural archetype, loading protocol, and material range rather than by time step or load step within one specimen.

Locked validation and blind-prediction rows must bind the parameter freeze to a SHA-256 snapshot, not only a timestamp. A dataset license that does not allow training cannot be assigned to calibration or development-regression roles.

## Licensing decision still required

Before ordinary external code contributions or redistribution are accepted, the copyright holder must decide among a permissive, file-level copyleft, network-copyleft/dual-license, or source-available policy and complete a third-party material review. This document does not choose that policy.
