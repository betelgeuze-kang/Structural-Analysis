FROM docker.io/library/python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# These mutable acquisition bytes become part of the derived local OCI image.
# The workflow records that image ID and every rootfs diff ID before execution;
# it never treats this Dockerfile alone as a reproducible package lock.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libblas3 \
        libgfortran5 \
        liblapack3 \
        libopenmpi3 \
        libquadmath0 \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["python"]
