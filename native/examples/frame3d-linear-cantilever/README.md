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

HTML_REPORT="$PWD/frame3d-linear-html-report"
"$STRUCTURAL_HOME/bin/structural-workbench" report-export-html \
  --workspace "$SESSION" --output-dir "$HTML_REPORT" --locale en-US
```

The create-new HTML export writes a standalone, script-free `report.html` and a self-hashed
`html-receipt.json`. The receipt binds the durable session, model, ResultIR, recovery, optional
reaction result, ReportIR, PDF, external comparison, and rendered HTML identities. Use `ko-KR`
for the deterministic Korean projection. Existing output directories are rejected.

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
one-iteration case now uses the same durable Workbench workflow. Because the bounded run converges
immediately, `03-run` is the verified terminal artifact directory and the resume transition is
explicitly `not_required`; no artificial partial run is manufactured:

```sh
CALCULIX_SESSION="$PWD/frame3d-linear-calculix-session"
"$STRUCTURAL_HOME/bin/structural-workbench" workflow-model-linear \
  "$EXAMPLE/model-calculix-axial.json" "$EXAMPLE/analysis-request-axial.json" \
  --external-result "$EXAMPLE/external-result-calculix-proxy.json" \
  --source-artifact "$EXAMPLE/calculix-technical-proxy.txt" \
  --workspace "$CALCULIX_SESSION" --step-budget 1
```

This is also explicit `proxy` evidence. It binds the frozen clean-runner
`axial_member_tip_load` metric but does not redistribute or execute CalculiX, satisfy product legal
approval, or establish independent validation.

The workflow succeeds only when the native result matches the bound oracle exactly and produces a
reported durable session with deterministic ResultIR, recovery, reaction, comparison, Markdown,
PDF, and bounded standalone HTML artifacts. It intentionally exercises only the installed CPU
Frame3D linear-static profile. The HTML is a verified projection, not complete schedules, an HTML
accessibility certification, or a design-code/engineering verdict. Unsupported shell and nonlinear
scope remains fail-closed.
