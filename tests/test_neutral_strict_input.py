"""Common model loading rejects ambiguous bytes before constructing a model."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from structural_analysis.io.neutral import loader


EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_cantilever.json"
)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"units":{},"units":{}}',
        b'{"metadata":{"width_m":0.9,"width_m":0.4}}',
        b'{"nodes":[{"id":"one","id":"two"}]}',
        b'{"width_m":0.9,"\\u0077idth_m":0.4}',
        b'{"metadata":{"x":NaN}}',
        b'{"metadata":{"x":Infinity}}',
        b'{"metadata":{"x":-Infinity}}',
        b'{"metadata":{"x":1e9999}}',
        b'{"metadata":{"x":-1e9999}}',
        b'{"metadata":{"x":"\\ud800"}}',
        b'{"\\udfff":1}',
        b'{"x":"\xff"}',
        b"\xef\xbb\xbf{}",
        b'{"broken":',
        b"[]",
        b"null",
        b"",
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_rejects_ambiguity_before_model_construction(raw, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("model construction reached invalid JSON")

    monkeypatch.setattr(loader, "_load_neutral_payload", forbidden)
    with pytest.raises(ValueError):
        loader.load_neutral_json_bytes(raw)


@pytest.mark.parametrize("kind", [bytes, bytearray, memoryview])
def test_valid_input_preserves_canonical_payload_and_original_digest(kind):
    raw = EXAMPLE.read_bytes()
    payload = json.loads(raw)
    expected = loader._load_neutral_payload(
        payload,
        source_path="valid.json",
        input_checksum="sha256:" + hashlib.sha256(raw).hexdigest(),
    )
    actual = loader.load_neutral_json_bytes(kind(raw), source_path="valid.json")
    assert actual.to_dict() == expected.to_dict()
    assert actual.canonical_model_checksum == expected.canonical_model_checksum


def test_repeated_keys_in_different_objects_and_numeric_metadata_remain_valid():
    payload = json.loads(EXAMPLE.read_bytes())
    payload["metadata"] = {
        "a": {"x": 0},
        "b": {"x": -0.0},
        "unicode": "\U0001f600",
        "integer": 2**60,
        "label": "NaN",
        "finite": 1e300,
    }
    raw = json.dumps(payload, ensure_ascii=True).encode()
    model = loader.load_neutral_json_bytes(raw)
    assert model.metadata == payload["metadata"]


def test_path_loader_enforces_existing_bound_without_reading_entire_file(tmp_path):
    path = tmp_path / "oversize.json"
    with path.open("wb") as f:
        f.seek(16 * 1024 * 1024)
        f.write(b" ")
    with pytest.raises(ValueError, match="bounded"):
        loader.load_neutral_json(path)


def test_path_and_bytes_loaders_share_duplicate_rejection(tmp_path):
    path = tmp_path / "ambiguous.json"
    path.write_bytes(b'{"nodes": [], "nodes": []}')
    with pytest.raises(ValueError, match="duplicate"):
        loader.load_neutral_json(path)
