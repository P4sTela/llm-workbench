# syntax=docker/dockerfile:1

FROM nvidia/cuda:13.1.2-devel-ubuntu24.04 AS build

ARG DEBIAN_FRONTEND=noninteractive
ARG NINFER_REPO=https://github.com/sergiuszm/ninfer-4090.git
ARG NINFER_COMMIT=1bd56c9a1bdf457c6188391a9385d44d86e953aa

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        cmake \
        git \
        libavcodec-dev \
        libavformat-dev \
        libavutil-dev \
        libcurl4-openssl-dev \
        libswscale-dev \
        ninja-build \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git init /src \
    && git -C /src remote add origin "$NINFER_REPO" \
    && git -C /src fetch --depth 1 origin "$NINFER_COMMIT" \
    && git -C /src checkout --detach "$NINFER_COMMIT" \
    && test "$(git -C /src rev-parse HEAD)" = "$NINFER_COMMIT"

RUN cmake -S /src -B /build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CUDA_ARCHITECTURES=89 \
        -DNINFER_BUILD_APPS=ON \
        -DBUILD_TESTING=OFF \
        -DNINFER_BUILD_BENCHMARKS=OFF \
    && cmake --build /build --parallel --target ninfer ninfer-serve

FROM nvidia/cuda:13.1.2-runtime-ubuntu24.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libavcodec60 \
        libavformat60 \
        libavutil58 \
        libcurl4t64 \
        libswscale7 \
    && rm -rf /var/lib/apt/lists/*

# GeForce cards must use the host driver rather than the CUDA image's forward-compatibility
# libraries, which are intended for datacenter GPUs.
RUN rm -rf /usr/local/cuda-13.1/compat /usr/local/cuda-13/compat /usr/local/cuda/compat

COPY --from=build /build/apps/ninfer /usr/local/bin/ninfer
COPY --from=build /build/apps/ninfer-serve /usr/local/bin/ninfer-serve

WORKDIR /workspace
EXPOSE 8080
STOPSIGNAL SIGTERM

CMD ["ninfer-serve", "--help"]
