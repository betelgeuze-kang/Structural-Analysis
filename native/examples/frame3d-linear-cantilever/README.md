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

An optional second session exercises the same installed native result against the stored
OpenSees 3.7.1 technical-result projection:

```sh
OPENSEES_SESSION="$PWD/frame3d-linear-opensees-proxy"
"$STRUCTURAL_HOME/bin/structural-workbench" workflow-model-linear \
  "$EXAMPLE/model.json" "$EXAMPLE/analysis-request.json" \
  --external-result "$EXAMPLE/external-result-opensees-proxy.json" \
  --source-artifact "$EXAMPLE/opensees-technical-proxy.txt" \
  --workspace "$OPENSEES_SESSION" --step-budget 1
```

This second comparison is deliberately encoded as `proxy`: the source note binds the frozen
clean-runner receipt and its exact `cantilever_tip_load` metric, while no OpenSees executable is
redistributed or executed by the installed package. It is a native-product integration bridge,
not a fresh current-source external run or independent validation.

The packaged 10 kN axial variant provides the corresponding stored CalculiX 2.17 bridge. This
one-iteration case runs directly through the product CLI; it does not manufacture a checkpoint for
the Workbench's checkpoint-required durable workflow:

```sh
CALCULIX_RESULT="$PWD/frame3d-linear-calculix-result"
CALCULIX_COMPARISON="$PWD/frame3d-linear-calculix-comparison"
"$STRUCTURAL_HOME/bin/structural-cli" analysis model-linear-run \
  "$EXAMPLE/model-calculix-axial.json" "$EXAMPLE/analysis-request-axial.json" \
  --output-dir "$CALCULIX_RESULT"
"$STRUCTURAL_HOME/bin/structural-cli" comparison model-linear \
  "$CALCULIX_RESULT/result-ir.json" "$CALCULIX_RESULT/result-recovery-ir.json" \
  "$EXAMPLE/external-result-calculix-proxy.json" \
  "$EXAMPLE/calculix-technical-proxy.txt" \
  --output-dir "$CALCULIX_COMPARISON" --require-pass
```

This is also explicit `proxy` evidence. It binds the frozen clean-runner
`axial_member_tip_load` metric but does not redistribute or execute CalculiX, satisfy product legal
approval, or establish independent validation.

The workflow succeeds only when the native result matches the bound oracle exactly and produces a
reported durable session with deterministic ResultIR, recovery, reaction, comparison, Markdown,
and PDF artifacts. It intentionally exercises only the installed CPU Frame3D linear-static profile.
Unsupported shell, nonlinear, design-code, and engineering-verdict scope remains fail-closed.
