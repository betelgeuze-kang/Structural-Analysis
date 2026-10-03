# Pin/roller RC stored-review fixture

Original job-service artifacts produced by the RC worker at backend source
`af03e5b6780b093af1060e15466a78980b96d8a3`. The source revision in the
request is a caller declaration, not an independent source attestation.

The synthetic pin/roller model has two lateral targets with one target per
chunk. `checkpointed-job.json` is the service view after the first saved
checkpoint. The service was reopened on the same temporary store before the
second chunk; `job.json`, request, checkpoint, result and evidence were read
from the completed service. The saved checkpoint is the original prefix
artifact and each result receipt retains its corresponding restart binding.

These bytes support local transport and display tests only. They do not
establish independent physical validation, design approval, or release
readiness.
