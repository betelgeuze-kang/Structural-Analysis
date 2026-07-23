FROM python:3.11-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        git \
        libblas3 \
        libgfortran5 \
        liblapack3 \
        libopenmpi3 \
        libquadmath0 \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install \
        numpy==1.26.4 \
        scipy==1.12.0 \
        jsonschema==4.26.0 \
        attrs==25.4.0 \
        jsonschema-specifications==2025.9.1 \
        referencing==0.37.0 \
        rpds-py==0.30.0 \
        typing-extensions==4.15.0

COPY run_clean_runner.py /opt/structural-analysis-clean-runner/run_clean_runner.py

ENTRYPOINT ["python", "/opt/structural-analysis-clean-runner/run_clean_runner.py"]
