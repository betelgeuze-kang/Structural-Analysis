from __future__ import annotations

from graph_partition_metis import partition_graph


def _line_edges(n: int) -> list[list[int]]:
    edges = [[i, i + 1] for i in range(n - 1)]
    for i in range(n - 4):
        if i % 3 == 0:
            edges.append([i, i + 3])
    return edges


def test_partition_graph_basic_quality() -> None:
    n = 128
    result = partition_graph(
        node_count=n,
        edges=_line_edges(n),
        k_partitions=8,
        halo_depth=1,
        weight_mode="degree",
        state_components=5,
        require_metis=False,
    )

    assert len(result["partition_id_per_node"]) == n
    assert result["edge_count"] > 0
    assert 0.0 <= float(result["cut_ratio"]) <= 1.0
    assert 0.0 <= float(result["halo_node_ratio"]) <= 1.0
    assert float(result["estimated_comm_bytes"]) >= 0.0


def test_partition_graph_balance_reasonable() -> None:
    n = 256
    result = partition_graph(
        node_count=n,
        edges=_line_edges(n),
        k_partitions=16,
        halo_depth=2,
        weight_mode="uniform",
        state_components=7,
        require_metis=False,
    )

    sizes = result["partition_sizes"]
    assert len(sizes) == 16
    assert min(sizes) > 0
    # Keep balance guard broad to allow both pymetis and fallback backend.
    assert float(result["partition_balance_ratio"]) <= 4.0
