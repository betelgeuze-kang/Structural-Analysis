#!/usr/bin/env python3
"""Backward-compatible wrapper for benchmark_kpi_contract.py.

Deprecated: keep this entrypoint to avoid breaking older scripts, but route all
logic to the production benchmark runner.
"""

from benchmark_kpi_contract import main


if __name__ == "__main__":
    main()

