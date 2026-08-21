# Verified Frame3D Linear Quickstart

This installed example runs one bounded two-node Frame3D cantilever through the native
`ModelIR -> Validate -> Run -> Resume -> Compare -> Report` workflow. The supplied comparison is
a language-neutral closed-form Euler-Bernoulli oracle, not commercial-solver validation or an
engineering-acceptance verdict.

Set `STRUCTURAL_HOME` to the installed release payload and choose a new writable directory:

```sh
STRUCTURAL_HOME=/opt/structural
EXAMPLE="$STRUCTURAL_HOME/share/structural-examples/frame3d-linear-cantilever"
SESSION="$PWD/frame3d-linear-quickstart"
```

Inspect the model, execute the complete checkpointed workflow, then read the terminal results:

```sh
"$STRUCTURAL_HOME/bin/structural-workbench" model-view \
  "$EXAMPLE/model.json" --locale en-US --projection isometric

"$STRUCTURAL_HOME/bin/structural-workbench" workflow-model-linear \
  "$EXAMPLE/model.json" "$EXAMPLE/analysis-request.json" \
  --external-result "$EXAMPLE/external-result.json" \
  --source-artifact "$EXAMPLE/language-neutral-oracle.txt" \
  --workspace "$SESSION" --step-budget 1

"$STRUCTURAL_HOME/bin/structural-workbench" report-view \
  --workspace "$SESSION" --locale en-US
"$STRUCTURAL_HOME/bin/structural-workbench" nodal-displacement-view \
  --workspace "$SESSION" --locale en-US
"$STRUCTURAL_HOME/bin/structural-workbench" reaction-view \
  --workspace "$SESSION" --locale en-US
"$STRUCTURAL_HOME/bin/structural-workbench" element-recovery-view \
  --workspace "$SESSION" --locale en-US
```

The workflow succeeds only when the native result matches the bound oracle exactly and produces a
reported durable session with deterministic ResultIR, recovery, reaction, comparison, Markdown,
and PDF artifacts. It intentionally exercises only the installed CPU Frame3D linear-static profile.
Unsupported shell, nonlinear, design-code, and engineering-verdict scope remains fail-closed.
