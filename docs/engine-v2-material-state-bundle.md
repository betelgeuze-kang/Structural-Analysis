# Engine v2 MaterialStateBundle v1

## Purpose

`MaterialStateBundle` is a backend-neutral transport and lineage contract for
ordered integration-point state bytes. It closes a contract gap between the
existing displacement-oriented `StateIR` and bounded nonlinear material paths
that currently own separate axial, truss, section, and element accepted-state
types.

The bundle does **not** interpret a constitutive law and does not grant solver,
numerical-result, engineering-result, design, release, or commercial authority.

## Bindings

Every bundle binds:

- exact `ModelIR` content hash;
- exact `ExecutionPlan` hash;
- one exact solver `StateIR` hash;
- committed or trial role and epoch;
- parent bundle hash for every non-initial state;
- deterministic integration-point order;
- entity, integration-point, material type, and material schema identity;
- opaque immutable state bytes through byte length and SHA-256;
- per-entry constitutive parent data hash for every non-initial entry.

Manifests contain descriptors only. Raw state bytes remain separate artifacts
and can be checked with `validate_material_state_entry_bytes`.

## Lifecycle

```text
initial committed bundle (epoch 0)
    |
    | open_trial_material_state_bundle
    v
trial bundle (epoch n+1)
    |                     \
    | commit               \ rollback
    v                        v
committed bundle           exact original
(parent = trial hash)       accepted object
```

Opening a trial requires identical entry identity and order. Each trial entry is
parented by the corresponding accepted entry data hash. Commit retains the exact
trial bytes while binding a committed solver-state hash. Rollback returns the
same accepted object. Default trial and committed IDs include the direct parent
bundle digest rather than recursively embedding parent IDs, so they remain
within the stable-ID bound across long epoch chains.

## Fail-closed behavior

The contract rejects:

- mutable or empty byte artifacts;
- unknown manifest fields;
- integral floats in integer fields;
- stale or mismatched entry-parent hashes;
- non-contiguous or order-mismatched imported entry indices;
- entity, integration-point, material type, schema, or ordering drift;
- descriptor/byte length or hash mismatch;
- non-initial bundles without parents;
- trials opened from non-committed bundles;
- coherent authority-profile promotion;
- bundle, entry-content, or artifact tamper.

## Current boundary

The contract remains a direct module API. A separate bounded adapter now
projects the exact built-in RC fiber states from one validated stateful
fiber-frame checkpoint through the accepted/trial/committed bundle lifecycle.
That adapter is one-way: the existing checkpoint codec remains the restart
representation, and the caller supplies the ModelIR, ExecutionPlan, and solver
StateIR hashes. The adapter binds those values but does not prove semantic
equivalence between the Engine v2 model and the bounded frame problem.

The current surface still does not:

- extend `StateIR v1` or change existing hashes;
- adapt standalone `StatefulAxialAcceptedState`, two-bar truss, standalone RC
  fiber-section, or standalone fiber-beam states;
- provide a generalized material/section codec registry;
- prove that opaque bytes came from the declared constitutive law;
- connect material state to nonlinear `NumericalResultIR` or engineering recovery;
- define Viewer projection or AI training eligibility;
- close a public nonlinear product path or G1.

Future slices may add separately verified one-way adapters for the remaining
bounded state families, then bind this bundle to a public nonlinear analysis
and nonlinear result authority contract.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_material_state_bundle_v1.py
python3 -m ruff check \
  src/structural_analysis/engine_v2/contracts/material_state_bundle.py \
  tests/test_engine_v2_material_state_bundle_v1.py
```
