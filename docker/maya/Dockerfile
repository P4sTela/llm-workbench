# syntax=docker/dockerfile:1
# Project Maya v1.1.31, GLM-5.3-Flash Maya-M-Derisked, RTX 4090 (sm_89).
# Compile at image build; keep weights, packs and runtime state on /data.
FROM nvidia/cuda:13.0.0-devel-ubuntu24.04

ARG MAYA_COMMIT=c4be54416a4f30a837c2fae91816dc9550d68b61
ARG CUDA_ARCHITECTURES=89
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 LANG=C.UTF-8 \
    MAYA_UPDATE_CHECK=0 HOME=/data/home

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git libatomic1 libgomp1 \
        python3 python3-pip python3-venv unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/maya
RUN git init . \
    && git remote add origin https://github.com/mw00/project-maya.git \
    && git fetch --depth 1 origin "$MAYA_COMMIT" \
    && git checkout --detach "$MAYA_COMMIT" \
    && test "$(git rev-parse HEAD)" = "$MAYA_COMMIT"

# Use upstream's package list/stamp and compile helper, not Strata's BUILD.json:
# Maya reuses build/strata and build/MAYA-BUILD.json with its source fingerprint.
RUN python3 -m venv .venv
RUN CUDA_ARCHITECTURES="$CUDA_ARCHITECTURES" .venv/bin/python - <<'PY'
import os
import setup
import maya

setup.pip_install(setup.PY_PACKAGES, "Maya's Python packages")
llama = setup.get_llama_cpp()
archs = [int(a) for a in os.environ["CUDA_ARCHITECTURES"].replace(",", ";").split(";")]
nvcc, host_compiler = maya.toolchain_for(archs, None, None)
if not nvcc:
    raise SystemExit("No CUDA compiler found")
maya.compile_engine(archs, [0], nvcc, host_compiler, llama,
                    setup.source_hash(setup.ENGINE_SOURCES))
PY

# GeForce uses the host driver's libraries, not datacenter forward compatibility.
RUN rm -rf /usr/local/cuda-13.0/compat /usr/local/cuda/compat
COPY scripts/download-model.py /opt/workbench/download-model.py
COPY models/manifests/glm53-flash-maya-m-derisked.json /opt/workbench/model.json
COPY models/manifests/glm53-flash-dflash2.json /opt/workbench/dflash2.json
COPY docker/maya/calibrate.py /opt/workbench/calibrate.py
COPY --chmod=755 docker/maya/docker-entrypoint.sh ./docker-entrypoint.sh

VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=1800s --retries=3 \
    CMD curl -fs "http://127.0.0.1:${PORT:-8080}/health" | .venv/bin/python -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("status") == "ok" else 1)'
ENTRYPOINT ["./docker-entrypoint.sh"]
