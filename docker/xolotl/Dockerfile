# Xolotl (Indras-Mirror/Xolotl, MIT) built from source for one RTX 40 card, serving
# Inkling 2 Mini through its own engine `xolotl-inkling` behind Xolotl's
# OpenAI/Anthropic-compatible server (python -m serve.server --engine strata).
ARG CUDA_IMAGE=nvidia/cuda:13.0.0-devel-ubuntu24.04
FROM ${CUDA_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates git libgomp1 libatomic1 python3 python3-venv curl \
    && rm -rf /var/lib/apt/lists/*
ARG XOLOTL_COMMIT=3435d55
ARG CUDA_ARCH=89
WORKDIR /opt/xolotl
RUN git clone -q https://github.com/Indras-Mirror/Xolotl.git . && git checkout -q ${XOLOTL_COMMIT}
RUN python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -q -r requirements.txt -r requirements-build.txt
ENV PATH=/opt/xolotl/.venv/bin:$PATH
RUN bash tools/xolotl/fetch-llama.sh
RUN cmake -S . -B build-xolotl -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON -DSTRATA_GGML_CUDA=ON \
        -DSTRATA_MMQ_KQUANTS=ON -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} -DSTRATA_GGML_DIR=/opt/xolotl/third_party/llama.cpp \
    && ninja -C build-xolotl strata xolotl-inkling xolotl-inkling-dspark
# configs/*.json point "exe" at build-eng/; keep both names.
RUN ln -s build-xolotl build-eng
EXPOSE 8134
ENTRYPOINT ["/opt/xolotl/.venv/bin/python", "-m", "serve.server", "--engine", "strata"]
