# Security policy

## Supported versions

The repository is a Developer Preview and does not currently designate a production-supported release line. Security fixes may target the current default branch and explicitly named preview tags only.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private models, customer data, signing material, or restricted benchmark data.

Use GitHub private vulnerability reporting when it is available for this repository. If that surface is unavailable, contact the repository owner privately through the contact method published on the owner's GitHub profile and include only the minimum information needed to establish a private channel.

A useful report includes:

- affected commit or tag;
- operating system and architecture;
- whether ROCm/HIP, a native library, the local web surface, or an imported model is involved;
- a minimal reproduction that contains no restricted data;
- expected and observed behavior;
- potential confidentiality, integrity, availability, or numerical-authority impact.

## Numerical and evidence integrity

Please treat the following as security-relevant integrity failures:

- a failed or non-converged run presented as an authoritative result;
- source, model, checkpoint, result, or evidence hash substitution;
- silent CPU fallback from a required HIP execution;
- unsafe native ABI ownership or memory behavior;
- untrusted report or project content causing code execution;
- signing-key, credential, or private-model leakage;
- a generated artifact being accepted against a different source epoch.

## Disclosure boundary

Receipt, hash, or provenance validation does not by itself grant product, design, hardware, external-V&V, or release authority. The repository owner will coordinate disclosure after a fix and reproduction path are available.
