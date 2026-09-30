"""Export the observed false-pass candidate's original graph for Workbench tests."""

import base64
import gzip
import hashlib
import json
from pathlib import Path

from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    RcSearchArtifactWSGIApplication,
)


def main():
    summary = json.loads(
        Path(
            "docs/engineering/rc-reinforcement-boundary-20260920.summary.json"
        ).read_bytes()
    )
    root = Path(summary["packet_root"])
    raw = (root / "inventory.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != summary["inventory_sha256"]:
        raise ValueError("original inventory pin mismatch")
    inventory = json.loads(raw)
    prefix = "w44-peak10/exhaustive-audit/"

    def read(name, maximum):
        ref = inventory[prefix + name]
        raw = (root / prefix / name).read_bytes()
        if (
            len(raw) > maximum
            or len(raw) != ref["byte_length"]
            or hashlib.sha256(raw).hexdigest() != ref["sha256"]
        ):
            raise ValueError("original graph bytes mismatch")
        return raw

    report = json.loads(read("result.json", 2 * 1024 * 1024))
    bundle = RcSearchArtifactBundle.from_reader(
        read, expected_report_hash=report["report_hash"]
    )
    app = RcSearchArtifactWSGIApplication(
        {("fixture", "boundary"): bundle},
        authorize=lambda tenant, token: (tenant, token) == ("fixture", "synthetic"),
    )
    for name, raw in bundle.artifacts.items():
        response = app.handle(
            "GET",
            "/v1/rc-search/boundary/" + name,
            headers={
                "X-Structural-Tenant": "fixture",
                "Authorization": "Bearer synthetic",
            },
        )
        if response.status != 200 or response.body != raw:
            raise ValueError("HTTP snapshot bytes mismatch")
    packed = {
        name: base64.b64encode(raw).decode() for name, raw in bundle.artifacts.items()
    }
    target = Path("tests/frontend/fixtures/boundary-search-artifacts.json.gz")
    target.write_bytes(
        gzip.compress(json.dumps(packed, sort_keys=True).encode(), mtime=0)
    )
    print(
        json.dumps(
            {
                "artifact_count": len(packed),
                "fixture_bytes": target.stat().st_size,
                "fixture_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "original_source_revision": summary["source_revision"],
            }
        )
    )


if __name__ == "__main__":
    main()
