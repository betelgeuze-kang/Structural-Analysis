from __future__ import annotations

import argparse
from pathlib import Path

from implementation.phase1.build_real_drawing_private_3d_webviewer import (
    DEFAULT_INTAKE_QUEUE,
    DEFAULT_MAX_PROXY_EDGES,
    DEFAULT_MAX_PROXY_NODES,
    DEFAULT_MAX_SEGMENTS_PER_ASSET,
    DEFAULT_OUT_SUMMARY,
    DEFAULT_OUT_VIEWER_SIDECAR,
    build_webviewer,
)


def export_structure_viewer_preset(
    *,
    intake_queue_path: Path = DEFAULT_INTAKE_QUEUE,
    out_summary: Path = DEFAULT_OUT_SUMMARY,
    out_viewer_sidecar: Path = DEFAULT_OUT_VIEWER_SIDECAR,
    max_segments_per_asset: int = DEFAULT_MAX_SEGMENTS_PER_ASSET,
    max_proxy_nodes: int = DEFAULT_MAX_PROXY_NODES,
    max_proxy_edges: int = DEFAULT_MAX_PROXY_EDGES,
) -> dict:
    return build_webviewer(
        intake_queue_path=intake_queue_path,
        out_html=None,
        out_summary=out_summary,
        out_viewer_sidecar=out_viewer_sidecar,
        max_segments_per_asset=max_segments_per_asset,
        max_proxy_nodes=max_proxy_nodes,
        max_proxy_edges=max_proxy_edges,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export real drawing derived topology as an integrated structure-viewer preset sidecar."
    )
    parser.add_argument("--intake-queue", default=str(DEFAULT_INTAKE_QUEUE))
    parser.add_argument("--out-summary", default=str(DEFAULT_OUT_SUMMARY))
    parser.add_argument("--out-viewer-sidecar", default=str(DEFAULT_OUT_VIEWER_SIDECAR))
    parser.add_argument("--max-segments-per-asset", type=int, default=DEFAULT_MAX_SEGMENTS_PER_ASSET)
    parser.add_argument("--max-proxy-nodes", type=int, default=DEFAULT_MAX_PROXY_NODES)
    parser.add_argument("--max-proxy-edges", type=int, default=DEFAULT_MAX_PROXY_EDGES)
    args = parser.parse_args()
    export_structure_viewer_preset(
        intake_queue_path=Path(args.intake_queue),
        out_summary=Path(args.out_summary),
        out_viewer_sidecar=Path(args.out_viewer_sidecar),
        max_segments_per_asset=args.max_segments_per_asset,
        max_proxy_nodes=args.max_proxy_nodes,
        max_proxy_edges=args.max_proxy_edges,
    )


if __name__ == "__main__":
    main()
