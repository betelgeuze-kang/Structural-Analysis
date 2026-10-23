from pathlib import Path
import runpy

import pytest


DRIVER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/benchmark_native_steel_batch.py")
)


def test_every_timed_sample_is_checked_even_if_last_matches_first():
    values = iter(["stable", "different", "stable", "stable"])
    with pytest.raises(RuntimeError, match="sample output differs"):
        DRIVER["measure"](lambda: next(values), 3, DRIVER["digest"])


def test_sample_fingerprints_and_raw_timings_are_preserved():
    last, timing, first = DRIVER["measure"](lambda: {"value": 42}, 3, DRIVER["digest"])
    assert first == last == {"value": 42}
    assert timing["sample_output_sha256"] == [timing["first_output_sha256"]] * 3
    assert len(timing["samples_ns"]) == 3
    assert all(value >= 0 for value in timing["samples_ns"])
