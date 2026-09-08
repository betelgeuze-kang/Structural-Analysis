# Preserved candidate-process review fixture

`observed-suite.json.gz` preserves the JSON bytes from the local, synthetic
two-case/two-repetition observation documented in
[`rc-fiber-candidate-process-runtime-20260908.md`](../../../docs/engineering/rc-fiber-candidate-process-runtime-20260908.md).
The producer source was `b4681eeabbaccb7cce3eedc491dc2fcd0f194444`.
This fixture supports portable exporter and browser contract tests without
starting a solver, collecting training data, fitting a policy or launching a
candidate worker.

## Contents and identities

- Gzip: 2,430,332 bytes; SHA-256
  `5df1a41f2a5387be864077d5472c9e55f45ca620a1e2b6a987e2f65c2a18ab1f`.
- Encoding: UTF-8 JSON, gzip compression level 9 with timestamp 0.
- Fixture schema: `rc-fiber-candidate-review-test-fixture.v1`.
- 71 files, totaling 16,751,824 uncompressed file bytes: the suite's 55 JSON
  input/request/worker/report files and eight original design-comparison
  manifest/report pairs.
- Original observation manifest SHA-256:
  `0b767212bc8cb12e55c244de7b2e0e23b20422c88619523517a530c62d118297`.
- Suite: `suite/suite.json`, 7,754,233 bytes; SHA-256
  `6539106620d6868abf8944b198c508b8eb1693302948013baefb84aa7d204dea`.

Each `files` entry has `path`, `byte_length`, `sha256` and `utf8`. Re-encode
`utf8` directly as UTF-8 and verify its byte length and SHA-256 before writing
to a fresh temporary root. Do not parse and reserialize the nested file text.
Reject absolute paths, traversal, duplicate paths and symlink escapes.
`expected_comparisons` associates each case/phase/repetition/strategy with its
original comparison pair. Original absolute paths inside those preserved JSON
files intentionally remain unchanged; relocation must resolve them through a
validated mapping to the extracted files, without reading the original paths.

The tests' reconstructed browser manifest exercises the consumer contract.
End-to-end exporter observations must separately use the Python exporter output;
a Node fixture reconstruction alone does not establish producer integration.

## Scope

These are saved measurements, not current performance measurements. The two
synthetic pools reused one historical training artifact: 4 historical, 16 online
and 12 oracle analysis requests, totaling 32. Each online choice had a budget of
2 requests including its own baseline. Learned selection chose `near-limit` in
all four comparisons, but paired timings changed sign across repetitions and
established no consistent acceleration. Synthetic prices are test inputs, not
quotes or evidence of construction savings.

Hashes establish local byte consistency. They do not attest authorship,
independent physical validation, cross-project generalization, hardware
acceptance, hosted CI or release approval. Failed/unknown/warmup contracts are
tested with explicitly derived variants rather than relabeled as observations
from this ready, measured-only run.
