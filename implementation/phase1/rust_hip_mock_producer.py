#!/usr/bin/env python3
"""Mock producer that emulates Rust/HIP DLPack bridge responses for strict probe tests."""

import json
import sys


def main() -> None:
    req = json.loads(sys.stdin.read())
    action = req.get("action")
    if action != "dlpack_bridge_probe":
        raise SystemExit(f"unsupported action: {action}")

    out = {
        "producer_kind": "rust_hip",
        "roundtrip_success": True,
        "shared_storage": True,
        "host_copy_bytes": 0,
        "device": "hip:0",
        "shape": [4096, 128],
        "dtype": "float32",
        "strides": [128, 1],
        "byte_offset": 0,
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
