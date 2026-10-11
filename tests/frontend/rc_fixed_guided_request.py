"""Emit a synthetic fixed-guided request; no specimen data or solver execution."""

from rc_lifecycle_http_fixture import authored_fixed_guided_request, canonical

if __name__ == "__main__":
    print(canonical(authored_fixed_guided_request()).decode())
