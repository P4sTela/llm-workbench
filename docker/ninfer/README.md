# NInfer V2

This recipe builds [`sergiuszm/ninfer-4090`](https://github.com/sergiuszm/ninfer-4090) at
pinned commit `1bd56c9a1bdf457c6188391a9385d44d86e953aa`. The Dockerfile passes
`CMAKE_CUDA_ARCHITECTURES=89` explicitly and builds `ninfer` plus `ninfer-serve`.

Compose reads the tested launch values from
[`configs/ninfer-v2-qwen38-4090-262k-e8-mtp3.env`](../../configs/ninfer-v2-qwen38-4090-262k-e8-mtp3.env),
mounts `MODEL_DIR` read-only at `/workspace/models`, and publishes loopback `127.0.0.1:8080`
by default. Weights are never copied into the image. See the root README for the clean-checkout
workflow, [`download-qwen38-27b.sh`](../../scripts/download-qwen38-27b.sh), and
[`smoke-ninfer.sh`](../../scripts/smoke-ninfer.sh).

The source contract and static recipe were checked here. The Docker build, model download,
GPU runtime, and API smoke test were not run in this environment.
