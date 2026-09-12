# Original cost-pruned layout fixtures

`rc-layout-pruned.json.gz` contains base64 maps of original JSON bytes for three
completed price-order, learned-order and shortened-horizon executions. Gzip has
a fixed zero mtime. Raw numeric tokens and original hashes are preserved.

`price` is the unchanged `o0-pruned` export from the sealed actual HTTP packet
`structural-layout-cost-pruned-http-qrzs4ei7`, inventory SHA-256
`997a747130bd075344a9e7000ee665a5a3b8fcfb2305f7486844f8bd113d481d`.
All copied originals were checked against that inventory. Numerical source is
`d11248ce06627c8466ae348a88f91a3b167ce05e`. It evaluates baseline/small/middle,
selects middle, and omits large/outside on the strict declared-cost bound.

`horizon` and `learned` were newly executed for UI regression using the Python
source at `5c1110737cc94d7decb19f02001bf155bef0ff72` (only frontend files were dirty).
Both reuse models, request, prices and, for learned order, the original policy
and historical training report from `structural-layout-standalone-http-k2szhu8w`.
Those inputs were checked against inventory
`6bfbec705085bc7b964d6acd2ec22266a8443d92bcb425604940b5d13fcbdca9`.

The horizon run evaluates baseline/small and selects none; middle/large/outside
are outside the consideration horizon, not cost-skipped. The learned run
evaluates baseline/large/middle/small, selects middle and cost-skips outside.
Both include actual fresh reference verification and pass HTTP admission.
Together they add six reference model rows, twelve analysis/verification
invocations, 72 target steps and 144 Newton iterations/linear solves. No new fit
is performed. Their generation call intervals are 6.673594746 s and
13.258234516 s, separately from frontend tests, browser review and historical
training. These are fixture preparation observations, not a matched performance
benchmark or independent generalization test.

The new driver, original results, decisions, exported graphs and receipts are
read-only at `structural-layout-pruned-ui-fixtures-vzzrx2jn` under the mounted
evidence volume. Its inventory SHA-256 is
`9296e2576472e37fdc918f6d992d018d783bfe89068c8769228a0b97a43eb0fa`
(162 files / 20,558,163 bytes). The compressed repository fixture is 3,293,758 bytes.
Prices are synthetic; original scope and non-qualification claims remain intact.
