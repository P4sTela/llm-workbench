# syntax=docker/dockerfile:1
#
# Strata: Qwen3.8-Flash-Next on an NVIDIA RTX 4090 (sm_89).
#
# Mirrors the official single-stage build from Niko1221/Strata at the pinned
# commit (docs/INSTALL.md, "Docker (Linux)"), with the `COPY . .` replaced by
# a pinned shallow fetch so the workbench recipe is reproducible from a clean
# checkout. The engine is compiled during docker build; the first container
# start only downloads the selected model into the /data volume and starts
# the OpenAI/Anthropic-compatible server on :8080 (IQ3_S or UD-IQ4_XS).
#
# Build:
#   docker build -t strata-qwen4:4090 -f docker/strata/Dockerfile .
#   # CUDA_ARCHITECTURES=89 (the default) targets the RTX 4090 only and is
#   # the fastest build. Use "75;80;86;89;120" to reproduce the official
#   # fat binary for RTX 20/30/40/50 + A-series.
#
# Run (host needs an NVIDIA driver >= 580 and nvidia-container-toolkit):
#   docker compose -f docker/strata/compose.yaml up --build
#
# GeForce cards use the host driver: the CUDA image's forward-compatibility
# libraries are for datacenter GPUs and are removed, as in docker/ninfer.

FROM nvidia/cuda:13.0.0-devel-ubuntu24.04

ARG STRATA_REPO=https://github.com/Niko1221/Strata.git
ARG STRATA_COMMIT=1678de333d0e0711bc414ad992b640e1a37dd814
# RTX 40 only by default (fastest build); the official default is "75;80;86;89;120".
ARG CUDA_ARCHITECTURES=89
ARG BUILD_VISION=1

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 LANG=C.UTF-8 STRATA_EXECV=1
# read by the build snippet below, exactly like the official Dockerfile
ENV CUDA_ARCHITECTURES=${CUDA_ARCHITECTURES} BUILD_VISION=${BUILD_VISION}

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git libatomic1 libgomp1 \
        python3 python3-pip python3-venv unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/strata

# Pinned shallow fetch in place of the official `COPY . .`
RUN git init . \
    && git remote add origin "$STRATA_REPO" \
    && git fetch --depth 1 origin "$STRATA_COMMIT" \
    && git checkout --detach "$STRATA_COMMIT" \
    && test "$(git rev-parse HEAD)" = "$STRATA_COMMIT"


# Keep upstream's per-model setup flow, adding optional resident-budget wiring.
COPY --chmod=755 docker/strata/docker-entrypoint.sh ./docker-entrypoint.sh
RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --upgrade pip \
    && .venv/bin/pip install --no-cache-dir -r requirements.txt \
    && chmod +x setup.sh docker-entrypoint.sh

# llama.cpp at the pinned commit, then the engine and the image encoder, built
# exactly the way setup.py builds them (verbatim from the official Dockerfile).
# BUILD.json records source=local with a matching src hash, so the first start
# reuses this engine instead of recompiling.
RUN .venv/bin/python - <<'PYEOF'
import json, os, pathlib, shutil
import setup

llama = setup.get_llama_cpp()
nvcc, _ = setup.find_nvcc()
arch = os.environ.get("CUDA_ARCHITECTURES", "75;80;86;89;120").strip().strip('"').replace(",", ";")
vision = "gpu" if os.environ.get("BUILD_VISION", "1") == "1" else "none"

setup.cmake_build(setup.ROOT, setup.ROOT / "build", "strata",
    ["-DSTRATA_ENABLE_CUDA=ON", "-DSTRATA_BUILD_TESTS=OFF",
     f"-DCMAKE_CUDA_ARCHITECTURES={arch}", f"-DCMAKE_CUDA_COMPILER={nvcc}",
     f"-DSTRATA_GGML_DIR={llama}"], None, "build-strata.bat")
if vision != "none":
    setup.cmake_build(setup.ROOT / "tools" / "vision", setup.ROOT / "build-vision", "strata-vision",
        [f"-DLLAMA_DIR={llama}", "-DSTRATA_VISION_CUDA=ON",
         f"-DCMAKE_CUDA_ARCHITECTURES={arch}", f"-DCMAKE_CUDA_COMPILER={nvcc}"], None, "build-vision.bat")

eng = setup.ROOT / "engine"
eng.mkdir(exist_ok=True)
shutil.copy2(setup.ROOT / "build" / setup.EXE, eng / setup.EXE)
if vision != "none":
    shutil.copy2(setup.ROOT / "build-vision" / "bin" / setup.VEXE, eng / setup.VEXE)
bindir = pathlib.Path(nvcc).parent
meta = {"source": "local", "version": setup.source_version(),
        "archs": [int(a.split("-")[0]) for a in arch.split(";") if a.split("-")[0].isdigit()], "vision": vision,
        "cuda_dirs": [str(d) for d in (bindir, bindir / "x64", bindir.parent / "lib64") if d.is_dir()],
        "src": setup.source_hash(setup.ENGINE_SOURCES),
        "vision_src": setup.source_hash(setup.VISION_SOURCES) if vision != "none" else None}
(eng / "BUILD.json").write_text(json.dumps(meta, indent=1))
PYEOF

# the cmake trees are build-time only; the engine itself is what the container needs
RUN rm -rf build build-vision

# Forward-compatibility libraries are for datacenter GPUs; on GeForce the host
# driver provides the CUDA runtime.
RUN rm -rf /usr/local/cuda-13.0/compat /usr/local/cuda/compat

VOLUME ["/data"]
EXPOSE 8080

# /health answers before the API key gate. The port only opens after the model
# loads (1-3 minutes, longer on a first run), so the start period is generous:
# a too short one marks a still-loading container unhealthy and a restart
# policy would kill it mid-download.
HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
  CMD curl -fs "http://127.0.0.1:${PORT:-8080}/health" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
