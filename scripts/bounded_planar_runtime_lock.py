"""Checked OpenSeesPy wheel lock shared by bounded-planar execution packages."""

from __future__ import annotations

import re


OPENSEESPY_VERSION = "3.7.1.2"
OPENSEES_CORE_VERSION = "3.7.1"
OPENSEESPY_WHEEL_SHA256 = (
    "1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65"
)
OPENSEESPY_LINUX_WHEEL_SHA256 = (
    "63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a"
)

REQUIREMENTS_TEXT = f"""\
openseespy=={OPENSEESPY_VERSION} \\
    --hash=sha256:{OPENSEESPY_WHEEL_SHA256}
openseespylinux=={OPENSEESPY_VERSION} \\
    --hash=sha256:{OPENSEESPY_LINUX_WHEEL_SHA256}
"""

EXPECTED_WHEEL_HASHES = {
    "openseespy": OPENSEESPY_WHEEL_SHA256,
    "openseespylinux": OPENSEESPY_LINUX_WHEEL_SHA256,
}


def requirements_bytes() -> bytes:
    return REQUIREMENTS_TEXT.encode("utf-8")


def validate_requirements_text(value: str) -> None:
    observed = {
        package: digest
        for package, digest in re.findall(
            r"(?m)^(openseespy|openseespylinux)==3\.7\.1\.2\s+\\\n"
            r"\s+--hash=sha256:([0-9a-f]{64})$",
            value,
        )
    }
    if observed != EXPECTED_WHEEL_HASHES or value != REQUIREMENTS_TEXT:
        raise ValueError("bounded_planar_openseespy_lock_invalid")
