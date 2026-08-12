from __future__ import annotations

from implementation.phase1 import rust_nonlinear_frame_bridge as frame_bridge
from implementation.phase1 import rust_track_lf_bridge as track_bridge


def test_frame_and_track_bridges_use_structural_runtime_crate() -> None:
    for bridge in [frame_bridge, track_bridge]:
        assert bridge.CRATE_DIR.name == "structural_runtime_ffi"
        assert "structural_runtime_ffi" in bridge._shared_lib_name()
        assert bridge.WORKSPACE_DIR.name == "native"
        assert bridge.TARGET_DIR == bridge.CRATE_DIR / "target" / "release"


def test_structural_runtime_crate_sources_are_available() -> None:
    for bridge in [frame_bridge, track_bridge]:
        assert (bridge.CRATE_DIR / "Cargo.toml").is_file()
        assert (bridge.CRATE_DIR / "src" / "lib.rs").is_file()
