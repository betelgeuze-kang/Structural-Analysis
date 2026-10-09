"""A build receipt must reject a missing or substituted dynamic public preset."""
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("mode", ["valid", "missing", "substituted"])
def test_public_preset_is_bound_into_delivery_receipt(tmp_path, mode):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime required")
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "scripts/verify-workbench-viewer-delivery.mjs"
    script.parent.mkdir()
    shutil.copyfile(root / "scripts/verify-workbench-viewer-delivery.mjs", script)
    fixtures = {
        "dist/index.html": '<div id="root"></div><script src="/assets/workbench.js"></script>',
        "dist/src/structure-viewer/index.html": '<main data-si-shell="product" data-viewer-workflow="model"></main><script src="/assets/viewer.js"></script>',
        "dist/assets/workbench.js": '"src/structure-viewer/index.html"; import("./App-fixture.js")',
        "dist/assets/viewer.js": 'new URL("/assets/index.midas33.data-fixture.js", import.meta.url)',
        "dist/assets/App-fixture.js": '"Structural Signal Desk native-authoring-controls release-gap-review-state"',
        "src/structure-viewer/index.midas33.data.js": 'window.__STRUCTURE_VIEWER_PRESET_PAYLOADS__={};',
    }
    if mode != "missing":
        fixtures["dist/assets/index.midas33.data-fixture.js"] = (
            fixtures["src/structure-viewer/index.midas33.data.js"]
            if mode == "valid" else "window.substituted=true;"
        )
    for name, data in fixtures.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=15)
    if mode == "valid":
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
        assert ("is missing" if mode == "missing" else "differs from its source") in result.stderr
