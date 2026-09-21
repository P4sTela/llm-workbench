# NInfer V2

This recipe builds [`P4sTela/ninfer-4090`](https://github.com/P4sTela/ninfer-4090) at
pinned commit `a889ce4377d0f88093bb491d851d29eb1555e4f8`. The Dockerfile passes
`CMAKE_CUDA_ARCHITECTURES=89` explicitly and builds `ninfer` plus `ninfer-serve`.

Compose defaults to the verified `ninfer-4090:dflash2` image and reads the canonical
245760-token launch values from
[`configs/ninfer-v2-qwen38-4090-245760-e8-dflash2.env`](../../configs/ninfer-v2-qwen38-4090-245760-e8-dflash2.env).
It mounts `MODEL_DIR` read-only at `/workspace/models` and publishes loopback
`127.0.0.1:8080` by default. `NINFER_BIND_ADDRESS`, `NINFER_PORT`, and `MODEL_DIR`
remain host-side overrides. Weights are never copied into the image. See the root README
for the clean-checkout workflow and [`smoke-ninfer.sh`](../../scripts/smoke-ninfer.sh).

Download the base artifact with the canonical manifest-driven command, then fetch and graft
the DFlash2 drafter:

```bash
MODEL_DIR=/path/to/ninfer-models \
  python3 ../../scripts/download-model.py ../../models/manifests/qwen3.8-27b-ninfer-v2.json
MODEL_DIR=/path/to/ninfer-models bash ../../scripts/download-qwen38-dflash2.sh
MODEL_DIR=/path/to/ninfer-models bash ../../scripts/graft-qwen38-dflash2.sh
```

The downloader falls back to `NINFER_MODEL_DIR` when `MODEL_DIR` is unset, then to
`models/`. [`download-qwen38-27b.sh`](../../scripts/download-qwen38-27b.sh) remains as a
compatibility wrapper. Each exact quantization or artifact gets its own manifest.

The default profile is the verified VM205 RTX 4090 DFlash2 runtime: context and KV
capacity 245760, prefill chunk 512, E8 KV, seven draft tokens, and the host/runtime
reservations recorded in the profile. The generated graft report is local metadata and is
not a repository artifact. The 245760 MTP3 profile is available for comparison, but GPU
validation is pending. The checked-in 262k profiles are retained as unsupported/
failed-capacity RTX 4090 experiments rather than defaults.
