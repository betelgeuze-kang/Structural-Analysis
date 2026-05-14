from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_app_resource_model_is_extracted_from_main_app_shell() -> None:
    app = (ROOT / "src" / "App.tsx").read_text(encoding="utf-8")
    resource_model = (ROOT / "src" / "workbench" / "resourceModel.ts").read_text(encoding="utf-8")

    assert "from './workbench/resourceModel'" in app
    assert "function createInitialResources" not in app
    assert "export function createInitialResources" in resource_model
    assert "export type ResourceMap" in resource_model
    assert "authoringRuntimeWritebackDepth" in resource_model
    assert "commercialWorkflowBreadth" in resource_model
