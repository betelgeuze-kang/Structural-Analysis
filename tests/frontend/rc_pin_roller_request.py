"""Emit the fixed synthetic pin/roller browser request; never execute a solver."""

from rc_lifecycle_http_fixture import authored_pin_roller_request, canonical

if __name__ == "__main__":
    print(canonical(authored_pin_roller_request()).decode())
