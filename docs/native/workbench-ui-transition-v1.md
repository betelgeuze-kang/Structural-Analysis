# Native Workbench UI transition v1

This contract keeps the React/TypeScript/JavaScript surface visible while product authority moves
to `structural-workbench`. It is a C5 transition inventory, not a C6 removal receipt.

## Native authority now present

The bounded fixed-guided ModelIR or normalized-MGT NDTHA profile runs
`Import -> Validate -> Run -> Resume -> Compare -> Report` without Python, Node, a browser, a CLI
subprocess, or an external renderer. The same Rust binary now also provides:

- `inspect`: a deterministic self-hashed operator view over verified stage, ResultIR, backend,
  comparison, and PDF receipts;
- `review`: one immutable explicit human disposition bound to the exact session, ResultIR,
  comparison IR, and PDF. Solver completion or comparison success never infers this decision;
- `export`: a deterministic self-hashed handoff manifest containing relative artifact names,
  lengths, and hashes.

This closes bounded results inspection and review/export behavior for the current native profile. It
does not provide a general visual model editor or 3D result explorer.

## Legacy authority still active

`native/decommission/workbench-ui-transition-v1.json` freezes the current source and CI inventory.
The product deployment authority has already left React Pages, but seven active workflows still use
Node for frontend, viewer, AI-contract, or broader quality verification. React/Vite source,
TypeScript tests, static JavaScript viewer modules, Node scripts, and their package manifest remain
active verification or parity material. They are not a deletion target yet.

The checker fails if source counts or active Node workflow inventory drift without an explicit
ledger update. It also fails if the manifest claims C6 without deriving it from every prerequisite.
Run it with:

```text
python3 scripts/check_native_workbench_ui_transition.py --json --fail-blocked
```

`--require-c6` intentionally exits nonzero while the transition remains open.

## Removal gates

React/TypeScript/JavaScript removal remains forbidden until all of these are simultaneously true:

1. general native feature parity is complete for the accepted product scope;
2. active Node verification authority is zero and Rust/Cargo/CTest/HIP E2E owns the tests;
3. Python and Node fixture ownership has moved to language-neutral golden data;
4. the approved-device HIP C2 receipts are complete;
5. the deprecation window and rollback package are complete;
6. a Python/Node-free clean-machine product package E2E is authoritative;
7. native result, error, and checksum parity is complete.

Until then `removal_allowed` and `c6_complete` stay false. A contract pass means the inventory is
honest; it does not mean the transition is finished.
