# RC browser review byte budgets

The default RC result limit remains 64 MiB. A trusted application host may opt
into a larger result on a workspace with sufficient memory:

```js
window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
  rcJobCollectionUrl: '/v1/jobs',
  jobAuthorization: existingAuthorizationProvider,
  rcReviewResultMaxBytes: 128 * 1024 * 1024,
}
```

The setting is a positive safe integer, at most 128 MiB. It is not read from job
input, media types, saved links or query parameters. Invalid settings fail closed.
The host can also choose a smaller limit. Changing the setting replaces the RC
review session and disposes its old Worker.

Admission checks all declared artifact sizes before downloading any artifact.
Request and evidence remain limited to 16 MiB each; checkpoint remains 128 MiB.
The total cannot exceed 224 MiB, the sum of the original role limits. Streaming
length limits, hashes, full result bindings and the real review Worker remain in
force. A size rejection has a specific workspace-capacity message.

These limits bound encoded input bytes, not JavaScript heap, browser RSS, total
host memory or numerical solver resources. Parsed objects and rendering consume
additional memory. Hosts must qualify the configured limit on their supported
machines. No performance improvement or unrestricted large-model support follows
from increasing a wire-byte allowance.

The source-informed 161-target managed lifecycle exposed this boundary with a
117,689,201-byte result. Its original default-budget rejection is retained. The
same result is used to test explicit host admission, two cold browser/server
opens, actual result/report validation and exact report downloads; the input is
not shortened to make it fit. Physical specimen qualification remains separate.

The cold-screen test also exposed a missing default public MIDAS33 viewer sidecar.
The loader now uses a build-resolved asset URL for that preset, and the delivery
verifier requires one emitted file with exact source bytes. Private drawing
sidecar loading is unchanged. Missing or substituted public preset files fail the
delivery check instead of silently receiving an HTML fallback from a static host.
