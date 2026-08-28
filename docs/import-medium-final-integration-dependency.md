# Import and medium final hardening integration boundary

This tail combines the PR #288 import-health work and the PR #389 medium-scale
work on current main. It closes only the medium, IFC, MGT 9/10, MGT 10/10,
Native clean-install, and Workbench import-health boundaries changed here.

The `current-support-bundle` producer and its Workbench/frontend consumer are an
explicit follow-on dependency. They are intentionally not restacked or edited in
this tail because PR #394 owns that separately reviewed frontend/support and
distribution boundary. After that tail is approved and landed, integration must
preserve its strict JSON and lexical repository-containment checks and then rerun
the combined workflow-contract tests.

The evidence emitted here remains same-operator technical evidence. Scientific
validation, general Native product authority, rights or redistribution approval,
product legal approval, and release authority all remain false. A successful
handoff attestation records only the exact source/run/attempt and the exact
receipt bytes independently checked by the fresh hosted verifier.

The privileged verifier deliberately runs no checkout, setup, package install,
or repository code. Unprivileged producers hand off only an artifact ID, digest,
name, and a final exact file/hash seal. This is a point-in-time workflow boundary;
it does not claim protection against later filesystem mutation or grant any
authority beyond the sealed technical receipt.

`canonical/technical-evidence-handoff-pair.v1.schema.json` and
`scripts/verify_technical_evidence_handoff_pair.py` define the downstream
recombination contract. The validator accepts an authenticated API identity
record, the downloaded handoff and attestation archives, and the JSON output of
an independent `gh attestation verify` invocation. It checks strict JSON, safe
archive paths, archive and inner-file digests, the final seal, the lane-specific
technical subject, and the source/tree/workflow-blob/run/attempt/Sigstore subject
bindings. It does not query GitHub or perform cryptographic verification itself.

The final Current Main Evidence Index remains responsible for authenticating API
responses, invoking Sigstore verification with the declared policy, calling this
validator, and cataloguing both artifacts as one indivisible pair. Until that
consumer and its catalog use this contract, these producer artifacts do not close
Product State or release readiness.
