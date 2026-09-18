# LLM Workbench

A personal workbench for experimenting with open-weight LLMs across different machines.

This is a public collection of Docker configurations, machine-specific settings, and notes from real runs. It is intentionally practical and experimental rather than a general-purpose framework or a production platform.

## Current focus

- Qwen3.8-27B on an NVIDIA RTX 4090
- NInfer and llama.cpp
- Long-context, KV-cache, speculative decoding, reasoning, and tool-use experiments
- Reproducible configurations that can move to another Linux GPU host

## Repository layout

- `docker/` — container definitions and compose files
- `configs/` — reusable runtime profiles
- `models/` — model metadata and download instructions; weights are not committed
- `notes/` — short notes and results from actual runs
- `scripts/` — small helpers for fetching, checking, and smoke-testing

## Principles

- Pin model revisions and record checksums when a run matters.
- Keep model weights outside Git and mount them into containers.
- Keep host-specific values such as bind addresses in local `.env` files.
- Mark results as tested, experimental, or failed instead of presenting guesses as benchmarks.
- Do not commit API keys, personal prompts, session logs, or private tool definitions.

## First recipe: NInfer V2 / Qwen3.8-27B / RTX 4090

This is the first reproducible recipe, kept deliberately small. It builds the public
`sergiuszm/ninfer-4090` source at commit
`1bd56c9a1bdf457c6188391a9385d44d86e953aa`, which pins the `sm_89` CUDA target. The
model stays on the host and is mounted read-only; it is not part of the image.

### Clean-checkout workflow

On a Linux host with an RTX 4090, a recent NVIDIA driver, Docker, and the NVIDIA
Container Toolkit:

```bash
export MODEL_DIR=/path/to/ninfer-models
python3 scripts/download-model.py models/manifests/qwen3.8-27b-ninfer-v2.json
docker compose -f docker/ninfer/compose.yaml build
MODEL_DIR="$MODEL_DIR" docker compose -f docker/ninfer/compose.yaml up
```

The manifest-driven command is canonical. It uses `MODEL_DIR`, then
`NINFER_MODEL_DIR`, and otherwise `models/`. Each exact quantization or artifact
gets its own manifest so future multi-file downloads do not need a new downloader.
The compatibility command `NINFER_MODEL_DIR="$MODEL_DIR" bash scripts/download-qwen38-27b.sh`
continues to use the same manifest.

In another terminal, run the small local API check:

```bash
bash scripts/smoke-ninfer.sh
```

The published port defaults to `127.0.0.1:8080`; override it with `NINFER_BIND_ADDRESS`
and `NINFER_PORT` when needed. The Compose command reads every launch value from
`configs/ninfer-v2-qwen38-4090-262k-e8-mtp3.env` explicitly.

The repository's notes record the earlier real RTX 4090 run. In this checkout I verified
the source/build contract and static recipe shape. Docker Buildx using the `orbstack`
builder successfully built the Dockerfile for `linux/amd64`, and the resulting image was
loaded as `llm-workbench-ninfer-v2:sm89`. In that image, `ninfer-serve --help` and
`ninfer --help` also ran successfully without a GPU, with the expected NVIDIA
driver-not-detected warning. GPU runtime on an NVIDIA host, model download, and the smoke
script against a real NInfer server remain untested here.

## DFlash2 experiment: Qwen3.8-27B / RTX 4090

`notes/qwen38-dflash2.md` documents the experimental DFlash2 path. It pins the
`z-lab/Qwen3.8-27B-DFlash2` drafter, downloads it into an isolated directory,
and grafts its W8/BF16 objects onto the existing V2 target artifact. The runtime
profile uses `SPEC=dflash2` and seven draft tokens; it does not enable the MTP
`--lm-head-draft` flag. The recipe and artifact conversion are statically
checked here, but the full graft requires the target artifact and a GPU run is
not yet verified in this checkout.

Select the profile explicitly when launching Compose. The DFlash2 engine
source lives in the P4sTela fork, so also override the build args (see
`notes/qwen38-dflash2.md` for the exact commit):

```bash
NINFER_REPO=https://github.com/P4sTela/ninfer-4090.git \
NINFER_COMMIT=95f6a04d \
NINFER_IMAGE=ninfer-4090:dflash2 \
NINFER_PROFILE=../../configs/ninfer-v2-qwen38-4090-262k-e8-dflash2.env \
  docker compose -f docker/ninfer/compose.yaml up --build
```

## License

No repository license has been selected yet. Until a license is added, the contents should not be assumed to be available for reuse. Model and dependency licenses remain the responsibility of their respective upstream projects.
