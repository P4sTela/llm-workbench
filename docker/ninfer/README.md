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

The source contract and static recipe were checked here. Docker Buildx using the `orbstack`
builder successfully built the Dockerfile for `linux/amd64`, and the resulting image was
loaded as `llm-workbench-ninfer-v2:sm89`. In that image, `ninfer-serve --help` and
`ninfer --help` also ran successfully without a GPU, with the expected NVIDIA
driver-not-detected warning. GPU runtime on an NVIDIA host, model download, and the smoke
script against a real NInfer server remain untested here.
